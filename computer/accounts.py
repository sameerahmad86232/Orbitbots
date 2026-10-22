"""User accounts and opaque, per-user encrypted backup envelopes."""
import hashlib,hmac,json,os,secrets,time
from fastapi import Depends,Header,HTTPException,Request
from pydantic import BaseModel,Field
class NewUser(BaseModel):
 username:str=Field(pattern=r'^[a-zA-Z0-9_.-]{3,60}$');password:str=Field(min_length=12,max_length=200);role:str=Field(pattern='^(owner|reviewer|viewer)$')
class Login(BaseModel):username:str=Field(max_length=60);password:str=Field(max_length=200)
class Backup(BaseModel):base_revision:int=Field(ge=0);envelope:dict
ATTEMPTS={}
def install(s):
 with s.db() as c:c.executescript('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,salt TEXT,password TEXT,role TEXT,disabled INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,user_id TEXT,expires REAL);CREATE TABLE IF NOT EXISTS backups(user_id TEXT PRIMARY KEY,revision INTEGER,envelope TEXT,updated REAL);')
 def session(token):
  with s.db() as c:r=c.execute('SELECT u.id,u.role FROM sessions t JOIN users u ON u.id=t.user_id WHERE t.hash=? AND t.expires>? AND u.disabled=0',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
  return dict(r) if r else None
 def identity(authorization:str=Header(default='')):
  token=authorization.removeprefix('Bearer ')
  for role,value in [('owner',s.TOKEN),('reviewer',os.getenv('ORBIT_REVIEWER_TOKEN','')),('viewer',os.getenv('ORBIT_VIEWER_TOKEN',''))]:
   if value and hmac.compare_digest(token,value):return 'workspace-'+role
  user=session(token)
  if not user:raise HTTPException(401,'Sign in required')
  return user['id']
 @s.app.post('/users',dependencies=[Depends(s.owner)])
 def create(u:NewUser):
  salt=secrets.token_hex(16);digest=hashlib.scrypt(u.password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
  with s.db() as c:
   if c.execute('SELECT 1 FROM users WHERE id=?',(u.username,)).fetchone():raise HTTPException(409,'Username exists')
   c.execute('INSERT INTO users VALUES(?,?,?,?,0)',(u.username,salt,digest,u.role))
  s.audit('user_created',{'user':u.username,'role':u.role});return {'username':u.username,'role':u.role}
 @s.app.post('/login')
 def login(u:Login,request:Request):
  address=request.client.host if request.client else 'unknown';now=time.time();recent=[t for t in ATTEMPTS.get(address,[]) if t>now-60];ATTEMPTS[address]=recent+[now]
  if len(recent)>=10:raise HTTPException(429,'Too many attempts; wait one minute')
  with s.db() as c:r=c.execute('SELECT * FROM users WHERE id=? AND disabled=0',(u.username,)).fetchone()
  salt=bytes.fromhex(r['salt']) if r else b'not-a-real-user!';digest=hashlib.scrypt(u.password.encode(),salt=salt,n=16384,r=8,p=1).hex()
  if not r or not hmac.compare_digest(digest,r['password']):raise HTTPException(401,'Invalid username or password')
  token=secrets.token_urlsafe(36)
  with s.db() as c:c.execute('DELETE FROM sessions WHERE expires<?',(now,));c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),r['id'],now+86400))
  return {'access_token':token,'expires_in':86400,'role':r['role']}
 @s.app.post('/logout',dependencies=[Depends(s.auth)])
 def logout(authorization:str=Header(default='')):
  with s.db() as c:c.execute('DELETE FROM sessions WHERE hash=?',(hashlib.sha256(authorization.removeprefix('Bearer ').encode()).hexdigest(),))
  return {'logged_out':True}
 @s.app.get('/users',dependencies=[Depends(s.owner)])
 def users():
  with s.db() as c:return {'users':[dict(r) for r in c.execute('SELECT id,role,disabled FROM users')]}
 @s.app.post('/users/{name}/disable',dependencies=[Depends(s.owner)])
 def disable(name:str):
  with s.db() as c:c.execute('UPDATE users SET disabled=1 WHERE id=?',(name,));c.execute('DELETE FROM sessions WHERE user_id=?',(name,))
  return {'disabled':True}
 @s.app.get('/sync',dependencies=[Depends(s.auth)])
 def get_backup(user=Depends(identity)):
  with s.db() as c:r=c.execute('SELECT * FROM backups WHERE user_id=?',(user,)).fetchone()
  return {'revision':r['revision'],'envelope':json.loads(r['envelope']),'updated':r['updated']} if r else {'revision':0}
 @s.app.post('/sync',dependencies=[Depends(s.auth)])
 def save_backup(b:Backup,user=Depends(identity)):
  if b.envelope.get('version')!=1 or any(not isinstance(b.envelope.get(k),str) for k in ['salt','iv','data']):raise HTTPException(422,'Unsupported encrypted envelope')
  encoded=json.dumps(b.envelope)
  if len(encoded)>20000000:raise HTTPException(413,'Encrypted backup limit: 20 MB')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT revision FROM backups WHERE user_id=?',(user,)).fetchone();revision=r[0] if r else 0
   if revision!=b.base_revision:raise HTTPException(409,'Backup changed on another device; refresh before overwriting')
   c.execute('INSERT OR REPLACE INTO backups VALUES(?,?,?,?)',(user,revision+1,encoded,time.time()))
  return {'revision':revision+1}
 return session,identity
