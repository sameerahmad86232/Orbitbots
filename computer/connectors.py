"""Fixed-origin OAuth connectors. Tokens encrypted at rest; writes require action review."""
import base64,hashlib,json,os,re,secrets,time
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from fastapi import Depends,Header,HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
PROVIDERS={
 'google':('https://accounts.google.com/o/oauth2/v2/auth','https://oauth2.googleapis.com/token','https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send',False,True),
 'microsoft':('https://login.microsoftonline.com/common/oauth2/v2.0/authorize','https://login.microsoftonline.com/common/oauth2/v2.0/token','offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send',False,True),
 'notion':('https://api.notion.com/v1/oauth/authorize','https://api.notion.com/v1/oauth/token','',True,False),
 'figma':('https://www.figma.com/oauth','https://api.figma.com/v1/oauth/token','current_user:read file_content:read file_comments:write',True,True),
 'canva':('https://www.canva.com/api/oauth/authorize','https://api.canva.com/rest/v1/oauth/token','design:meta:read design:content:read',True,True),
 'quickbooks':('https://appcenter.intuit.com/connect/oauth2','https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer','com.intuit.quickbooks.accounting',True,False)
}
def install(s):
 keyfile=s.DATA/'connector.key'
 if not keyfile.exists():
  fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
 vault=Fernet(keyfile.read_bytes())
 with s.db() as c:c.executescript('CREATE TABLE IF NOT EXISTS oauth_states(hash TEXT PRIMARY KEY,user_id TEXT,provider TEXT,verifier TEXT,expires REAL);CREATE TABLE IF NOT EXISTS connections(user_id TEXT,provider TEXT,token TEXT,updated REAL,PRIMARY KEY(user_id,provider));')
 def config(name):
  if name not in PROVIDERS:raise HTTPException(404,'Unknown connector')
  client=os.getenv(name.upper()+'_CLIENT_ID','');secret=os.getenv(name.upper()+'_CLIENT_SECRET','');origin=os.getenv('PUBLIC_BASE_URL','').rstrip('/')
  if not client or not secret or not origin.startswith('https://'):raise HTTPException(409,'Register this OAuth app and configure its client ID, secret and public HTTPS server URL')
  return client,secret,origin+'/oauth/'+name+'/callback'
 def store(user,name,data):
  with s.db() as c:c.execute('INSERT OR REPLACE INTO connections VALUES(?,?,?,?)',(user,name,vault.encrypt(json.dumps(data).encode()).decode(),time.time()))
 def tokens(user,name):
  with s.db() as c:r=c.execute('SELECT token FROM connections WHERE user_id=? AND provider=?',(user,name)).fetchone()
  if not r:raise HTTPException(409,'Connect the account first')
  data=json.loads(vault.decrypt(r['token'].encode()))
  if data.get('_expires',time.time()+60)<time.time()+30 and data.get('refresh_token'):
   client,secret,redirect=config(name);params={'grant_type':'refresh_token','refresh_token':data['refresh_token']};basic=PROVIDERS[name][3]
   if not basic:params.update(client_id=client,client_secret=secret)
   r=httpx.post(PROVIDERS[name][1],json=params if name=='notion' else None,data=None if name=='notion' else params,auth=(client,secret) if basic else None,timeout=30,follow_redirects=False)
   if r.status_code!=200:raise HTTPException(409,'Account refresh failed; reconnect')
   update=r.json();data.update(update);data['_expires']=time.time()+int(update.get('expires_in',3600));store(user,name,data)
  return data
 @s.app.get('/connectors',dependencies=[Depends(s.auth)])
 def listing(user=Depends(s.identity)):
  with s.db() as c:connected={r[0] for r in c.execute('SELECT provider FROM connections WHERE user_id=?',(user,))}
  return {'connectors':[{'id':n,'connected':n in connected,'configured':bool(os.getenv(n.upper()+'_CLIENT_ID') and os.getenv(n.upper()+'_CLIENT_SECRET') and os.getenv('PUBLIC_BASE_URL','').startswith('https://'))} for n in PROVIDERS]}
 @s.app.post('/connectors/{name}/start',dependencies=[Depends(s.auth)])
 def start(name:str,user=Depends(s.identity)):
  client,secret,redirect=config(name);state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);auth,token,scope,basic,pkce=PROVIDERS[name]
  with s.db() as c:c.execute('DELETE FROM oauth_states WHERE expires<?',(time.time(),));c.execute('INSERT INTO oauth_states VALUES(?,?,?,?,?)',(hashlib.sha256(state.encode()).hexdigest(),user,name,verifier,time.time()+600))
  params={'client_id':client,'redirect_uri':redirect,'response_type':'code','state':state}
  if scope:params['scope']=scope
  if pkce:params.update(code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),code_challenge_method='S256')
  if name=='google':params.update(access_type='offline',prompt='consent')
  if name=='notion':params['owner']='user'
  return {'authorization_url':auth+'?'+urlencode(params)}
 @s.app.get('/oauth/{name}/callback')
 def callback(name:str,state:str='',code:str='',realmId:str='',error:str=''):
  if name not in PROVIDERS or not state:raise HTTPException(400,'Invalid authorization response')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM oauth_states WHERE hash=?',(hashlib.sha256(state.encode()).hexdigest(),)).fetchone();c.execute('DELETE FROM oauth_states WHERE hash=?',(hashlib.sha256(state.encode()).hexdigest(),))
  if not row or row['provider']!=name or row['expires']<time.time():raise HTTPException(400,'Authorization state expired or already used')
  if error or not code:return HTMLResponse('Authorization was not completed. Return to Orbit and reconnect.',status_code=400)
  client,secret,redirect=config(name);params={'grant_type':'authorization_code','code':code,'redirect_uri':redirect};basic=PROVIDERS[name][3]
  if PROVIDERS[name][4]:params['code_verifier']=row['verifier']
  if not basic:params.update(client_id=client,client_secret=secret)
  try:
   r=httpx.post(PROVIDERS[name][1],json=params if name=='notion' else None,data=None if name=='notion' else params,auth=(client,secret) if basic else None,timeout=30,follow_redirects=False)
   if r.status_code!=200 or not r.json().get('access_token'):raise ValueError()
   data=r.json();data['_connection_id']=secrets.token_hex(16);data['_expires']=time.time()+int(data.get('expires_in',31536000));data['_realm']=realmId;store(row['user_id'],name,data)
  except Exception:raise HTTPException(502,'OAuth token exchange failed; retry connecting')
  return HTMLResponse('<h2>Account connected</h2><p>Return to Orbit. No account tokens are shown here.</p>')
 @s.app.delete('/connectors/{name}',dependencies=[Depends(s.auth)])
 def disconnect(name:str,user=Depends(s.identity)):
  with s.db() as c:c.execute('DELETE FROM connections WHERE user_id=? AND provider=?',(user,name))
  return {'disconnected':True,'note':'Local credentials removed; revoke the app in the provider account settings to revoke upstream access'}
 def request(user,name,operation,payload):
  data=tokens(user,name);headers={'Authorization':'Bearer '+data['access_token']};method='GET';body=None
  if name=='google' and operation=='list':url='https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10'
  elif name=='microsoft' and operation=='list':url='https://graph.microsoft.com/v1.0/me/messages?$top=10&$select=id,subject,from,receivedDateTime'
  elif name=='notion' and operation=='list':url='https://api.notion.com/v1/search';method='POST';body={'page_size':20}
  elif name=='figma' and operation=='list':url='https://api.figma.com/v1/me'
  elif name=='canva' and operation=='list':url='https://api.canva.com/rest/v1/designs'
  elif name=='quickbooks' and operation=='list':
   realm=data.get('_realm','')
   if not realm.isdigit():raise HTTPException(409,'Reconnect QuickBooks to select a company')
   url='https://quickbooks.api.intuit.com/v3/company/'+realm+'/companyinfo/'+realm;headers['Accept']='application/json'
  elif name=='notion' and operation=='create_page':url='https://api.notion.com/v1/pages';method='POST';body=payload
  elif name=='figma' and operation=='comment':
   file=str(payload.get('file',''))
   if not re.fullmatch('[A-Za-z0-9_-]{1,150}',file):raise HTTPException(422,'Invalid Figma file key')
   url='https://api.figma.com/v1/files/'+file+'/comments';method='POST';body={'message':str(payload.get('message',''))[:10000]}
  elif name in ('google','microsoft') and operation=='send':
   to=str(payload.get('to',''));subject=str(payload.get('subject',''));text=str(payload.get('text',''))
   if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',to) or '\n' in subject or '\r' in subject:raise HTTPException(422,'Invalid recipient or subject')
   method='POST'
   if name=='google':
    from email.message import EmailMessage
    msg=EmailMessage();msg['To']=to;msg['Subject']=subject;msg.set_content(text);body={'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode()};url='https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
   else:url='https://graph.microsoft.com/v1.0/me/sendMail';body={'message':{'subject':subject,'body':{'contentType':'Text','content':text},'toRecipients':[{'emailAddress':{'address':to}}]}}
  else:raise HTTPException(422,'Unsupported connector operation')
  if name=='notion':headers['Notion-Version']='2026-03-11'
  r=httpx.request(method,url,json=body,headers=headers,timeout=45,follow_redirects=False)
  if not 200<=r.status_code<300:raise HTTPException(502,'Provider rejected the request; check permissions and account access')
  return r.json() if r.content else {'completed':True}
 @s.app.get('/connectors/{name}/items',dependencies=[Depends(s.auth)])
 def items(name:str,user=Depends(s.identity)):return {'data':request(user,name,'list',{})}
 class Write(BaseModel):operation:str=Field(max_length=50);payload:dict
 @s.app.post('/connectors/{name}/write',dependencies=[Depends(s.reviewer)])
 def queue_write(name:str,body:Write,user=Depends(s.identity)):
  allowed={'google':['send'],'microsoft':['send'],'notion':['create_page'],'figma':['comment']}
  if body.operation not in allowed.get(name,[]):raise HTTPException(422,'Unsupported write operation')
  connected=tokens(user,name)
  if len(json.dumps(body.payload))>50000:raise HTTPException(413,'Write payload too large')
  action=s.Action(kind='connector_write',connector=name,operation=body.operation,account=user,connection_id=connected.get('_connection_id',''),payload=body.payload)
  return {'id':s.enqueue(action),'status':'pending'}
 # Writes are NOT exposed directly: queued actions bind this identity before review.
 def write(a,ident):
  if tokens(a.account,a.connector).get('_connection_id','')!=a.connection_id:raise HTTPException(409,'Account connection changed; queue and review a new request')
  return request(a.account,a.connector,a.operation,a.payload)
 return write
