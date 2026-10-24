#!/usr/bin/env bash
# SSH to Cyclone_C4 via Tailscale
S="100.71.239.65"
P=8022
U="u0_a147"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p $P $U@$S "$@"
