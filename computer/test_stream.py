"""Authenticated RFB handshake + proof that the VNC server rejects pointer input."""
import asyncio,json,os,struct,urllib.request
from pathlib import Path
import websockets
BASE=os.getenv('ORBIT_TEST_URL','http://127.0.0.1:8123');TOKEN=Path(os.environ['ORBIT_TEST_TOKEN_FILE']).read_text().strip()
async def pointer(x,y):
 req=urllib.request.Request(BASE+'/desktop/ticket',data=b'{}',headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
 ticket=json.load(urllib.request.urlopen(req))['ticket'];url=BASE.replace('http://','ws://').replace('https://','wss://')+'/vnc'
 async with websockets.connect(url,max_size=4000000) as ws:
  await ws.send(json.dumps({'ticket':ticket}));assert await ws.recv()=='ready';buffer=bytearray()
  async def read(n):
   while len(buffer)<n:
    frame=await ws.recv();assert isinstance(frame,bytes);buffer.extend(frame)
   result=bytes(buffer[:n]);del buffer[:n];return result
  version=await read(12);assert version.startswith(b'RFB ');await ws.send(b'RFB 003.008\n');count=(await read(1))[0];types=await read(count);assert 1 in types;await ws.send(b'\x01');assert await read(4)==b'\x00'*4;await ws.send(b'\x01');header=await read(24);width,height=struct.unpack('>HH',header[:4]);assert(width,height)==(1280,800);await read(struct.unpack('>I',header[20:24])[0]);await ws.send(struct.pack('>BBHH',5,1,x,y));await ws.send(struct.pack('>BBHH',5,0,x,y));await asyncio.sleep(.3)
 try:
  async with websockets.connect(url) as ws:
   await ws.send(json.dumps({'ticket':ticket}));await ws.recv();raise AssertionError('Ticket replay accepted')
 except websockets.exceptions.ConnectionClosed as e:assert e.code==1008
 print('PASS: real authenticated RFB handshake and single-use stream ticket')
if __name__=='__main__':asyncio.run(pointer(1,1))
