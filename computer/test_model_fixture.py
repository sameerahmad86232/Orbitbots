"""Local test fixture only. Not a language model; never started by the product."""
import base64,io,json
from http.server import BaseHTTPRequestHandler,HTTPServer
from PIL import Image
SEEN={}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  request=json.loads(self.rfile.read(int(self.headers['Content-Length'])));content=request['messages'][1]['content'];Image.open(io.BytesIO(base64.b64decode(content[1]['image_url']['url'].split(',',1)[1]))).verify();goal=content[0]['text'].split('\nPrevious action')[0];SEEN[goal]=SEEN.get(goal,0)+1
  action={'kind':'open_url','text':'http://127.0.0.1:8080/'} if SEEN[goal]==1 else {'kind':'finish','text':'Fixture observed completed browser navigation'}
  body=json.dumps({'choices':[{'message':{'content':json.dumps(action)}}]}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
HTTPServer(('127.0.0.1',8130),Handler).serve_forever()
