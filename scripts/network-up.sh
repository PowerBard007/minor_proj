#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Use sudo bash scripts/network-up.sh'; exit 1; }
# Refuse to overwrite an existing lab or unrelated interface.
for n in gd-br-c gd-br-s gd-veth gd-tap-c gd-tap-s; do
  if ip link show "$n" >/dev/null 2>&1; then echo "$n already exists. Stop the lab and run network-down.sh first."; exit 1; fi
done
if ip netns list | awk '{print $1}' | grep -qx gd-client; then echo 'gd-client already exists'; exit 1; fi
ip netns add gd-client
ip link add gd-br-c type bridge
ip link add gd-br-s type bridge
ip link set gd-br-c type bridge stp_state 0 forward_delay 0
ip link set gd-br-s type bridge stp_state 0 forward_delay 0
ip link add gd-veth type veth peer name gd-eth
ip link set gd-eth netns gd-client
ip link set gd-veth master gd-br-c
ip tuntap add dev gd-tap-c mode tap
ip tuntap add dev gd-tap-s mode tap
ip link set gd-tap-c master gd-br-c
ip link set gd-tap-s master gd-br-s
for n in gd-br-c gd-br-s gd-veth gd-tap-c gd-tap-s; do ip link set "$n" up; done
ip addr add 10.42.0.2/24 dev gd-br-s
ip -n gd-client link set lo up
ip -n gd-client link set gd-eth up
ip -n gd-client addr add 10.42.0.1/24 dev gd-eth
# Docker can set FORWARD to DROP. Permit only traffic within this lab bridge.
iptables -I FORWARD 1 -i gd-br-c -o gd-br-c -j ACCEPT
echo 'Created client 10.42.0.1 and server 10.42.0.2. No default route is added to the client.'
echo 'They can communicate only when the NS-3 process is running.'
