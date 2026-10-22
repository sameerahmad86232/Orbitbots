"""Explicit, bounded provider-backed media jobs. No bundled models or free credits."""
import asyncio,base64,json,os,re,time,uuid
from pathlib import Path
import httpx
from fastapi import Depends,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
class Generate(BaseModel):
 kind:str=Field(pattern='^(image|video|transcribe|speech)$');prompt:str=Field(default='',max_length=10000);filename:str=Field(default='audio.wav',max_length=100);audio_base64:str=Field(default='',max_length=12000000)
def install(s):
 folder=s.DATA/'media';folder.mkdir(exist_ok=True)
 with s.db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,user_id TEXT,kind TEXT,state TEXT,result TEXT,created REAL,updated REAL)');c.execute("UPDATE media SET state='interrupted',result='Server restarted; request may have been billed. No automatic retry.' WHERE state='running'")
 def config(kind):
  prefix={'image':'IMAGE','video':'VIDEO','transcribe':'TRANSCRIBE','speech':'SPEECH'}[kind];base=os.getenv(prefix+'_BASE_URL','https://api.x.ai/v1' if kind=='video' else '').rstrip('/');model=os.getenv(prefix+'_MODEL','');key=os.getenv(prefix+'_API_KEY','')
  if not base or not model:raise HTTPException(409,'Configure '+prefix+' base URL, model and API key as required')
  s.outbound(base);return base,model,({'Authorization':'Bearer '+key} if key else {})
 def save(ident,data,extension,mime):
  if len(data)>20000000:raise ValueError('Media exceeds 20 MB')
  path=folder/(ident+'.'+extension);path.write_bytes(data);return {'filename':path.name,'mime':mime,'bytes':len(data),'id':ident}
 def work(ident,job):
  try:
   base,model,headers=config(job.kind)
   with httpx.Client(timeout=180,follow_redirects=False) as client:
    if job.kind=='image':
     body={'model':model,'prompt':job.prompt,'n':1}
     if not model.startswith('gpt-image'):body['response_format']='b64_json'
     r=client.post(base+'/images/generations',json=body,headers=headers);r.raise_for_status();item=r.json()['data'][0]
     if not item.get('b64_json'):raise ValueError('Provider must return base64 image output')
     data=base64.b64decode(item['b64_json'],validate=True)
     from PIL import Image
     import io
     im=Image.open(io.BytesIO(data));im.verify();mime={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(im.format)
     if not mime:raise ValueError('Unsupported image format')
     result=save(ident,data,{'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[mime],mime)
    elif job.kind=='speech':
     r=client.post(base+'/audio/speech',json={'model':model,'input':job.prompt,'voice':os.getenv('SPEECH_VOICE','alloy'),'response_format':'mp3'},headers=headers);r.raise_for_status();result=save(ident,r.content,'mp3','audio/mpeg')
    elif job.kind=='transcribe':
     audio=base64.b64decode(job.audio_base64,validate=True)
     if not audio or len(audio)>8000000:raise ValueError('Audio limit: 8 MB')
     name=re.sub('[^A-Za-z0-9_.-]','_',job.filename);r=client.post(base+'/audio/transcriptions',data={'model':model},files={'file':(name,audio,'application/octet-stream')},headers=headers);r.raise_for_status();result={'text':str(r.json()['text'])[:300000]}
    else:
     # xAI's documented asynchronous JSON video protocol. Other protocols are not guessed.
     r=client.post(base+'/videos/generations',json={'model':model,'prompt':job.prompt,'duration':5},headers=headers);r.raise_for_status();request_id=r.json()['request_id']
     if not re.fullmatch('[A-Za-z0-9_-]{1,200}',request_id):raise ValueError('Invalid video request ID')
     result={'provider_request_id':request_id,'note':'Generation accepted; use Check video to poll without creating another paid generation'}
    with s.db() as c:c.execute('UPDATE media SET state=?,result=?,updated=? WHERE id=?',('pending_video' if job.kind=='video' else 'completed',json.dumps(result),time.time(),ident))
  except Exception:
   with s.db() as c:c.execute("UPDATE media SET state='error',result='Provider request failed or output unsupported. Requests already accepted may be billed; no automatic retry.',updated=? WHERE id=?",(time.time(),ident))
 @s.app.get('/media',dependencies=[Depends(s.auth)])
 def listing(user=Depends(s.identity)):
  flags={}
  for kind in ['image','video','transcribe','speech']:
   try:config(kind);flags[kind]=True
   except Exception:flags[kind]=False
  with s.db() as c:return {'configured':flags,'media':[dict(r) for r in c.execute('SELECT * FROM media WHERE user_id=? ORDER BY created DESC LIMIT 30',(user,))]}
 @s.app.post('/media',dependencies=[Depends(s.reviewer)])
 async def generate(job:Generate,user=Depends(s.identity)):
  config(job.kind)
  if job.kind!='transcribe' and not job.prompt.strip():raise HTTPException(422,'Enter a prompt or text')
  ident=uuid.uuid4().hex
  with s.db() as c:
   if c.execute("SELECT COUNT(*) FROM media WHERE user_id=? AND state='running'",(user,)).fetchone()[0]>=2:raise HTTPException(429,'Two media jobs are already running')
   c.execute('INSERT INTO media VALUES(?,?,?,?,?,?,?)',(ident,user,job.kind,'running','',time.time(),time.time()))
  asyncio.create_task(asyncio.to_thread(work,ident,job));return {'id':ident,'state':'running'}
 @s.app.post('/media/{ident}/check',dependencies=[Depends(s.auth)])
 def check(ident:str,user=Depends(s.identity)):
  with s.db() as c:row=c.execute('SELECT * FROM media WHERE id=? AND user_id=?',(ident,user)).fetchone()
  if not row:raise HTTPException(404,'Media job not found')
  if row['state']!='pending_video':return {'state':row['state']}
  base,model,headers=config('video');result=json.loads(row['result'])
  try:
   r=httpx.get(base+'/videos/'+result['provider_request_id'],headers=headers,timeout=45,follow_redirects=False);r.raise_for_status();body=r.json();body=body.get('response',body)
   if body.get('video',{}).get('url'):
    url=body['video']['url']
    from urllib.parse import urlparse
    if urlparse(url).scheme!='https':raise ValueError()
    result['url']=url;state='completed'
   elif body.get('status') in ('failed','error'):state='error'
   else:state='pending_video'
   with s.db() as c:c.execute('UPDATE media SET state=?,result=?,updated=? WHERE id=?',(state,json.dumps(result),time.time(),ident))
   return {'state':state,'result':result}
  except Exception:raise HTTPException(502,'Video status unavailable; request not resubmitted')
 @s.app.get('/media/{ident}/content',dependencies=[Depends(s.auth)])
 def content(ident:str,user=Depends(s.identity)):
  with s.db() as c:row=c.execute('SELECT * FROM media WHERE id=? AND user_id=?',(ident,user)).fetchone()
  if not row or row['state']!='completed':raise HTTPException(404,'Completed file not found')
  result=json.loads(row['result']);name=result.get('filename','')
  if not re.fullmatch(r'[a-f0-9]{32}\.(png|jpg|webp|mp3)',name):raise HTTPException(404,'No downloadable local media file')
  return FileResponse(folder/name,media_type=result['mime'],filename=name)
 return config
