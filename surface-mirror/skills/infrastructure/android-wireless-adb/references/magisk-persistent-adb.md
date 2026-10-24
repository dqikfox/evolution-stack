# Magisk-rooted persistent wireless ADB (Android 10 / pre-wireless-debug era)

If the phone is rooted with Magisk, the wireless-debugging pair flow from SKILL.md is unnecessary. A single init script makes `adbd` listen on `service.adb.tcp.port=5555` after every boot — no 5-min idle disconnect, no `Settings → Wireless debugging` dance, no pairing window.

## When this applies (vs the SKILL.md stock flow)

- Stock Android 14+ (wireless debugging toggle exists) → use SKILL.md.
- Magisk-rooted Android 10 / 11 / 12 → use this reference.
- Cyclone_C4 (Android 10, Magisk) is the canonical case this was built against.

## Procedure

### 1. Compose the init script

Write to `%LOCALAPPDATA%/hermes/scripts/adb_tcp.sh` on the host, then push. The script sets both persistent and runtime props, restarts adbd, and runs a 10×2-second background retry loop so the listener survives the Tailscale tunnel handshake.

```sh
#!/system/bin/sh
setprop persist.adb.tcp.port 5555
setprop service.adb.tcp.port 5555
stop adbd
start adbd
(
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    P=$(getprop service.adb.tcp.port)
    if [ "$P" = "5555" ] && pgrep -f adbd >/dev/null; then exit 0; fi
    setprop service.adb.tcp.port 5555
    stop adbd
    start adbd
  done
) &
exit 0
```

### 2. Push and install

**Never try to write `/data/adb/post-fs-data.d/...` directly through `adb shell` heredocs** — MSYS quoting mangles the EOF and you get `Permission denied` or `no closing quote`. The reliable pattern is: `adb push` to `/sdcard/` then `su -c 'cp /sdcard/foo /target && chmod && chown'`.

```bash
adb -s <phone-ip>:<port> push adb_tcp.sh /sdcard/adb_tcp.sh
adb -s <phone-ip>:<port> shell "su -c 'cp /sdcard/adb_tcp.sh /data/adb/post-fs-data.d/adb_tcp.sh && chmod 755 /data/adb/post-fs-data.d/adb_tcp.sh && chown root:root /data/adb/post-fs-data.d/adb_tcp.sh && rm /sdcard/adb_tcp.sh'"
```

### 3. Verify on the phone

```bash
adb -s <phone-ip>:<port> shell "su -c 'md5sum /data/adb/post-fs-data.d/adb_tcp.sh'"
adb -s <phone-ip>:<port> shell "getprop service.adb.tcp.port"   # → 5555
adb -s <phone-ip>:<port> shell "getprop persist.adb.tcp.port"  # → 5555
```

### 4. Reboot and prove the post-boot path

```bash
adb -s <phone-ip>:<port> reboot
# wait ~30s, then:
adb disconnect <phone-ip>:<port> 2>/dev/null
adb connect <phone-ip>:<port>
adb -s <phone-ip>:<port> shell echo PERSISTED
```

The Magisk script fires from `post-fs-data.d/` (after data partition mounts, before most user services), so adbd restarts immediately. But Tailscale Android takes longer — see the gotcha below.

## Post-reboot gotcha: Tailscale tunnel may not auto-come-up

The Magisk script handles ADB. **The Tailscale Android app is gated on the user session** — `tun0` will not exist after an `adb reboot` until the app is foregrounded. `am start-service` from `adb shell` fails with "app is in background uid null" because Android 10+ stops background services from being cold-started by the shell.

Fix: launch the app via `monkey`, then poll for the tunnel.

```bash
adb -s <phone-ip>:<port> shell "monkey -p com.tailscale.ipn -c android.intent.category.LAUNCHER 1" >/dev/null
for i in 1 2 3 4 5 6 7 8; do
  sleep 4
  if adb -s <phone-ip>:<port> shell "ip -4 addr show tun0" 2>/dev/null | grep -q 'inet '; then
    echo "tun0 up after $((i*4))s"
    break
  fi
done
```

After `tun0` is up the tailnet IP responds and `adb connect <phone-tailnet-ip>:5555` works again. Load average spikes during boot (Magisk retry loop + Tailscale handshake) — normal, settles within ~5 minutes.

## LAN fallback helper

When the tailnet path is broken but the phone is on the same `192.168.4.x` subnet, fall back to LAN ADB without any reboot dance:

```bash
adb connect <phone-lan-ip>:5555
```

For Cyclone_C4 specifically, the helper `%LOCALAPPDATA%/hermes/scripts/phone_cyclone_adb.sh` picks Tailscale first, falls back to LAN, then USB serial — one entry point for any transport.

## Why Magisk `post-fs-data.d/` and not `service.d/`

Magisk has two init hook directories: `post-fs-data.d/` (after data partition mounts, before `adbd` starts) and `service.d/` (after `adbd` is up). For setting `service.adb.tcp.port` and restarting adbd you want `post-fs-data.d/` — running it from `service.d/` would race with the system adbd lifecycle and leave the listener in an inconsistent state.
