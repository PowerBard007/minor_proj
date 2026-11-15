# Ghost Dose: complete build and demonstration guide

Prepared 13 November 2026. All source files referenced here are included.

**Question:** Can a successfully delivered industrial command still be wrong because it belongs to another product or arrives too late?

**Build:** real CoAP communication through an NS-3 simulated network; an OpenPLC software controller; a simulated glue dispenser; deliberate stale-command and display faults; and a comparison with application validation enabled.

**Validation status:** Python syntax and nine policy unit tests were checked during preparation. The complete Linux/NS-3/OpenPLC integration has NOT been executed in the authoring environment. Follow the acceptance checkpoints below on your VM. Expected results are predictions, not measured findings.

## 1. Architecture and scope

| Component | Implementation | Responsibility |
|---|---|---|
| Recipe sender | Python using aiocoap | Send real CoAP POST requests |
| Network | NS-3 real-time CSMA topology | Carry real frames with simulated delay and receive errors |
| Gateway | Python CoAP server | Validate recipes and write Modbus registers |
| PLC | OpenPLC runtime executing Structured Text | Decide when the valve opens and closes |
| Factory process | Python mathematical model | Integrate adhesive dose from valve output |
| Dashboard | Local web page | Show actual and reported process values |

```text
Ubuntu VM
 client namespace                         normal VM namespace
 CoAP client 10.42.0.1                     CoAP gateway 10.42.0.2
       | veth                                       |
 Linux bridge gd-br-c                       Linux bridge gd-br-s
       | TAP gd-tap-c                                | TAP gd-tap-s
       +---------- NS-3 simulated CSMA link --------+
                                                    |
                                           localhost:1502 Modbus
                                                    |
                                             OpenPLC in Docker
                                                    |
                                         valve output / measured dose
                                                    |
                                          Python virtual dispenser
                                                    |
                                          localhost:8088 dashboard
```

This is **NS-3 network emulation with a software PLC and a simulated process**. CoAP executes in real external endpoints, not as a native application module inside NS-3. If your instructor requires an in-process NS-3 CoAP module specifically, confirm whether this architecture meets that requirement before the full build. The provided assignment wording does not resolve that distinction.

The conveyor is represented by starting a job; no conveyor mechanics are simulated. Modbus is the internal PLC interface; CoAP is your selected non-MQTT M2M protocol. No physical equipment is needed.

The two Linux bridges are separate. Stopping NS-3 must break communication between client and gateway. This is your evidence that the packets really cross the simulation.

## 2. The experiment

Job A requires **10 adhesive units**. Job B requires **6**. These are arbitrary educational units.

1. Execute A normally and retain its recipe payload.
2. Start B with an independent reference target of 6.
3. Send the saved A payload as a new CoAP exchange.
4. The weak gateway ignores the job mismatch and forwards a 10-unit recipe.
5. The PLC correctly executes the wrong recipe, making B defective.
6. The protected gateway rejects the mismatch; a fresh B recipe then produces approximately 6.

The reference target is set locally by the experiment operator. It is deliberately independent of the network recipe, so an attacker cannot redefine the expected outcome simply by changing the command.

This is **application replay**, not ordinary CoAP retransmission. CoAP has message duplicate handling. A new request containing old production instructions is a different problem.

Both modes retain PLC time and quantity limits. Those constrain runaway operation but cannot tell whether a 10-unit recipe belongs to A or B. Equipment limits and product correctness are separate concerns.

## 3. Prepare Ubuntu and Python

Use an **Ubuntu 24.04 desktop VM** with sudo access. Suggested allocation: 4 CPU cores, 6–8 GB RAM and 30 GB free disk, if your laptop can spare them. These are planning estimates. Use NAT for downloads. The lab client has no default route; PLC web/Modbus ports are published only on VM loopback.

**All commands below run in the Ubuntu terminal, not Windows PowerShell.** Copy the supplied ZIP into the VM's Downloads directory.

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git python3 python3-venv \
  python3-pip pkg-config iproute2 iptables iputils-ping tcpdump unzip docker.io
sudo systemctl enable --now docker
mkdir -p "$HOME/ghost-dose-lab"
unzip "$HOME/Downloads/ghost-dose.zip" -d "$HOME/ghost-dose-lab"
cd "$HOME/ghost-dose-lab/ghost-dose"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p results commands
.venv/bin/python -m pip freeze > results/python-versions.txt
.venv/bin/python -m unittest discover -s tests -v
```

The ZIP contains a top-level `ghost-dose` folder. If you copy the unzipped folder instead, place it at `$HOME/ghost-dose-lab/ghost-dose`.

**Checkpoint:** nine policy tests pass. These do not verify the full integration.

Dependencies are pinned. In particular, PyModbus 3.6.9 uses `slave=1`; do not combine newer client API examples with this version. The code targets Python 3.12 in Ubuntu 24.04.

## 4. Build NS-3 3.44

```bash
cd "$HOME/ghost-dose-lab"
git clone --depth 1 --branch ns-3.44 https://gitlab.com/nsnam/ns-3-dev.git ns-3.44
cp ghost-dose/ns3/ghost-dose.cc ns-3.44/scratch/ghost-dose.cc
cd ns-3.44
./ns3 configure --enable-examples --enable-tests
./ns3 build
git rev-parse HEAD > ../ghost-dose/results/ns3-commit.txt
```

Build as your normal user. Launching the TAP experiment later needs sudo. Confirm configure includes `tap-bridge` and real-time support. The build can take several minutes.

The C++ file does the following:

- Uses `RealtimeSimulatorImpl` so external applications and network simulation progress together.
- Creates two CSMA devices on a 10 Mbps simulated channel.
- Sets one-way propagation delay through `delayMs`.
- Adds a packet-based receive error model to each device through `loss`.
- Attaches each device to an existing Linux TAP using `UseBridge`.
- Saves PCAP traffic captures.

The real Linux endpoints supply IP and UDP, so the ghost nodes need no NS-3 Internet stack. This is an Ethernet frame bridge. Large delays such as 1500 ms are stress conditions, not a realistic Ethernet cable model. Configured receive-error probability is not the same as measured application-message loss.

Source: [NS-3 installation](https://www.nsnam.org/docs/release/3.44/installation/html/quick-start.html), [TapBridge](https://www2.nsnam.org/docs/release/3.44/models/html/tap.html).

## 5. Build and start OpenPLC

This package deliberately targets **OpenPLC v3**, whose `%MW` Modbus mapping the scripts use. Its repository is now archived and marks v3 as end-of-life, replaced by v4. This is an isolated coursework compatibility choice. Do not silently substitute v4 without adapting and verifying the mapping. [Official repository and status](https://github.com/thiagoralves/OpenPLC_v3).

```bash
cd "$HOME/ghost-dose-lab"
git clone https://github.com/thiagoralves/OpenPLC_v3.git
cd OpenPLC_v3
git rev-parse HEAD > ../ghost-dose/results/openplc-commit.txt
sudo docker build -t ghost-dose-openplc:v3 .
sudo docker volume create ghost-dose-plc-data
sudo docker run -d --name ghost-dose-plc \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:1502:502 \
  -v ghost-dose-plc-data:/docker_persistent \
  ghost-dose-openplc:v3
sudo docker logs --tail 60 ghost-dose-plc
```

The upstream Dockerfile downloads its own dependencies and can take considerable time. Record the commit and save image information after a successful build. A recorded source revision alone does not freeze upstream package downloads.

No hardware passthrough is needed, so this command does not grant a privileged container. Host loopback port 1502 maps to Modbus port 502 inside the container.

In the **VM browser**, visit `http://127.0.0.1:8080`:

1. Sign in. An unmodified v3 first-run database normally uses `openplc` / `openplc`; use your existing account if already configured. Change the default afterward.
2. Stop the runtime before changing programs.
3. In **Hardware**, select **Blank**, because all process I/O is simulated.
4. In **Programs**, upload the supplied `plc/dispenser.st` and name it `Ghost Dose Dispenser`.
5. Wait for successful compilation. Do not proceed with compiler errors.
6. In **Settings**, enable the Modbus TCP server on **502** inside the container. Disable unused industrial protocol servers for the experiment.
7. Start the runtime and verify **Running**.

UI wording may vary by archived revision. Do not add the gateway as a remote slave: OpenPLC is the Modbus server and the gateway is its client.

Read the registers:

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
.venv/bin/python src/plc_io.py
```

Expected: a dictionary containing recipe, sequence, enable, measured, ack, valve, done and fault. A fresh program normally starts with zero values.

**Crucial mapping checkpoint:** a successful register read alone does not prove your PLC program is connected. Test its scan logic while dispensing is disabled:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import time
from plc_io import PLC
p = PLC()
p.write(2, [0])
p.write(1, [123])
time.sleep(0.2)
r = p.read()
print(r)
assert r[4] == 123, 'Ack did not follow Sequence. Check program, RUN state and mapping.'
assert r[5] == 0, 'Valve must be off with Enable=0.'
p.write(1, [0])
time.sleep(0.1)
p.close()
print('PLC mapping and scan checkpoint passed')
PY
```

## 6. Understand the controller and process

These are **zero-based holding-register addresses**, not 4xxxx display notation. In v3, `%MW0` maps to 1024.

| Variable | IEC address | Modbus address | Writer | Meaning |
|---|---|---:|---|---|
| Recipe | `%MW0` | 1024 | Gateway | Requested dose × 100 |
| Sequence | `%MW1` | 1025 | Gateway | New command sequence |
| Enable | `%MW2` | 1026 | Local process manager | Product present; 0 resets operation |
| Measured | `%MW3` | 1027 | Process model | Simulated dose × 100 |
| Ack | `%MW4` | 1028 | PLC | Last consumed sequence |
| Valve | `%MW5` | 1029 | PLC | 0 closed, 1 open |
| Done | `%MW6` | 1030 | PLC | Target reached |
| Fault | `%MW7` | 1031 | PLC | Time/quantity/recipe fault |

Mapping reference: [v3 Modbus implementation](https://github.com/thiagoralves/OpenPLC_v3/blob/master/webserver/core/modbus.cpp).

`dispenser.st` runs every 20 ms. Enable=0 closes the valve and clears the operation. A changed Sequence latches Recipe and updates Ack. The valve remains open until Measured reaches the latched target. A six-second watchdog and 11-unit quantity bound force a fault and close it.

Python polls about every 50 ms and integrates the previous observed valve output:

```text
new dose = old dose + 2 units/second × elapsed seconds × valve state
```

Thus 6 units take about 3 seconds and 10 about 5. Small overshoot comes from polling, PLC scan and scheduling. PASS is within 0.5 units of the local reference target; that is a teaching tolerance, not an industrial specification.

Python does not decide the valve state. It models the physical consequence of the PLC output. Jobs without an acceptable command abort after 12 seconds. Host polling gaps above 0.5 seconds produce `TIMING_ERROR`; discard those trials and fix VM load.

## 7. Create and verify the network

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
sudo bash scripts/network-up.sh
sudo ip netns exec gd-client ping -c 2 -W 1 10.42.0.2
```

Before NS-3 starts, ping should **fail**. The setup creates only named `gd-*` interfaces, the `gd-client` namespace and a forwarding rule limited to the client lab bridge. Docker can otherwise block bridged traffic through its default FORWARD policy.

Open **Terminal 1**, run this, and leave it running:

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
bash scripts/run-network.sh 20 0 1 low-delay
```

Arguments: 20 ms delay, zero receive-error probability, RNG run 1, capture label. The process has a one-hour limit. The launcher finds the built executable and sets its library path.

From another terminal:

```bash
sudo ip netns exec gd-client ping -c 4 -W 3 10.42.0.2
```

**Checkpoint:** ping succeeds, with RTT roughly twice propagation delay plus host overhead after ARP resolves. Stop Terminal 1 with Ctrl+C: ping should fail again. Restart Terminal 1 and confirm recovery. Do this before any production job and show it in your recording.

## 8. Run a normal job in weak mode

With NS-3 running, open **Terminal 2**:

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
.venv/bin/python src/lab.py --mode weak --out results/weak-01
```

Open `http://127.0.0.1:8088` in the VM browser. You should see actual/reported dose, job, phase, mode, valve and command decision.

In **Terminal 3**:

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
sudo -v
.venv/bin/python src/demo.py baseline
```

`sudo -v` handles permission prompting before timing-sensitive command creation. The demo runs as the normal user; it launches only the CoAP client inside the namespace using sudo.

Expected: `staged`, rising dose, valve closure near 6 units and PASS. `staged` means registers were written, not that dispensing is complete. PLC Ack/Done/Fault and the final dose provide execution evidence.

Every application run needs an unused output directory. If `weak-01` already exists, use `weak-02`; the program refuses to overwrite its CSV evidence.

## 9. Replay the previous product's recipe

```bash
.venv/bin/python src/demo.py replay
```

The script creates A with target10, saves/sends its command, waits for completion, creates B with target6, and sends the identical A payload in a new CoAP exchange.

Expected in weak mode: A passes; B receives around10 and is DEFECT. `commands.csv` shows the command's job A against the active job B.

The attacker is a lab-network client with an old payload and permission to submit requests to the intentionally weak endpoint. This is not an unknown CoAP/OpenPLC exploit. The weakness is deliberately missing application checks.

## 10. Enable validation and repeat

Wait for the job to finish. Stop Terminal 2 with Ctrl+C, then restart:

```bash
.venv/bin/python src/lab.py --mode protected --out results/protected-01
```

In Terminal 3:

```bash
sudo -v
.venv/bin/python src/demo.py baseline
.venv/bin/python src/demo.py replay
```

Expected: A's replay for B returns `wrong_job`. The demo sends a new valid B recipe and B passes near6.

Protected mode validates shape/range, READY phase, matching job, age ≤1 second, no timestamp more than0.1s in the future, and unused command ID. IDs are reserved in persistent `results/used.sqlite` before the Modbus side effect. A crash can lose an operation but should not allow reuse of a reserved ID. This is fail-closed reservation, **not a complete exactly-once protocol**. Retain that database between runs; demos generate unique IDs.

These controls are **not authentication or encryption**. A malicious client can invent a fresh ID/timestamp and guess the active job. Identity authentication, recipe authorization and protection against a compromised gateway remain future work. The two endpoints share a VM clock; separate hosts would need a clock/freshness design.

## 11. Test an expired command

```bash
.venv/bin/python src/demo.py expired
```

This deliberately backdates a command by five seconds. It tests application age, not network-induced delay.

- Weak: accepts it; the product can still PASS because the dose happens to match. Stale acceptance does not always create a defect.
- Protected: returns `expired`; no valve motion; job becomes ABORTED after its timeout. This preserves safety at a production-availability cost.

Run once in each mode. Do not report an aborted product as a successful manufactured product.

## 12. Test real NS-3 delay and random errors

Only change the network when no job is active. Stop Terminal 1 and restart:

```bash
bash scripts/run-network.sh 1500 0 1 high-delay
```

Warm up ARP, then create and send a fresh command:

```bash
sudo ip netns exec gd-client ping -c 2 -W 10 10.42.0.2
sudo -v
.venv/bin/python src/demo.py delayed
```

Protected mode should reject a fresh command that reaches it after the one-second age limit. Weak mode should accept if still READY. This scenario prints observed results without asserting exact timing, because queueing, retries, ARP and scheduling vary.

For random receive errors, stop Terminal 1 and restart:

```bash
bash scripts/run-network.sh 20 0.05 1 loss-run1
```

Use `src/demo.py delayed` again. Repeat RNG run numbers2–5 with fresh output directories. A request may be delivered, expire after retransmission, or time out. The package does not include a traffic-flooding generator; delay and random receive errors are the implemented impairments.

Suggested comparison matrix:

| Scenario | Modes | Delay ms | Error probability | Trials |
|---|---|---:|---:|---:|
| Baseline | Both | 20 | 0 | 5 each |
| Recipe replay | Both | 20 | 0 | 5 each |
| Network expiry | Both | 1500 | 0 | 5 each |
| Random errors | Both | 20 | 0.05 | 5 RNG runs each |

Fixed seeds control NS-3 random streams, not all real-host scheduling. Five trials demonstrate behaviour; they do not establish strong statistical conclusions.

## 13. Demonstrate a misleading operator display

Return NS-3 to20ms and zero loss. In either mode:

```bash
.venv/bin/python src/demo.py freeze
```

Actual dose rises to around6; reported dose stays at0. PLC feedback still uses actual modeled dose, so the product itself can pass.

Restore reporting:

```bash
.venv/bin/python src/control.py freeze off
```

This is an explicit local display-compromise fault switch. It is not an exploited dashboard vulnerability, implemented network MITM, or falsified PLC sensor input. Describe exactly that scope in the video.

## 14. Manual commands and payload

The automated helper avoids typing delays. To explain the underlying commands, run these with no active job:

```bash
.venv/bin/python src/control.py begin --job manual-A --target 10
.venv/bin/python src/client.py make --job manual-A --dose 10 --file commands/manual-A.json
sudo ip netns exec gd-client "$PWD/.venv/bin/python" \
  "$PWD/src/client.py" send --file "$PWD/commands/manual-A.json"
.venv/bin/python src/control.py state
```

In protected mode paste make/send together immediately: waiting more than a second intentionally causes expiry. The files contain `job_id`, a generated `command_id`, numeric `dose`, and Unix `issued_at` timestamp. Do not reuse hand-written example timestamps.

After A completes, replay into B in weak mode:

```bash
.venv/bin/python src/control.py begin --job manual-B --target 6
sudo ip netns exec gd-client "$PWD/.venv/bin/python" \
  "$PWD/src/client.py" send --file "$PWD/commands/manual-A.json"
```

## 15. Inspect and plot your measured evidence

Each run produces:

- `telemetry.csv`: actual/reported dose, target, valve, Ack, fault and phase over time.
- `commands.csv`: command age, active/command job IDs and decision.
- `jobs.csv`: final dose, signed error and verdict.

NS-3 PCAP files are in `results/captures`, named using the label and timestamp. They may be root-owned because NS-3 runs with TAP permissions.

After stopping the relevant application run:

```bash
.venv/bin/python src/plot.py results/weak-01
.venv/bin/python src/plot.py results/protected-01
```

Open each generated `plot.png`. Upper panel: actual, reported and reference dose. Lower panel: PLC valve. The command also prints final job rows.

Optionally install Wireshark, open a PCAP as your normal user and filter:

```bash
sudo apt install -y wireshark
```

```text
coap || udp.port == 5683
```

Inspect POST `/recipe`, JSON payload, confirmable message type, token/message ID, response and any retransmission. A sender capture includes frames that may later be lost: use receiver evidence and gateway logs to establish delivery.

Report:

```text
signed dose error = actual − target
absolute dose error = |actual − target|
command age = gateway receipt time − issued_at
defect rate among completed products = DEFECT / (PASS + DEFECT)
abort rate = ABORTED / attempted jobs
```

List faults and timing errors separately. Include aborted jobs in availability discussion. CoAP RTT, one-way command age and dispensing completion time are different measurements.

## 16. Threat model

Assets: correct dose, PLC program integrity, freshness, availability, operator visibility, logs and engineering credentials. Boundaries: client→gateway, gateway→PLC, process feedback→PLC, engineering access, dashboard and build dependencies.

| Threat | Prerequisite / impact | Demonstrated control or limitation |
|---|---|---|
| Wrong-job replay | Saved payload → incorrect product dose | Implemented job validation comparison |
| Expired commands | Old/delayed request → stale action | Implemented age checks |
| Reused command IDs | Repeat ID → repeated processing | Persistent reservation; unit test |
| Forged fresh requests | Unauthenticated sender → unauthorized recipe | Not solved; needs identity and recipe authorization |
| Compromised gateway | Code execution → arbitrary permitted Modbus commands | Not solved; PLC limits only constrain some outcomes |
| Direct Modbus manipulation | Internal interface access → control/feedback changes | Loopback reduces exposure; no Modbus authentication implemented |
| PLC logic replacement | Engineering account compromise → changed control | Threat-model only, with optional controlled extension below |
| False process feedback | Sensor/model compromise → wrong PLC decisions | Not solved; independent checks would be needed |
| Frozen display | Presentation compromise → misleading operator view | Implemented local fault switch |
| Flooding | Reachable endpoint → service exhaustion | Not implemented; discuss rate limits/resource bounds |
| Network loss/outage | Fault/interference → missed deadlines | Random errors and job timeout implemented |
| Clock manipulation | Clock influence → invalid freshness decisions | Not solved; same-VM clock is a lab assumption |
| Gateway crash/restart | Interrupted control → uncertain action | Reservation and PLC watchdog; no atomic end-to-end transaction |
| Replay-state rollback | File access → old IDs become reusable | Not solved; protect persistent state |
| Log tampering | Host access → false evidence | Export/hash evidence; trusted logging remains future work |
| Dependency compromise | Malicious package/build → trusted component compromised | Record revisions and isolate the lab |

Connect the project to the general industrial-security concern of altered control behaviour and misleading observations. Do not call it a reproduction of Stuxnet.

Optional PLC modification extension: copy `plc/dispenser.st` to `plc/dispenser_modified.st`. In that copy, change `Target := Recipe;` to `Target := 1000;`. Upload it through your own engineering interface and run a normal6-unit baseline. It should dispense around10 within existing interlocks; the helper's PASS assertion should fail, which is expected evidence. Restore the original program afterward. This models an already-compromised engineering path, not gaining that access. Keep its results separate from gateway replay.

## 17. Satisfy the protocol-exploration part

Include a brief table comparing MQTT's broker-based publish/subscribe model, CoAP's resource-oriented request/response model and AMQP messaging. State that MQTT is excluded from your implementation by the assignment and CoAP is selected. Explain which actual integration routes you investigated.

List the NS-3 modules actually used: core, network, csma and tap-bridge. Network simulation support does not mean every application protocol ships as a native module. The third-party `maesoser/ns3-coap` repository describes a partial implementation; this project instead runs real CoAP endpoints through NS-3. Do not claim a native AMQP module exists merely because a project-ideas page mentions it.

## 18. Record the walkthrough

Use your screen recorder and microphone. Make the terminals readable. Target7–9minutes:

| Time | Show and explain |
|---|---|
| 0:00–0:45 | Objective, architecture, real versus simulated components |
| 0:45–1:30 | NS-3 setup and stopping/restarting it to prove the path |
| 1:30–2:15 | PLC program, register mapping and local limits |
| 2:15–3:15 | Baseline recipe, valve and correct final dose |
| 3:15–4:30 | Weak replay: A's payload produces a defect in B |
| 4:30–5:45 | Protected replay rejection and valid B command |
| 5:45–6:45 | Delay or frozen-display experiment |
| 6:45–8:00 | Plots, threat model, safety/availability trade-off and limitations |
| End | Supporting files and reproduction guide |

Main narration: “The network delivers the command successfully and the PLC executes it correctly, but it belongs to an earlier product. The protected gateway checks job identity and freshness before passing it to the controller.”

## 19. Troubleshoot by layer

| Symptom | Check |
|---|---|
| Existing network interfaces | Stop processes; run network-down then network-up |
| Ping works without NS-3 | Unintended bypass: inspect bridges/routes before continuing |
| Ping fails with NS-3 | Both TAP names, live simulator, bridge links and lab FORWARD rule |
| TAP open/helper error | Use launcher with sudo; ensure tap-bridge was built |
| Shell script permission error | Invoke `bash scripts/...`; executable permission is unnecessary |
| `^M` shell error | Run `sed -i 's/\r$//' scripts/*.sh` after Windows transfer |
| Modbus refused | Container, RUN state, internal502 enabled, host1502 publication |
| Read works but Ack unchanged | Correct ST program, v3 mapping, active PLC scans |
| `slave` keyword error | Install pinned PyModbus3.6.9 |
| Cannot bind10.42.0.2 | Run network-up and check gd-br-s address |
| CoAP timeout | Ping, gateway terminal and PCAP before changing code |
| Baseline expires | Low delay, sudo-v before trial, automated demo, no manual pause |
| TIMING_ERROR | VM/host overloaded or paused; discard trial and rerun |
| PLC watchdog on normal target | Verify scan/poll timing; target10 should finish near5s |
| Output files already exist | Choose an unused output directory |
| Port8088 in use | Stop old lab.py before starting the other mode |
| OpenPLC image build failure | Save build log; archived upstream dependencies may need repair; do not switch mappings silently |

Useful commands:

```bash
ip -br link
ip addr show gd-br-s
sudo ip netns exec gd-client ip addr
sudo iptables -S FORWARD
sudo docker ps --filter name=ghost-dose-plc
sudo docker logs --tail 80 ghost-dose-plc
sudo ss -lunp | grep 5683
sudo tcpdump -ni gd-br-s udp port 5683
```

## 20. Stop and submit

Wait for completion. Stop lab.py with Ctrl+C (it requests Enable=0), then stop NS-3. Run:

```bash
cd "$HOME/ghost-dose-lab/ghost-dose"
sudo docker stop ghost-dose-plc
sudo bash scripts/network-down.sh
sudo docker image inspect ghost-dose-openplc:v3 > results/openplc-image.json
sha256sum plc/dispenser.st ns3/ghost-dose.cc src/*.py > results/source-sha256.txt
```

The Docker container and volume remain. Next session use `sudo docker start ghost-dose-plc`, recreate the lab network and restart NS-3/application. Do not repeat docker-run with the same container name.

After placing your recording and report in the project folder:

```bash
cd "$HOME/ghost-dose-lab"
tar --exclude='ghost-dose/.venv' --exclude='*/__pycache__' \
  -czf ghost-dose-submission.tar.gz ghost-dose
```

Submit sources, guide, versions/commits, actual CSV/PCAP files, plots, report and narrated video. Exclude the virtual environment. For offline reproduction, optionally save the working Docker image separately.

Report order: objective; architecture; protocol exploration; plant/PLC assumptions; threat model; experiments; measured results; limitations; conclusion.

## References

- [NS-3 installation](https://www.nsnam.org/docs/release/3.44/installation/html/quick-start.html)
- [NS-3 TapBridge](https://www2.nsnam.org/docs/release/3.44/models/html/tap.html)
- [CSMA error-model implementation](https://github.com/nsnam/ns-3-dev-git/blob/ns-3.44/src/csma/model/csma-net-device.cc)
- [CoAP RFC7252](https://www.rfc-editor.org/rfc/rfc7252/)
- [aiocoap examples](https://aiocoap.readthedocs.io/en/latest/examples.html)
- [PyModbus3.6.9 interface](https://pymodbus.readthedocs.io/en/v3.6.9/source/client.html)
- [OpenPLC v3 repository](https://github.com/thiagoralves/OpenPLC_v3)
- [OpenPLC v3 Modbus mapping](https://github.com/thiagoralves/OpenPLC_v3/blob/master/webserver/core/modbus.cpp)
- [Third-party partial CoAP module](https://github.com/maesoser/ns3-coap)
- [Assignment's project ideas](https://ns3simulation.com/m2m-communication-projects-examples-using-ns3/)

Use primary sources to support technical claims; the project-ideas page is inspiration, not proof of module availability or compatibility.
