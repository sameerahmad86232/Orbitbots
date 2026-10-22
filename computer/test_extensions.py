import base64,hashlib,hmac,io,json,os,tempfile,time,unittest
from unittest.mock import patch
os.environ['ORBIT_DATA']=tempfile.mkdtemp(prefix='orbit-ext-');os.environ['ORBIT_TOKEN']='owner-fixture-'+('x'*40)
import server
from fastapi.testclient import TestClient
import httpx
class Extensions(unittest.TestCase):
 def setUp(self):self.client=TestClient(server.app);self.client.__enter__();self.h={'Authorization':'Bearer '+os.environ['ORBIT_TOKEN']}
 def tearDown(self):self.client.__exit__(None,None,None)
 def post(self,path,body,h=None):return self.client.post(path,json=body,headers=h or self.h)
 def response(self,data):return httpx.Response(200,json=data,request=httpx.Request('POST','https://fixture.example'))
 def test_accounts_sync_conflicts_and_role_isolation(self):
  name='viewer'+str(time.time_ns());self.assertEqual(self.post('/users',{'username':name,'password':'fixture password enough','role':'viewer'}).status_code,200)
  result=self.post('/login',{'username':name,'password':'fixture password enough'}).json();user={'Authorization':'Bearer '+result['access_token']}
  self.assertEqual(self.post('/actions',{'kind':'key','text':'Return'},user).status_code,403)
  envelope={'version':1,'salt':'opaque','iv':'opaque','data':'encrypted-ciphertext'}
  self.assertEqual(self.post('/sync',{'base_revision':0,'envelope':envelope},user).json()['revision'],1)
  self.assertEqual(self.post('/sync',{'base_revision':0,'envelope':envelope},user).status_code,409)
  self.assertEqual(self.client.get('/sync',headers=self.h).json()['revision'],0)
  self.post('/users/'+name+'/disable',{});self.assertEqual(self.client.get('/sync',headers=user).status_code,401)
 def test_oauth_state_pkce_exchange_encryption_and_fixed_origins(self):
  env={'PUBLIC_BASE_URL':'https://orbit.example','GOOGLE_CLIENT_ID':'fixture-client','GOOGLE_CLIENT_SECRET':'fixture-secret'}
  with patch.dict(os.environ,env):
   start=self.post('/connectors/google/start',{}).json()['authorization_url']
   from urllib.parse import urlparse,parse_qs
   params=parse_qs(urlparse(start).query);self.assertIn('code_challenge',params)
   with patch('httpx.post',return_value=self.response({'access_token':'provider-fixture-token','refresh_token':'provider-fixture-refresh','expires_in':3600})):
    self.assertEqual(self.client.get('/oauth/google/callback',params={'state':params['state'][0],'code':'fixture-code'}).status_code,200)
    self.assertEqual(self.client.get('/oauth/google/callback',params={'state':params['state'][0],'code':'fixture-code'}).status_code,400)
   with server.db() as c:stored=c.execute("SELECT token FROM connections WHERE provider='google'").fetchone()[0]
   self.assertNotIn('provider-fixture-token',stored)
   with patch('httpx.request',return_value=self.response({'messages':[]})) as request:
    self.assertEqual(self.client.get('/connectors/google/items',headers=self.h).status_code,200);self.assertTrue(request.call_args.args[1].startswith('https://gmail.googleapis.com/'))
   queued=self.post('/connectors/google/write',{'operation':'send','payload':{'to':'a@example.test','subject':'Fixture','text':'Only mock'}}).json()['id']
   with patch('httpx.request',return_value=self.response({'id':'fixture-sent'})) as request:
    result=self.post('/actions/'+queued+'/review',{'approved':True});self.assertEqual(result.json()['status'],'done');self.assertEqual(request.call_count,1)
   self.assertEqual(self.post('/actions',{'kind':'connector_write','account':'victim','connector':'google'}).status_code,403)
 def test_embeddings_and_documents(self):
  doc=self.post('/knowledge',{'title':'Fixture semantic doc','content':'Green tea knowledge'}).json()['id']
  env={'EMBEDDING_BASE_URL':'https://embed.example/v1','EMBEDDING_MODEL':'fixture'}
  with patch.dict(os.environ,env),patch('httpx.post',return_value=self.response({'data':[{'index':0,'embedding':[1.0,0.0,0.5]}]})):
   self.assertEqual(self.post('/rag/index',{'document_id':doc}).json()['indexed_chunks'],1)
   matches=self.post('/rag/search',{'query':'tea'}).json()['matches'];self.assertEqual(matches[0]['document_id'],doc);self.assertAlmostEqual(matches[0]['score'],1.0)
  result=self.post('/documents/extract',{'filename':'note.txt','data':base64.b64encode('hello ✓'.encode()).decode()}).json();self.assertEqual(result['text'],'hello ✓')
 def test_checkout_review_idempotency_and_signed_webhook(self):
  env={'STRIPE_SECRET_KEY':'sk_test_fixture','STRIPE_RETURN_URL':'https://orbit.example/thanks','STRIPE_WEBHOOK_SECRET':'fixture-webhook-secret'}
  with patch.dict(os.environ,env):
   action=self.post('/payments/checkout',{'name':'Fixture','amount':20000,'currency':'inr'}).json()['id']
   with patch('httpx.post',return_value=self.response({'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/cs_fixture'})) as upstream:
    self.assertEqual(upstream.call_count,0);self.assertEqual(self.post('/actions/'+action+'/review',{'approved':True}).json()['status'],'done');self.assertEqual(upstream.call_args.kwargs['headers']['Idempotency-Key'],action)
   event={'id':'evt_fixture','type':'checkout.session.completed','data':{'object':{'id':'cs_fixture','payment_status':'paid'}}};raw=json.dumps(event).encode();stamp=str(int(time.time()));signature=hmac.new(env['STRIPE_WEBHOOK_SECRET'].encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
   self.assertEqual(self.client.post('/payments/webhook',content=raw,headers={'stripe-signature':'t='+stamp+',v1='+signature}).status_code,200)
   self.assertEqual(self.client.get('/payments',headers=self.h).json()['checkouts'][0]['status'],'paid')
   self.assertEqual(self.client.post('/payments/webhook',content=raw,headers={'stripe-signature':'t='+stamp+',v1=bad'}).status_code,400)
 def test_media_image_and_realtime_signaling_contract(self):
  from PIL import Image
  image=io.BytesIO();Image.new('RGB',(4,4),'blue').save(image,'PNG')
  env={'IMAGE_BASE_URL':'https://image.example/v1','IMAGE_MODEL':'fixture-image','REALTIME_API_KEY':'fixture-voice-key','REALTIME_MODEL':'fixture-voice-model'}
  with patch.dict(os.environ,env),patch('httpx.Client') as client_factory:
   client_factory.return_value.__enter__.return_value.post.return_value=self.response({'data':[{'b64_json':base64.b64encode(image.getvalue()).decode()}]})
   result=self.post('/media',{'kind':'image','prompt':'Fixture'}).json();ident=result['id']
   for _ in range(30):
    row=next(x for x in self.client.get('/media',headers=self.h).json()['media'] if x['id']==ident)
    if row['state']!='running':break
    time.sleep(.02)
   self.assertEqual(row['state'],'completed');self.assertEqual(self.client.get('/media/'+ident+'/content',headers=self.h).headers['content-type'],'image/png')
  with patch.dict(os.environ,env),patch('httpx.post',return_value=httpx.Response(201,text='v=0\r\nfixture-answer',request=httpx.Request('POST','https://api.openai.com'))):
   self.assertIn('sdp',self.post('/voice/offer',{'sdp':'v=0\r\nfixture-offer'}).json())
if __name__=='__main__':unittest.main()
