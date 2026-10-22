"""Single-workspace self-hosted computer. Every input action requires an approval.
No model credentials are accepted by this API. Deploy behind authenticated TLS.
"""
import asyncio, base64, hashlib, hmac, io, json, os, re, secrets, shlex, sqlite3, subprocess, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ConfigDict
from PIL import Image
DATA=Path(os.getenv('ORBIT_DATA','/tmp/orbit-computer'));DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'orbit.sqlite';TOKEN=os.getenv('ORBIT_TOKEN','');LOCK=asyncio.Lock()
def db():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row;return c
def init():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL,result TEXT,created REAL NOT NULL,reviewed REAL);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT,details TEXT,created REAL);
  CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,title TEXT,content TEXT);
  CREATE VIRTUAL TABLE IF NOT EXISTS knowledge USING fts5(id UNINDEXED,title,content);
  CREATE TABLE IF NOT EXISTS routines(id TEXT PRIMARY KEY,name TEXT,payload TEXT,interval_seconds INTEGER,next_run REAL,enabled INTEGER);
  CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,message TEXT,created REAL);
  ''')
  c.execute("UPDATE actions SET status='interrupted',result='Server restarted during execution; inspect desktop before retrying' WHERE status='executing'")
init()
def audit(event,details):
 with db() as c:c.execute('INSERT INTO audit(event,details,created) VALUES(?,?,?)',(event,json.dumps(details),time.time()))
def auth(authorization:str=Header(default='')):
 supplied=authorization.removeprefix('Bearer ')
 if not authorization.startswith('Bearer '):raise HTTPException(401,'Authentication required')
 for role,value in [('owner',TOKEN),('reviewer',os.getenv('ORBIT_REVIEWER_TOKEN','')),('viewer',os.getenv('ORBIT_VIEWER_TOKEN',''))]:
  if len(value)>=24 and hmac.compare_digest(supplied,value):return role
 raise HTTPException(401,'Authentication required')
def owner(role=Depends(auth)):
 if role!='owner':raise HTTPException(403,'Owner role required')
 return role
def reviewer(role=Depends(auth)):
 if role not in ('owner','reviewer'):raise HTTPException(403,'Reviewer role required')
 return role
class Action(BaseModel):
 model_config=ConfigDict(extra='forbid')
 kind:Literal['click','double_click','drag','type','key','scroll','open_url','terminal','send_email']
 x:int=Field(default=0,ge=0,le=1279);y:int=Field(default=0,ge=0,le=799)
 end_x:int=Field(default=0,ge=0,le=1279);end_y:int=Field(default=0,ge=0,le=799)
 text:str=Field(default='',max_length=20000)
 direction:Literal['up','down']='down'
 steps:int=Field(default=3,ge=1,le=10)
 to:str=Field(default='',max_length=250);subject:str=Field(default='',max_length=250)
class Review(BaseModel):approved:bool
class Document(BaseModel):title:str=Field(max_length=150);content:str=Field(max_length=300000)
class Routine(BaseModel):name:str=Field(max_length=100);action:Action;interval_seconds:int=Field(ge=60,le=2592000);enabled:bool=False
def run(argv,timeout=15):return subprocess.run(argv,check=True,capture_output=True,timeout=timeout).stdout
def screenshot():
 raw=run(['scrot','-z','-'],10);im=Image.open(io.BytesIO(raw)).convert('RGB');out=io.BytesIO();im.save(out,'JPEG',quality=65);return out.getvalue()
def validate_action(a):
 if a.kind=='key' and not re.fullmatch(r'(ctrl\+|alt\+|shift\+|super\+){0,3}(Return|Tab|Escape|BackSpace|Delete|space|Left|Right|Up|Down|Home|End|Page_Up|Page_Down|[a-zA-Z0-9]|F[1-9]|F1[0-2])',a.text):raise HTTPException(422,'Unsupported key combination')
 if a.kind=='open_url':
  from urllib.parse import urlparse
  u=urlparse(a.text)
  if u.scheme not in ['https','http'] or not u.hostname or u.username or u.password:raise HTTPException(422,'Use a web URL without credentials')
 if a.kind=='terminal' and os.getenv('ORBIT_ALLOW_TERMINAL')!='1':raise HTTPException(403,'Terminal disabled by server administrator')
 if a.kind=='send_email':
  if not os.getenv('SMTP_HOST') or not os.getenv('SMTP_FROM'):raise HTTPException(409,'SMTP is not configured')
  if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',a.to) or '\n' in a.subject or '\r' in a.subject:raise HTTPException(422,'Invalid email')
def enqueue(a):
 validate_action(a);ident=uuid.uuid4().hex
 with db() as c:c.execute('INSERT INTO actions VALUES(?,?,?,NULL,?,NULL)',(ident,a.model_dump_json(),'pending',time.time()))
 audit('approval_requested',{'id':ident,'kind':a.kind});return ident
def execute(a):
 if a.kind in ('click','double_click'):
  run(['xdotool','mousemove','--sync',str(a.x),str(a.y)]);run(['xdotool','click','--repeat','2' if a.kind=='double_click' else '1','--delay','100','1'])
 elif a.kind=='drag':run(['xdotool','mousemove','--sync',str(a.x),str(a.y),'mousedown','1','mousemove','--sync',str(a.end_x),str(a.end_y),'mouseup','1'])
 elif a.kind=='type':run(['xdotool','type','--clearmodifiers','--delay','1','--',a.text],45)
 elif a.kind=='key':run(['xdotool','key','--clearmodifiers',a.text])
 elif a.kind=='scroll':run(['xdotool','click','--repeat',str(a.steps),'--delay','60','4' if a.direction=='up' else '5'])
 elif a.kind=='open_url':run(['xdotool','key','--clearmodifiers','ctrl+l']);run(['xdotool','type','--clearmodifiers','--delay','1','--',a.text]);run(['xdotool','key','Return'])
 elif a.kind=='terminal':
  p=subprocess.run(['bash','-lc',a.text],cwd=DATA,capture_output=True,timeout=30,env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ('TOKEN','KEY','SECRET','PASSWORD','SMTP','IMAP'))});return {'stdout':p.stdout.decode(errors='replace')[:20000],'stderr':p.stderr.decode(errors='replace')[:5000],'exit_code':p.returncode}
 elif a.kind=='send_email':
  import smtplib, ssl
  from email.message import EmailMessage
  msg=EmailMessage();msg['From']=os.environ['SMTP_FROM'];msg['To']=a.to;msg['Subject']=a.subject;msg.set_content(a.text)
  port=int(os.getenv('SMTP_PORT','587'));client=smtplib.SMTP_SSL if port==465 else smtplib.SMTP
  with client(os.environ['SMTP_HOST'],port,timeout=20) as s:
   if port!=465:
    if os.getenv('ORBIT_SMTP_TEST_PLAINTEXT')=='1':
     if os.environ['SMTP_HOST'] not in ('localhost','127.0.0.1'):raise RuntimeError('Plaintext mail is limited to loopback tests')
    else:s.starttls(context=ssl.create_default_context())
   if os.getenv('SMTP_USER'):s.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
   s.send_message(msg)
  return {'sent':True,'to':a.to}
 return {'executed':True}
async def ticker():
 while True:
  await asyncio.sleep(2)
  now=time.time()
  with db() as c:
   due=c.execute('SELECT * FROM routines WHERE enabled=1 AND next_run<=?',(now,)).fetchall()
   for r in due:
    # Claim schedule in the transaction; missed intervals coalesce into one run.
    c.execute('UPDATE routines SET next_run=? WHERE id=?',(now+r['interval_seconds'],r['id']))
  for r in due:
   try:ident=enqueue(Action.model_validate_json(r['payload']));audit('routine_queued',{'routine':r['id'],'approval':ident})
   except Exception:audit('routine_error',{'routine':r['id']})
@asynccontextmanager
async def lifespan(app):
 if len(TOKEN)<24:raise RuntimeError('ORBIT_TOKEN must be at least 24 characters')
 task=asyncio.create_task(ticker());brain=asyncio.create_task(agent_worker())
 try:yield
 finally:
  task.cancel();brain.cancel();await asyncio.gather(task,brain,return_exceptions=True)
app=FastAPI(title='Orbit Computer',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
@app.middleware('http')
async def headers(request,call_next):
 response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer';response.headers['X-Frame-Options']='DENY';return response
@app.get('/status',dependencies=[Depends(auth)])
def status():
 try:run(['xdotool','getdisplaygeometry']);ready=True
 except Exception:ready=False
 try:browser=bool(run(['xdotool','search','--onlyvisible','--class','chromium'],3))
 except Exception:browser=False
 with db() as c:pending=c.execute("SELECT COUNT(*) FROM actions WHERE status='pending'").fetchone()[0]
 return {'ready':ready,'browser':browser,'width':1280,'height':800,'pending':pending,'terminal':os.getenv('ORBIT_ALLOW_TERMINAL')=='1','smtp':bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')),'imap':bool(os.getenv('IMAP_HOST') and os.getenv('IMAP_USER')),'preview':'JPEG polling, not WebRTC/VNC','approval_policy':'all actions','version':'3.0','agent':bool(os.getenv('MODEL_BASE_URL') and os.getenv('MODEL_ID'))}
@app.get('/screen',dependencies=[Depends(auth)])
async def screen():
 try:return Response(await asyncio.to_thread(screenshot),media_type='image/jpeg')
 except Exception:raise HTTPException(503,'Desktop capture unavailable')
@app.post('/actions',dependencies=[Depends(reviewer)])
def actions(a:Action):return {'id':enqueue(a),'status':'pending','message':'Review the exact action before approval'}
@app.get('/actions',dependencies=[Depends(auth)])
def list_actions():
 with db() as c:rows=c.execute('SELECT * FROM actions ORDER BY created DESC LIMIT 40').fetchall()
 return {'actions':[{**dict(r),'payload':json.loads(r['payload'])} for r in rows]}
@app.get('/actions/{ident}',dependencies=[Depends(auth)])
def get_action(ident:str):
 with db() as c:r=c.execute('SELECT * FROM actions WHERE id=?',(ident,)).fetchone()
 if not r:raise HTTPException(404,'Unknown action')
 return {**dict(r),'payload':json.loads(r['payload'])}
@app.post('/actions/{ident}/review',dependencies=[Depends(reviewer)])
async def review(ident:str,decision:Review):
 async with LOCK:
  with db() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM actions WHERE id=?',(ident,)).fetchone()
   if not r:raise HTTPException(404,'Unknown action')
   if r['status']!='pending':raise HTTPException(409,'Already reviewed; actions never replay automatically')
   c.execute('UPDATE actions SET status=?,reviewed=? WHERE id=?',('executing' if decision.approved else 'rejected',time.time(),ident))
  audit('approved' if decision.approved else 'rejected',{'id':ident})
  if not decision.approved:return {'status':'rejected'}
  try:
   a=Action.model_validate_json(r['payload']);validate_action(a);result=await asyncio.to_thread(execute,a);state='done'
  except Exception:result={'error':'Action failed or timed out. Inspect the desktop before retrying; an external action may have partially completed.'};state='failed'
  with db() as c:c.execute('UPDATE actions SET status=?,result=? WHERE id=?',(state,json.dumps(result),ident))
  audit('execution_'+state,{'id':ident});return {'status':state,'result':result}
@app.get('/audit',dependencies=[Depends(auth)])
def logs():
 with db() as c:return {'events':[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]}
@app.post('/knowledge',dependencies=[Depends(owner)])
def knowledge(d:Document):
 ident=uuid.uuid4().hex
 with db() as c:c.execute('INSERT INTO documents VALUES(?,?,?)',(ident,d.title,d.content));c.execute('INSERT INTO knowledge VALUES(?,?,?)',(ident,d.title,d.content))
 return {'id':ident}
@app.get('/knowledge',dependencies=[Depends(auth)])
def search(q:str):
 terms=re.findall(r'\w+',q)[:12]
 if not terms:return {'matches':[]}
 query=' OR '.join('"'+t+'"' for t in terms)
 with db() as c:return {'matches':[dict(r) for r in c.execute("SELECT id,title,snippet(knowledge,2,'[',']','…',35) AS excerpt FROM knowledge WHERE knowledge MATCH ? ORDER BY rank LIMIT 8",(query,))]}
@app.post('/routines',dependencies=[Depends(owner)])
def routine(r:Routine):
 validate_action(r.action);ident=uuid.uuid4().hex
 with db() as c:c.execute('INSERT INTO routines VALUES(?,?,?,?,?,?)',(ident,r.name,r.action.model_dump_json(),r.interval_seconds,time.time()+r.interval_seconds,int(r.enabled)))
 return {'id':ident,'enabled':r.enabled,'note':'Scheduled actions queue for approval; they do not bypass review'}
@app.get('/routines',dependencies=[Depends(auth)])
def routines():
 with db() as c:return {'routines':[dict(r) for r in c.execute('SELECT * FROM routines')]}
@app.delete('/routines/{ident}',dependencies=[Depends(owner)])
def delete_routine(ident:str):
 with db() as c:c.execute('DELETE FROM routines WHERE id=?',(ident,))
 return {'deleted':True}
@app.get('/inbox',dependencies=[Depends(owner)])
def inbox():
 if not os.getenv('IMAP_HOST') or not os.getenv('IMAP_USER'):raise HTTPException(409,'IMAP not configured')
 import imaplib,email
 try:
  with imaplib.IMAP4_SSL(os.environ['IMAP_HOST'],int(os.getenv('IMAP_PORT','993'))) as im:
   im.login(os.environ['IMAP_USER'],os.environ.get('IMAP_PASSWORD',''));im.select('INBOX',readonly=True);_,ids=im.search(None,'ALL');messages=[]
   for ident in ids[0].split()[-10:]:
    _,rows=im.fetch(ident,'(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])');raw=next((row[1] for row in rows if isinstance(row,tuple)),b'');m=email.message_from_bytes(raw);messages.append({'id':ident.decode(),'from':m.get('From',''),'subject':m.get('Subject',''),'date':m.get('Date','')})
   return {'messages':messages}
 except Exception:raise HTTPException(502,'IMAP connection failed; check server configuration')
@app.get('/')
def home():return HTMLResponse((Path(__file__).parent/'preview.html').read_text())

import sys
from agent import install
agent_worker,agent_tick,agent_model=install(sys.modules[__name__])
