import asyncio,json,os,secrets,time
from pathlib import Path
import httpx
from fastapi import Depends,HTTPException,WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
class Offer(BaseModel):sdp:str=Field(min_length=10,max_length=100000)
def install(s):
 tickets={}
 @s.app.post('/desktop/ticket',dependencies=[Depends(s.auth)])
 def ticket():
  now=time.time()
  for key in list(tickets):
   if tickets[key]<now:tickets.pop(key,None)
  value=secrets.token_urlsafe(32);tickets[value]=now+30;return {'ticket':value,'expires_in':30}
 @s.app.websocket('/vnc')
 async def vnc(ws:WebSocket):
  await ws.accept();writer=None
  try:
   initial=await asyncio.wait_for(ws.receive_json(),10);expires=tickets.pop(initial.get('ticket',''),0)
   if expires<time.time():await ws.close(code=1008);return
   reader,writer=await asyncio.open_connection('127.0.0.1',5900);await ws.send_text('ready')
   async def up():
    while True:
     data=await ws.receive_bytes()
     if len(data)>1000000:raise ValueError()
     writer.write(data);await writer.drain()
   async def down():
    while True:
     data=await reader.read(65536)
     if not data:return
     await ws.send_bytes(data)
   tasks=[asyncio.create_task(up()),asyncio.create_task(down())];done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
   for task in pending:task.cancel()
   await asyncio.gather(*tasks,return_exceptions=True)
  except Exception:pass
  finally:
   if writer:writer.close()
   try:await ws.close()
   except Exception:pass
 @s.app.get('/desktop')
 def desktop():return HTMLResponse((Path(__file__).parent/'desktop.html').read_text())
 root=Path('/opt/novnc')
 if root.exists():s.app.mount('/novnc',StaticFiles(directory=root),name='novnc')
 @s.app.get('/voice')
 def voice():return HTMLResponse((Path(__file__).parent/'voice.html').read_text())
 @s.app.post('/voice/offer',dependencies=[Depends(s.reviewer)])
 def offer(body:Offer):
  key=os.getenv('REALTIME_API_KEY','');model=os.getenv('REALTIME_MODEL','')
  if not key or not model:raise HTTPException(409,'Configure an OpenAI Realtime API key and model on the server')
  session={'type':'realtime','model':model,'audio':{'output':{'voice':os.getenv('REALTIME_VOICE','marin')}},'instructions':'You are an independent Orbit voice assistant. Have a helpful conversation. You have no computer, payment or email tools in this voice session. Never claim to perform external actions.'}
  r=httpx.post('https://api.openai.com/v1/realtime/calls',files={'sdp':(None,body.sdp),'session':(None,json.dumps(session))},headers={'Authorization':'Bearer '+key},timeout=45,follow_redirects=False)
  if r.status_code not in (200,201):raise HTTPException(502,'Realtime provider rejected session setup')
  return {'sdp':r.text}
