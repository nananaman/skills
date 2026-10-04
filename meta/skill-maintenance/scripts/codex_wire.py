"""Bounded RFC 6455 framing over an existing byte proxy; no socket discovery."""
import base64
import hashlib
import os

LIMIT = 8 * 1024 * 1024


def require(condition, message):
    if not condition: raise ValueError(message)


def exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size-len(data))
        require(chunk, 'WebSocket stream ended')
        data.extend(chunk)
    return bytes(data)


def request():
    key=base64.b64encode(os.urandom(16)).decode('ascii')
    message=('GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
             'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '+key+'\r\n\r\n')
    return key,message.encode('ascii')


def accept(stream,key):
    data=bytearray()
    while not data.endswith(b'\r\n\r\n'):
        require(len(data)<16384,'WebSocket handshake header too large')
        data.extend(exact(stream,1))
    lines=data.decode('ascii').split('\r\n')
    status=lines[0].split(' ')
    require(len(status)>=2 and status[0]=='HTTP/1.1','unknown WebSocket handshake response')
    require(status[1]=='101','WebSocket handshake rejected: HTTP '+status[1])
    headers={}
    for line in lines[1:]:
        if not line:continue
        name,separator,value=line.partition(':')
        require(separator and name.lower() not in headers,'invalid WebSocket handshake header')
        headers[name.lower()]=value.strip()
    expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')
    require(headers.get('upgrade','').lower()=='websocket' and
            'upgrade' in {v.strip().lower() for v in headers.get('connection','').split(',')} and
            headers.get('sec-websocket-accept')==expected,'invalid WebSocket upgrade acceptance')


def frame(payload,opcode=1):
    require(len(payload)<=LIMIT and opcode in {1,8,10},'invalid outgoing WebSocket frame')
    require(opcode==1 or len(payload)<=125,'invalid control frame')
    mask=os.urandom(4);size=len(payload)
    if size<126:header=bytes([0x80|opcode,0x80|size])
    elif size<=65535:header=bytes([0x80|opcode,0xfe])+size.to_bytes(2,'big')
    else:header=bytes([0x80|opcode,0xff])+size.to_bytes(8,'big')
    return header+mask+bytes(value^mask[index%4] for index,value in enumerate(payload))


def receive(stream):
    first,second=exact(stream,2);final=bool(first&0x80);opcode=first&0xf
    require(not first&0x70 and not second&0x80 and opcode in {0,1,8,9,10},'unsupported WebSocket frame')
    size=second&0x7f
    if size==126:size=int.from_bytes(exact(stream,2),'big')
    elif size==127:size=int.from_bytes(exact(stream,8),'big')
    require(size<=LIMIT,'WebSocket frame budget exhausted')
    require(opcode<8 or final and size<=125,'invalid WebSocket control frame')
    return final,opcode,exact(stream,size)
