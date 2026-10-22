import os,tempfile,unittest,threading,socketserver,json
from unittest.mock import patch
os.environ['ORBIT_DATA']=tempfile.mkdtemp(prefix='orbit-server-test-')
os.environ['ORBIT_TOKEN']='owner-test-token-'+('a'*32)
os.environ['ORBIT_REVIEWER_TOKEN']='reviewer-test-token-'+('b'*32)
os.environ['ORBIT_VIEWER_TOKEN']='viewer-test-token-'+('c'*32)
import server
from fastapi.testclient import TestClient
MESSAGES=[]
class SMTP(socketserver.StreamRequestHandler):
 def handle(self):
  self.wfile.write(b'220 localhost test SMTP\r\n');data=False;message=[]
  while True:
   line=self.rfile.readline()
   if not line:break
   if data:
    if line==b'.\r\n':MESSAGES.append(b''.join(message));data=False;self.wfile.write(b'250 accepted\r\n')
    else:message.append(line)
   elif line.upper().startswith(b'EHLO'):self.wfile.write(b'250-localhost\r\n250 SIZE 1000000\r\n')
   elif line.upper().startswith(b'DATA'):data=True;self.wfile.write(b'354 end with dot\r\n')
   elif line.upper().startswith(b'QUIT'):self.wfile.write(b'221 bye\r\n');break
   else:self.wfile.write(b'250 ok\r\n')
class Contracts(unittest.TestCase):
 def setUp(self):self.client=TestClient(server.app);self.client.__enter__();self.headers={'Authorization':'Bearer '+os.environ['ORBIT_TOKEN']}
 def tearDown(self):self.client.__exit__(None,None,None)
 def call(self,path,data=None,headers=None):return self.client.request('POST' if data is not None else 'GET',path,json=data,headers=headers or self.headers)
 def test_auth_and_roles(self):
  self.assertEqual(self.client.get('/status').status_code,401)
  viewer={'Authorization':'Bearer '+os.environ['ORBIT_VIEWER_TOKEN']};reviewer={'Authorization':'Bearer '+os.environ['ORBIT_REVIEWER_TOKEN']}
  self.assertEqual(self.call('/status',headers=viewer).status_code,200)
  self.assertEqual(self.call('/actions',{'kind':'key','text':'Return'},headers=viewer).status_code,403)
  ident=self.call('/actions',{'kind':'key','text':'Return'},headers=reviewer).json()['id']
  self.assertEqual(self.call('/actions/'+ident+'/review',{'approved':True},headers=viewer).status_code,403)
  with patch.object(server,'execute',return_value={'executed':True}):self.assertEqual(self.call('/actions/'+ident+'/review',{'approved':True},headers=reviewer).json()['status'],'done')
  self.assertEqual(self.call('/actions/'+ident+'/review',{'approved':True}).status_code,409)
  self.assertEqual(self.call('/routines',{'name':'x','action':{'kind':'key','text':'Return'},'interval_seconds':60},headers=reviewer).status_code,403)
 def test_mail_requires_review_and_sends_once(self):
  MESSAGES.clear();smtp=socketserver.TCPServer(('127.0.0.1',0),SMTP);thread=threading.Thread(target=smtp.serve_forever,daemon=True);thread.start()
  env={'SMTP_HOST':'127.0.0.1','SMTP_PORT':str(smtp.server_address[1]),'SMTP_FROM':'orbit@example.test','ORBIT_SMTP_TEST_PLAINTEXT':'1'}
  try:
   with patch.dict(os.environ,env):
    ident=self.call('/actions',{'kind':'send_email','to':'test@example.test','subject':'Loopback test','text':'No external mail sent'}).json()['id'];self.assertEqual(len(MESSAGES),0)
    self.assertEqual(self.call('/actions/'+ident+'/review',{'approved':True}).json()['status'],'done');self.assertEqual(len(MESSAGES),1);self.assertIn(b'Loopback test',MESSAGES[0])
    self.assertEqual(self.call('/actions/'+ident+'/review',{'approved':True}).status_code,409);self.assertEqual(len(MESSAGES),1)
  finally:smtp.shutdown();smtp.server_close()
 def test_validation_knowledge_and_config(self):
  self.assertEqual(self.call('/actions',{'kind':'click','x':1280}).status_code,422)
  self.assertEqual(self.call('/actions',{'kind':'key','text':'Return;evil'}).status_code,422)
  self.assertEqual(self.call('/actions',{'kind':'terminal','text':'echo no'}).status_code,403)
  self.assertEqual(self.call('/inbox').status_code,409)
  self.call('/knowledge',{'title':'Note','content':'Purple nebula 987654'})
  self.assertEqual(self.call('/knowledge?q=987654').json()['matches'][0]['title'],'Note')
 def test_failed_execution_is_not_retried(self):
  ident=self.call('/actions',{'kind':'key','text':'Return'}).json()['id']
  with patch.object(server,'execute',side_effect=RuntimeError('private secret error')):
   result=self.call('/actions/'+ident+'/review',{'approved':True}).json();self.assertEqual(result['status'],'failed');self.assertNotIn('private secret',str(result))
  self.assertEqual(self.call('/actions/'+ident+'/review',{'approved':True}).status_code,409)
if __name__=='__main__':unittest.main()
