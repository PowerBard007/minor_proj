"""CoAP gateway, virtual process, local dashboard and evidence logging.

The PLC, not Python, decides when to open/close the valve. Python integrates
the most recently observed valve output into simulated adhesive quantity.
"""
import argparse
import asyncio
import csv
import json
from pathlib import Path
import sqlite3
import time
import aiocoap
import aiocoap.resource as resource
from aiohttp import web
from plc_io import PLC
from policy import rejection

DASHBOARD = '''<!doctype html><html><head><meta charset="utf-8"><title>Ghost Dose</title>
<style>body{font:18px system-ui;background:#101827;color:#eef4ff;margin:40px;max-width:1000px}
h1{color:#80e6d2}pre{background:#1e293b;padding:24px;white-space:pre-wrap}
.meters{display:flex;gap:30px}.meter{flex:1;padding:20px;background:#1e293b}
progress{width:100%;height:28px}small{color:#b9c9db}</style></head><body>
<h1>Ghost Dose</h1><p>CoAP → NS-3 → gateway → OpenPLC → virtual dispenser</p>
<div class="meters"><div class="meter">Actual dose (experiment observer)
<p id="actual"></p><progress id="actualbar" max="12"></progress></div>
<div class="meter">Reported dose (operator display)
<p id="reported"></p><progress id="reportedbar" max="12"></progress></div></div>
<p id="status"></p><pre id="detail"></pre>
<small>The reference target is set locally by the experiment operator.
Freeze affects the reported display only; it does not alter PLC feedback.</small>
<script>setInterval(async()=>{try{let s=await(await fetch('/state')).json();
for(let k of ['actual','reported']){document.getElementById(k).textContent=s[k].toFixed(2)+' units';
document.getElementById(k+'bar').value=s[k]}
document.getElementById('status').textContent=s.phase+' | '+s.mode+' | Job '+s.job_id;
document.getElementById('detail').textContent=JSON.stringify(s,null,2);
}catch(e){document.getElementById('status').textContent='DISCONNECTED: '+e}},250)</script></body></html>'''

class Lab:
    def __init__(self, args):
        self.args = args
        self.plc = PLC(port=args.plc_port)
        self.plc.write(2, [0])
        self.lock = asyncio.Lock()
        self.phase = 'IDLE'; self.job_id = ''; self.target = 0
        self.actual = 0.; self.reported = 0.; self.freeze = False
        self.valve = 0; self.ack = 0; self.fault = 0; self.verdict = ''
        self.last_decision = ''; self.started = 0.; self.last_tick = time.monotonic()
        self.last_log = 0.; self.command_issued = None; self.pending_sequence = None
        self.args.out.mkdir(parents=True, exist_ok=True)
        self.files = []
        self.telemetry = self.writer('telemetry.csv', ['wall_time','job_id','phase','target','actual','reported','valve','ack','fault','mode'])
        self.commands = self.writer('commands.csv', ['wall_time','job_id','command_id','command_job','dose','age_ms','decision','mode'])
        self.jobs = self.writer('jobs.csv', ['wall_time','job_id','target','actual','error','verdict','mode'])
        args.state.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(args.state)
        self.db.execute('CREATE TABLE IF NOT EXISTS used (command_id TEXT PRIMARY KEY, reserved_at REAL)')
        self.db.commit()

    def writer(self, name, fields):
        path = self.args.out / name
        if path.exists():
            raise RuntimeError(f'{path} already exists. Use a fresh --out directory per run.')
        f = path.open('w', newline='', encoding='utf-8', buffering=1)
        self.files.append(f)
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        return w

    def state(self):
        return dict(mode=self.args.mode, job_id=self.job_id, phase=self.phase, target=self.target,
            actual=round(self.actual,3), reported=round(self.reported,3), valve=self.valve,
            ack=self.ack, fault=self.fault, verdict=self.verdict, freeze=self.freeze,
            last_decision=self.last_decision)

    async def begin(self, request):
        try:
            data = await request.json()
            target = float(data['target']); job = data['job_id']
            if not isinstance(job, str) or not 1 <= len(job) <= 80 or not 0 < target <= 10:
                raise ValueError('Use a job ID and a reference target in (0,10].')
        except (ValueError, TypeError, KeyError) as exc:
            raise web.HTTPBadRequest(text=str(exc))
        async with self.lock:
            if self.phase in ('READY','DISPENSING'):
                raise web.HTTPConflict(text='Wait for the current job to finish or time out.')
            self.plc.write(2, [0])
            await asyncio.sleep(.15)  # Several PLC scans reset its state.
            r = self.plc.read()
            self.plc.write(0, [0, r[4], 1, 0])
            self.job_id=job; self.target=target; self.actual=0.; self.reported=0.
            self.phase='READY'; self.verdict=''; self.valve=0; self.fault=0
            self.started=time.monotonic(); self.last_tick=self.started
            self.pending_sequence=None; self.command_issued=None
        return web.json_response(self.state())

    async def command(self, c):
        async with self.lock:
            now = time.time()
            cid = c.get('command_id') if isinstance(c, dict) else None
            seen = isinstance(cid, str) and self.db.execute('SELECT 1 FROM used WHERE command_id=?', (cid,)).fetchone() is not None
            reason = rejection(c, mode=self.args.mode, job_id=self.job_id, phase=self.phase,
                               now=now, seen=seen, max_age=self.args.max_age)
            if reason is None:
                # Reserve before the side effect: crash/restart fails closed, not exactly-once delivery.
                if self.args.mode == 'protected':
                    self.db.execute('INSERT INTO used VALUES (?,?)', (cid,now)); self.db.commit()
                try:
                    r = self.plc.read()
                    sequence = (r[4] % 65535) + 1
                    self.plc.write(0, [round(c['dose']*100), sequence])
                    self.phase='DISPENSING'; self.pending_sequence=sequence
                    self.command_issued=c['issued_at']
                    reason='staged'
                except Exception as exc:
                    reason='plc_error'; self.finish('ERROR')
                    print('PLC error:', repr(exc), flush=True)
            self.last_decision=reason
            obj = c if isinstance(c, dict) else {}
            issued = obj.get('issued_at')
            age = (now-issued)*1000 if isinstance(issued,(int,float)) else ''
            self.commands.writerow(dict(wall_time=now,job_id=self.job_id,command_id=cid,
                command_job=obj.get('job_id'),dose=obj.get('dose'),age_ms=age,decision=reason,mode=self.args.mode))
            print(json.dumps({'decision':reason, 'active_job':self.job_id, 'command':c}), flush=True)
            return reason

    def finish(self, verdict=None):
        self.phase='DONE' if verdict is None else verdict
        self.verdict=verdict or ('PASS' if abs(self.actual-self.target)<=0.5 else 'DEFECT')
        self.jobs.writerow(dict(wall_time=time.time(),job_id=self.job_id,target=self.target,
            actual=round(self.actual,4),error=round(self.actual-self.target,4),verdict=self.verdict,mode=self.args.mode))
        self.plc.write(2,[0]); self.valve=0

    async def tick(self):
        while True:
            await asyncio.sleep(.05)
            async with self.lock:
                now=time.monotonic(); dt=now-self.last_tick; self.last_tick=now
                if self.phase in ('READY','DISPENSING'):
                    if dt > .5:
                        self.finish('TIMING_ERROR')
                        print('Host scheduling gap exceeded 0.5 s; discard this trial.', flush=True)
                        continue
                    # Integrate previous observed output; approximation error is about one poll interval.
                    self.actual += 2.0*dt*self.valve
                    self.plc.write(3,[min(65535,round(self.actual*100))])
                    r=self.plc.read(); self.ack=r[4]; self.valve=int(r[5]!=0); self.fault=r[7]
                    if self.fault:
                        self.finish('PLC_FAULT')
                    elif self.phase=='DISPENSING' and r[6] and self.ack==self.pending_sequence:
                        self.finish()
                    elif now-self.started > 12:
                        self.finish('ABORTED')
                if not self.freeze:
                    self.reported=self.actual
                if now-self.last_log >= .1:
                    self.last_log=now
                    self.telemetry.writerow(dict(wall_time=time.time(),job_id=self.job_id,phase=self.phase,
                        target=self.target,actual=self.actual,reported=self.reported,valve=self.valve,
                        ack=self.ack,fault=self.fault,mode=self.args.mode))

    async def set_freeze(self, request):
        data=await request.json()
        if type(data.get('enabled')) is not bool:
            raise web.HTTPBadRequest(text='enabled must be Boolean')
        self.freeze=data['enabled']
        return web.json_response(self.state())

    def close(self):
        try: self.plc.write(2,[0])
        except Exception: pass
        self.plc.close(); self.db.close()
        for f in self.files: f.close()

class Recipe(resource.Resource):
    def __init__(self, lab): super().__init__(); self.lab=lab
    async def render_post(self, request):
        try: c=json.loads(request.payload)
        except (ValueError,UnicodeError):
            return aiocoap.Message(code=aiocoap.BAD_REQUEST,payload=b'{"decision":"invalid_json"}')
        result=await self.lab.command(c)
        code=aiocoap.CHANGED if result=='staged' else aiocoap.BAD_REQUEST
        return aiocoap.Message(code=code,payload=json.dumps({'decision':result}).encode(),content_format=50)

async def main(args):
    lab=Lab(args)
    coap=None; runner=None
    try:
        app=web.Application(client_max_size=4096)
        async def index(request): return web.Response(text=DASHBOARD,content_type='text/html')
        async def state(request): return web.json_response(lab.state())
        app.add_routes([web.get('/',index),web.get('/state',state),web.post('/begin',lab.begin),web.post('/freeze',lab.set_freeze)])
        runner=web.AppRunner(app); await runner.setup()
        await web.TCPSite(runner,'127.0.0.1',8088).start()
        site=resource.Site(); site.add_resource(['recipe'],Recipe(lab))
        coap=await aiocoap.Context.create_server_context(site,bind=('10.42.0.2',5683),transports=['udp6'])
        print('Dashboard http://127.0.0.1:8088 | CoAP 10.42.0.2:5683 | '+args.mode,flush=True)
        await lab.tick()
    finally:
        lab.close()
        if coap: await coap.shutdown()
        if runner: await runner.cleanup()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['weak','protected'],required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--state',type=Path,default=Path('results/used.sqlite'))
    p.add_argument('--max-age',type=float,default=1.0)
    p.add_argument('--plc-port',type=int,default=1502)
    try: asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt: pass
