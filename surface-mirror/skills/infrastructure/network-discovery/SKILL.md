---
name: network-discovery
description: Use for investigating unreachable subnet hosts.
---
# Network Discovery & Reconnaissance

## Overview
This skill provides a workflow for identifying "ghost" infrastructure—devices like 'Mercury' that exist on the LAN but remain invisible to Tailscale or primary management nodes due to L3 isolation.

## Workflow
1. **Trace Intent**: Search the local codebase (`search_files`) for any IP addresses or hostnames found in `core/config.py` or similar files. If an IP is documented but unpingable, do not assume it is dead; assume it is logically isolated.
2. **Audit Routing Tables**: Run `route print` and `netstat -r` on all active interfaces. Look for any route entries pointing toward the target subnet (e.g., `192.168.4.0`).
3. **Inspect ARP Cache**: Execute `arp -a`. This is critical. Even if a node is unreachable via Tailscale, its MAC address may still be present in your hardware's ARP table if a bridge/gateway has communicated with it recently. 
    - *Goal*: Find an entry that bridges your current interface to the target subnet.
4. **Identify the Pivot**: If you find a device with a dual-homed IP (one in `.56.` and one in the unknown range), focus all subsequent reconnaissance on that host via SSH. It is your "Bridge."
5. **Verify Presence**: Use `nmap -sn <target_subnet>` from suspected pivot nodes to confirm life without triggering heavy alerts.

## Pitfalls
- **The Zombie Node**: A node may appear active in Tailscale's control plane (`tailscale status`) but be completely unreachable on the data plane due to firewall/L3 isolation. Always verify physical connectivity, not just registry presence.
- **False Negatives**: Do not conclude a device is "dead" simply because `ping` fails; if it appears in code, there *is* a path—you just haven't found the mediator yet.

## References
- `references/network_investigation_log.md`: Traces of recent investigations into disconnected subnet nodes (e.g., Mercury).