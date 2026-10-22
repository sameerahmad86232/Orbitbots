"""Run against an isolated test container, not a personal desktop.
ORBIT_TEST_TOKEN_FILE points at a local secret file; credentials are never printed.
"""
import io,json,os,re,subprocess,time,urllib.request,urllib.error,uuid
from pathlib import Path
from PIL import Image
BASE=os.getenv('ORBIT_TEST_URL','http://127.0.0.1:8123');NAME=os.getenv('ORBIT_TEST_CONTAINER','orbit-computer-v3')
TOKEN=Path(os.environ['ORBIT_TEST_TOKEN_FILE']).read_text().strip()
def api(path,body=None,method=None,token=TOKEN):
 req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method=method or ('POST' if body is not None else 'GET'))
 with urllib.request.urlopen(req,timeout=65) as r:return r.read() if path=='/screen' else json.load(r)
def denied(path,body,code,method=None,token=TOKEN):
 try:api(path,body,method,token);raise AssertionError('Expected HTTP '+str(code))
 except urllib.error.HTTPError as e:assert e.code==code,(e.code,code)
def inside(*cmd):return subprocess.check_output(['docker','exec',NAME,*cmd]).decode().strip()
def action(payload):return api('/actions',payload)['id']
def approve(ident):return api('/actions/'+ident+'/review',{'approved':True})
for _ in range(30):
 try:
  api('/status');break
 except (urllib.error.URLError,ConnectionError):time.sleep(1)
subprocess.run(['docker','exec',NAME,'pkill','-x','xmessage'],capture_output=True)
time.sleep(.3)
for _ in range(25):
 if api('/status').get('browser'):break
 time.sleep(1)
assert api('/status')['ready'] and api('/status')['browser'];denied('/status',None,401,token='invalid')
raw=api('/screen');assert Image.open(io.BytesIO(raw)).size==(1280,800)
ident=action({'kind':'open_url','text':'http://127.0.0.1:8080/'})
assert api('/actions/'+ident)['status']=='pending'
assert approve(ident)['status']=='done';denied('/actions/'+ident+'/review',{'approved':True},409)
time.sleep(2)
assert 'Orbit Computer' in inside('xdotool','getactivewindow','getwindowname')
# A local X11 fixture proves real OS click execution, not a mocked DOM event.
marker='/data/click-test-'+uuid.uuid4().hex
subprocess.check_call(['docker','exec','-d',NAME,'sh','-c',"xmessage -name OrbitClickFixture -geometry 400x200+300+250 -buttons Done:0 'Click to finish local test' && touch "+marker])
time.sleep(1)
window=inside('xdotool','search','--name','OrbitClickFixture').splitlines()[-1]
geom=inside('xwininfo','-id',window)
x=int(re.search(r'Absolute upper-left X:\s+(\d+)',geom).group(1))+30
y=int(re.search(r'Absolute upper-left Y:\s+(\d+)',geom).group(1))+int(re.search(r'Height:\s+(\d+)',geom).group(1))-18
if os.getenv('ORBIT_TEST_STREAM')=='1':
 import asyncio
 from test_stream import pointer
 asyncio.run(pointer(x,y))
 assert inside('sh','-c','test ! -e '+marker+' && echo blocked')=='blocked'
 print('PASS: direct VNC pointer injection blocked at the server; approval gate cannot be bypassed')
click=action({'kind':'click','x':x,'y':y})
assert inside('sh','-c','test ! -e '+marker+' && echo waiting')=='waiting'
assert approve(click)['status']=='done';time.sleep(.5)
assert inside('sh','-c','test -e '+marker+' && echo clicked')=='clicked'
# Rejected requests never execute.
rejected=action({'kind':'type','text':'must never type'})
assert api('/actions/'+rejected+'/review',{'approved':False})['status']=='rejected';denied('/actions/'+rejected+'/review',{'approved':True},409)
denied('/actions',{'kind':'click','x':1280,'y':0},422);denied('/actions',{'kind':'terminal','text':'echo disabled'},403)
api('/knowledge',{'title':'Contract fixture','content':'Orbit unique nebula knowledge fact 7351'})
assert any('Contract fixture'==m['title'] for m in api('/knowledge?q=7351')['matches'])
routine=api('/routines',{'name':'Fixture only','action':{'kind':'key','text':'Return'},'interval_seconds':60,'enabled':True})['id']
inside('python','-c',"import sqlite3;c=sqlite3.connect('/data/orbit.sqlite');c.execute('UPDATE routines SET next_run=0 WHERE id=?',('"+routine+"',));c.commit()")
time.sleep(3)
assert any(json.loads(e['details']).get('routine')==routine for e in api('/audit')['events'] if e['event']=='routine_queued')
api('/routines/'+routine,method='DELETE')
assert any(e['event']=='execution_done' for e in api('/audit')['events'])
if os.getenv('ORBIT_TEST_AGENT')=='1':
 job=api('/jobs',{'goal':'Fixture browser navigation '+uuid.uuid4().hex,'max_steps':3})['id']
 for _ in range(15):
  item=next(j for j in api('/jobs')['jobs'] if j['id']==job)
  if item['state'] in ('waiting_approval','error'):break
  time.sleep(1)
 assert item['state']=='waiting_approval',item
 assert approve(item['action_id'])['status']=='done'
 for _ in range(15):
  item=next(j for j in api('/jobs')['jobs'] if j['id']==job)
  if item['state'] in ('completed','error','limit_reached'):break
  time.sleep(1)
 assert item['state']=='completed',item
 assert item['step']==2
 print('PASS: screenshot → local model-protocol fixture → pending action → real browser input → screenshot → completed persistent server job. Fixture is not real AI inference.')
Path(os.getenv('ORBIT_TEST_SCREENSHOT','/tmp/orbit-live-after.jpg')).write_bytes(api('/screen'))
print('PASS: real container desktop capture, actual browser navigation, actual X11 click, pending/reject/approve gates, replay prevention, validation, FTS retrieval, persistent scheduler queue and audit trail. No paid model or external email used.')
