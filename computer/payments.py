import hashlib,hmac,json,os,time
import httpx
from fastapi import Depends,HTTPException,Request
from pydantic import BaseModel,Field
class Checkout(BaseModel):name:str=Field(min_length=1,max_length=150);amount:int=Field(ge=1,le=10000000);currency:str=Field(pattern='^[a-z]{3}$')
def install(s):
 with s.db() as c:c.executescript('CREATE TABLE IF NOT EXISTS checkouts(id TEXT PRIMARY KEY,url TEXT,status TEXT,created REAL);CREATE TABLE IF NOT EXISTS payment_events(id TEXT PRIMARY KEY,created REAL);')
 @s.app.post('/payments/checkout',dependencies=[Depends(s.owner)])
 def queue(body:Checkout):
  if not os.getenv('STRIPE_SECRET_KEY') or not os.getenv('STRIPE_RETURN_URL','').startswith('https://'):raise HTTPException(409,'Configure Stripe merchant credentials and HTTPS return URL')
  payload=body.model_dump();ident=s.enqueue(s.Action(kind='stripe_checkout',payload=payload));return {'id':ident,'status':'pending','note':'Creates a checkout link after approval; it does not charge a card automatically'}
 def create(a,ident):
  key=os.environ['STRIPE_SECRET_KEY'];p=Checkout.model_validate(a.payload);return_url=os.environ['STRIPE_RETURN_URL']
  data={'mode':'payment','success_url':return_url,'cancel_url':return_url,'line_items[0][quantity]':'1','line_items[0][price_data][currency]':p.currency,'line_items[0][price_data][unit_amount]':str(p.amount),'line_items[0][price_data][product_data][name]':p.name}
  r=httpx.post('https://api.stripe.com/v1/checkout/sessions',data=data,auth=(key,''),headers={'Idempotency-Key':ident},timeout=45,follow_redirects=False)
  if r.status_code!=200:raise RuntimeError('Stripe checkout rejected')
  result=r.json();url=result.get('url','')
  if not url.startswith('https://checkout.stripe.com/'):raise RuntimeError('Unexpected checkout URL')
  with s.db() as c:c.execute('INSERT OR REPLACE INTO checkouts VALUES(?,?,?,?)',(result['id'],url,'created',time.time()))
  return {'checkout_url':url,'session_id':result['id'],'paid':False}
 @s.app.get('/payments',dependencies=[Depends(s.owner)])
 def listing():
  with s.db() as c:return {'configured':bool(os.getenv('STRIPE_SECRET_KEY')),'checkouts':[dict(r) for r in c.execute('SELECT * FROM checkouts ORDER BY created DESC LIMIT 30')]}
 @s.app.post('/payments/webhook')
 async def webhook(request:Request):
  secret=os.getenv('STRIPE_WEBHOOK_SECRET','')
  if not secret:raise HTTPException(409,'Webhook secret not configured')
  raw=await request.body()
  if len(raw)>1000000:raise HTTPException(413,'Webhook too large')
  try:
   parts={}
   for part in request.headers.get('stripe-signature','').split(','):
    k,v=part.split('=',1);parts.setdefault(k,[]).append(v)
   stamp=int(parts['t'][0]);expected=hmac.new(secret.encode(),str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
   if abs(time.time()-stamp)>300 or not any(hmac.compare_digest(expected,v) for v in parts.get('v1',[])):raise ValueError()
   event=json.loads(raw)
  except Exception:raise HTTPException(400,'Invalid Stripe signature')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT 1 FROM payment_events WHERE id=?',(event['id'],)).fetchone():return {'received':True}
   c.execute('INSERT INTO payment_events VALUES(?,?)',(event['id'],time.time()))
   if event.get('type') in ('checkout.session.completed','checkout.session.async_payment_succeeded') and event['data']['object'].get('payment_status')=='paid':c.execute("UPDATE checkouts SET status='paid' WHERE id=?",(event['data']['object']['id'],))
  return {'received':True}
 return create
