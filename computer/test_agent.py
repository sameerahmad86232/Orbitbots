import asyncio,json,os,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
os.environ['ORBIT_DATA']=tempfile.mkdtemp(prefix='orbit-agent-test-')
os.environ['ORBIT_TOKEN']='owner-agent-fixture-'+('z'*32)
import server
SEEN=[]
class Model(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));SEEN.append(data)
  command={'kind':'key','text':'Return'} if len(SEEN)==1 else {'kind':'finish','text':'Fixture task completed'}
  out=json.dumps({'choices':[{'message':{'content':json.dumps(command)}}]}).encode();self.send_response(200);self.send_header('Content-Length',str(len(out)));self.end_headers();self.wfile.write(out)
class AgentTest(unittest.IsolatedAsyncioTestCase):
 async def test_loop_has_real_http_model_contract_and_waits_for_approval(self):
  from fastapi.testclient import TestClient
  model=ThreadingHTTPServer(('127.0.0.1',0),Model);threading.Thread(target=model.serve_forever,daemon=True).start();SEEN.clear()
  env={'MODEL_BASE_URL':'http://127.0.0.1:'+str(model.server_address[1])+'/v1','MODEL_ID':'fixture-vision'}
  try:
   with patch.dict(os.environ,env),patch.object(server,'screenshot',return_value=b'fixture-jpeg-bytes'):
    # No lifespan/background task: explicitly step the durable worker.
    client=TestClient(server.app);headers={'Authorization':'Bearer '+os.environ['ORBIT_TOKEN']}
    ident=client.post('/jobs',json={'goal':'Fixture goal','max_steps':3},headers=headers).json()['id']
    await server.agent_tick()
    with server.db() as c:job=dict(c.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone())
    self.assertEqual(job['state'],'waiting_approval');self.assertEqual(len(SEEN),1)
    self.assertTrue(SEEN[0]['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,'))
    await server.agent_tick();self.assertEqual(len(SEEN),1)
    with patch.object(server,'execute',return_value={'executed':True}):self.assertEqual(client.post('/actions/'+job['action_id']+'/review',json={'approved':True},headers=headers).json()['status'],'done')
    await server.agent_tick()
    with server.db() as c:result=dict(c.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone())
    self.assertEqual(result['state'],'completed');self.assertEqual(result['step'],2)
    self.assertEqual(result['result'],'Fixture task completed')
    # Cancellation rejects the pending action and prevents future requests.
    SEEN.clear();cancel=client.post('/jobs',json={'goal':'Cancel fixture','max_steps':2},headers=headers).json()['id'];await server.agent_tick()
    client.post('/jobs/'+cancel+'/cancel',json={},headers=headers);await server.agent_tick();self.assertEqual(len(SEEN),1)
    with server.db() as c:self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=?',(cancel,)).fetchone()[0],'cancelled')
  finally:model.shutdown();model.server_close()
if __name__=='__main__':unittest.main()
