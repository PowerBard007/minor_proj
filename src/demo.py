"""Run as a normal VM user after `sudo -v`; sudo is used only for the network namespace."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]

def api(route,data=None):
    req=urllib.request.Request('http://127.0.0.1:8088/'+route,
        data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r: return json.load(r)

def make(job,dose,backdate=0):
    path=ROOT/'commands'/(str(uuid.uuid4())+'.json'); path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(dict(job_id=job,command_id=str(uuid.uuid4()),dose=dose,
                                   issued_at=time.time()-backdate)),encoding='utf-8')
    return path

def send(path):
    result=subprocess.run(['sudo','ip','netns','exec','gd-client',str(Path(sys.executable).absolute()),
        str(ROOT/'src/client.py'),'send','--file',str(path)],text=True,capture_output=True,timeout=50)
    print(result.stdout,flush=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout.strip().splitlines()[-1])['response']['decision']

def wait():
    deadline=time.monotonic()+18
    while time.monotonic()<deadline:
        s=api('state')
        if s['phase'] not in ('READY','DISPENSING'):
            print(json.dumps(s,indent=2),flush=True)
            return s
        time.sleep(.2)
    raise RuntimeError('Job did not terminate; inspect the lab terminal.')

p=argparse.ArgumentParser()
p.add_argument('scenario',choices=['baseline','replay','expired','freeze','delayed'])
a=p.parse_args()
tag=uuid.uuid4().hex[:8]
mode=api('state')['mode']
api('freeze',{'enabled':False})

if a.scenario=='replay':
    api('begin',{'job_id':'A-'+tag,'target':10})
    saved=make('A-'+tag,10)
    assert send(saved)=='staged','First job failed; check latency and max age.'
    assert wait()['verdict']=='PASS','Baseline job failed; fix it before the replay experiment.'
    api('begin',{'job_id':'B-'+tag,'target':6})
    decision=send(saved)
    if mode=='protected':
        assert decision=='wrong_job',decision
        assert send(make('B-'+tag,6))=='staged'
    else:
        assert decision=='staged',decision
    result=wait()
    assert result['verdict']==('PASS' if mode=='protected' else 'DEFECT'),result
    print('Replay comparison behaved as expected.')
else:
    job=a.scenario+'-'+tag
    api('begin',{'job_id':job,'target':6})
    if a.scenario=='freeze': api('freeze',{'enabled':True})
    decision=send(make(job,6,backdate=5 if a.scenario=='expired' else 0))
    result=wait()
    if a.scenario=='baseline':
        assert decision=='staged' and result['verdict']=='PASS',result
    elif a.scenario=='expired':
        assert decision==('expired' if mode=='protected' else 'staged'),decision
        assert result['verdict']==('ABORTED' if mode=='protected' else 'PASS'),result
    elif a.scenario=='freeze':
        assert result['verdict']=='PASS' and result['reported']==0,result
        print('Display remains frozen for your recording. Run control.py freeze off to restore it.')
    # delayed intentionally reports observed results without presuming retransmission timing.
