#!/usr/bin/env bash
set -euo pipefail
lab_root="$(cd "$(dirname "$0")/.." && pwd)"
ns3_root="${NS3_ROOT:-$HOME/ghost-dose-lab/ns-3.44}"
delay_ms="${1:-20}"
loss="${2:-0}"
run="${3:-1}"
label="${4:-network}"
[[ "$label" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Use a simple alphanumeric capture label'; exit 1; }
bin="$(find "$ns3_root/build/scratch" -maxdepth 1 -type f -name '*ghost-dose*' -executable -print -quit)"
[[ -n "$bin" ]] || { echo 'Build scratch/ghost-dose.cc in NS-3 first'; exit 1; }
mkdir -p "$lab_root/results/captures"
prefix="$lab_root/results/captures/${label}-$(date +%Y%m%d-%H%M%S)"
cd "$ns3_root"
echo "NS-3 delay=${delay_ms}ms loss=${loss} run=${run} capture=${prefix}"
exec sudo env LD_LIBRARY_PATH="$ns3_root/build/lib" "$bin" \
  --delayMs="$delay_ms" --loss="$loss" --run="$run" --pcap="$prefix" --duration=3600
