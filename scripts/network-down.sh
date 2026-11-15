#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Use sudo bash scripts/network-down.sh'; exit 1; }
# Delete only the explicitly named lab interfaces. Stop lab processes first.
iptables -D FORWARD -i gd-br-c -o gd-br-c -j ACCEPT 2>/dev/null || true
ip netns del gd-client 2>/dev/null || true
for n in gd-veth gd-tap-c gd-tap-s gd-br-c gd-br-s; do ip link del "$n" 2>/dev/null || true; done
