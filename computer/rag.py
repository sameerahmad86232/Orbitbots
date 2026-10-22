import hashlib,json,math,os,re
import httpx
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field
class Index(BaseModel):document_id:str
class Query(BaseModel):query:str=Field(min_length=1,max_length=2000)
def install(s):
 with s.db() as c:c.execute('CREATE TABLE IF NOT EXISTS vectors(doc_id TEXT,chunk INTEGER,model TEXT,text TEXT,vector TEXT,PRIMARY KEY(doc_id,chunk,model))')
 def embed(texts):
  base=os.getenv('EMBEDDING_BASE_URL','').rstrip('/');model=os.getenv('EMBEDDING_MODEL','')
  if not base or not model:raise HTTPException(409,'Configure an embedding endpoint and model')
  s.outbound(base);headers={};key=os.getenv('EMBEDDING_API_KEY','')
  if key:headers['Authorization']='Bearer '+key
  try:
   r=httpx.post(base+'/embeddings',json={'model':model,'input':texts},headers=headers,timeout=90,follow_redirects=False);r.raise_for_status();rows=r.json()['data'];rows=sorted(rows,key=lambda v:v.get('index',0));vectors=[v['embedding'] for v in rows]
   if len(vectors)!=len(texts) or not vectors or not all(isinstance(v,list) and 1<=len(v)<=8192 and all(isinstance(n,(float,int)) and math.isfinite(n) for n in v) for v in vectors) or len({len(v) for v in vectors})!=1:raise ValueError()
   return vectors,hashlib.sha256((base+'|'+model).encode()).hexdigest()
  except HTTPException:raise
  except Exception:raise HTTPException(502,'Embedding provider failed or returned invalid vectors')
 @s.app.post('/rag/index',dependencies=[Depends(s.owner)])
 def index(body:Index):
  with s.db() as c:r=c.execute('SELECT * FROM documents WHERE id=?',(body.document_id,)).fetchone()
  if not r:raise HTTPException(404,'Document not found')
  text=r['content'];chunks=[text[i:i+2000] for i in range(0,len(text),1800)]
  if not chunks or len(chunks)>40:raise HTTPException(413,'Index up to 72,000 characters per document; split larger documents first')
  vectors,model=embed(chunks)
  with s.db() as c:
   c.execute('DELETE FROM vectors WHERE doc_id=?',(body.document_id,))
   c.executemany('INSERT INTO vectors VALUES(?,?,?,?,?)',[(body.document_id,i,model,t,json.dumps(v)) for i,(t,v) in enumerate(zip(chunks,vectors))])
  return {'indexed_chunks':len(chunks),'document_id':body.document_id}
 @s.app.post('/rag/search',dependencies=[Depends(s.auth)])
 def search(body:Query):
  vectors,model=embed([body.query]);q=vectors[0];norm=math.sqrt(sum(x*x for x in q));matches=[]
  with s.db() as c:rows=c.execute('SELECT v.*,d.title FROM vectors v JOIN documents d ON d.id=v.doc_id WHERE model=? LIMIT 10000',(model,)).fetchall()
  for r in rows:
   v=json.loads(r['vector'])
   if len(v)!=len(q):continue
   denominator=norm*math.sqrt(sum(x*x for x in v));score=sum(a*b for a,b in zip(q,v))/denominator if denominator else 0
   matches.append({'document_id':r['doc_id'],'title':r['title'],'text':r['text'],'score':score})
  return {'matches':sorted(matches,key=lambda x:x['score'],reverse=True)[:8],'retrieval':'embedding cosine similarity'}
 return search
