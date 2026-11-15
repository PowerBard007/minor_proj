import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser(); p.add_argument('run',type=Path); a=p.parse_args()
with (a.run/'telemetry.csv').open() as f: rows=list(csv.DictReader(f))
if not rows: raise SystemExit('No telemetry rows')
t0=float(rows[0]['wall_time']); t=[float(r['wall_time'])-t0 for r in rows]
fig, ax=plt.subplots(2,1,figsize=(11,7),sharex=True,layout='constrained')
for key,label in [('actual','Actual dose'),('reported','Reported dose'),('target','Reference target')]:
    ax[0].plot(t,[float(r[key]) for r in rows],label=label,linestyle='--' if key!='actual' else '-')
ax[0].set_ylabel('Adhesive units'); ax[0].legend(); ax[0].grid(alpha=.2)
ax[1].step(t,[int(r['valve']) for r in rows],where='post',label='PLC valve output')
ax[1].set(xlabel='Seconds from log start',ylabel='Valve (0 / 1)',yticks=[0,1]); ax[1].grid(alpha=.2)
fig.suptitle('Ghost Dose — '+a.run.name)
path=a.run/'plot.png'; fig.savefig(path,dpi=160); print(path)
with (a.run/'jobs.csv').open() as f:
    for r in csv.DictReader(f): print(r)
