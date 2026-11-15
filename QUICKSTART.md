# Terminal checklist — use after completing README setup

Run inside the Ubuntu VM. The complete installation and explanation are in README.md.

## Start the infrastructure

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
sudo docker start ghost-dose-plc
sudo bash scripts/network-up.sh
```

If the container or interfaces are already running, do not repeat their creation. Verify OpenPLC is RUNNING with the supplied program.

## Terminal 1 — simulated network (leave open)

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
bash scripts/run-network.sh 20 0 1 demo
```

## Terminal 2 — gateway and process (leave open)

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
.venv/bin/python src/lab.py --mode weak --out results/weak-video-01
```

Use a fresh output directory each time. Open `http://127.0.0.1:8088` in the VM browser.

## Terminal 3 — experiments

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
sudo -v
sudo ip netns exec gd-client ping -c 3 10.42.0.2
.venv/bin/python src/demo.py baseline
.venv/bin/python src/demo.py replay
.venv/bin/python src/demo.py expired
.venv/bin/python src/demo.py freeze
.venv/bin/python src/control.py freeze off
```

Wait for each command to finish. Expected weak replay result: job B receives about 10 against its target of 6, producing DEFECT.

## Compare protected mode

Stop Terminal 2 with Ctrl+C, then run there:

```bash
.venv/bin/python src/lab.py --mode protected --out results/protected-video-01
```

In Terminal 3:

```bash
sudo -v
.venv/bin/python src/demo.py baseline
.venv/bin/python src/demo.py replay
.venv/bin/python src/demo.py expired
```

Expected: replay rejected as wrong_job, valid replacement recipe passes; expired command rejected and job eventually ABORTED.

## Plot after stopping Terminal 2

```bash
.venv/bin/python src/plot.py results/weak-video-01
.venv/bin/python src/plot.py results/protected-video-01
```

## Shutdown

Stop Terminal 2, then Terminal 1, with Ctrl+C. In Terminal 3:

```bash
sudo docker stop ghost-dose-plc
sudo bash scripts/network-down.sh
```

Do not call this complete until your VM passes the README's NS-3 path test, PLC acknowledgement test and baseline/replay demonstrations.
