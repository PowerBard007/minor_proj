"""Generate a recipe file or send that exact payload as a new CoAP exchange."""
import argparse
import asyncio
import json
from pathlib import Path
import time
import uuid
import aiocoap

async def send(args):
    c = await aiocoap.Context.create_client_context(transports=['udp6'])
    start = time.monotonic()
    try:
        msg = aiocoap.Message(code=aiocoap.POST, mtype=aiocoap.CON,
            uri='coap://10.42.0.2/recipe', payload=Path(args.file).read_bytes(), content_format=50)
        reply = await asyncio.wait_for(c.request(msg).response, timeout=40)
        print(json.dumps({'code': str(reply.code), 'rtt_ms': round(1000*(time.monotonic()-start), 2),
                          'response': json.loads(reply.payload)}))
    finally:
        await c.shutdown()

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='action', required=True)
    make = sub.add_parser('make')
    make.add_argument('--job', required=True)
    make.add_argument('--dose', required=True, type=float)
    make.add_argument('--file', required=True)
    make.add_argument('--command-id', default=None)
    make.add_argument('--backdate', type=float, default=0)
    tx = sub.add_parser('send'); tx.add_argument('--file', required=True)
    a = p.parse_args()
    if a.action == 'make':
        out = Path(a.file); out.parent.mkdir(parents=True, exist_ok=True)
        data = {'job_id': a.job, 'command_id': a.command_id or str(uuid.uuid4()),
                'dose': a.dose, 'issued_at': time.time()-a.backdate}
        out.write_text(json.dumps(data), encoding='utf-8')
        print(json.dumps(data))
    else:
        asyncio.run(send(a))

if __name__ == '__main__':
    main()
