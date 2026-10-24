#!/system/bin/sh
# THRONE: keep ADB TCP on 5555 across reboots, surviving Tailscale handshake.
# Magisk post-fs-data.d runs after data partition mounts, before most user
# services. Tailscale's tunnel can take a few extra seconds to come up, so
# we re-confirm the listener until it's actually ready.
setprop persist.adb.tcp.port 5555
setprop service.adb.tcp.port 5555
stop adbd
start adbd
(
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    P=$(getprop service.adb.tcp.port)
    if [ "$P" = "5555" ] && pgrep -f adbd >/dev/null; then
      exit 0
    fi
    setprop service.adb.tcp.port 5555
    stop adbd
    start adbd
  done
) &
exit 0
