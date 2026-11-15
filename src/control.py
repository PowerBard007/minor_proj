"""Local operator interface. Not reachable from the CoAP client namespace."""
import argparse
import json
import urllib.request

p = argparse.ArgumentParser()
s = p.add_subparsers(dest='action', required=True)
b = s.add_parser('begin'); b.add_argument('--job', required=True); b.add_argument('--target', type=float, required=True)
s.add_parser('state')
f = s.add_parser('freeze'); f.add_argument('value', choices=['on', 'off'])
a = p.parse_args()
data = None
if a.action == 'begin': data = {'job_id': a.job, 'target': a.target}
if a.action == 'freeze': data = {'enabled': a.value == 'on'}
r = urllib.request.Request('http://127.0.0.1:8088/' + a.action,
    data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(r, timeout=5) as response:
        print(json.dumps(json.load(response), indent=2))
except urllib.error.HTTPError as exc:
    raise SystemExit(exc.read().decode())
