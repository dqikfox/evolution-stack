#!/usr/bin/env bash
# Cyclone_C4 control helpers (THRONE)
set -e
LAN=192.168.4.242
TS=100.71.239.65
PORT=5555
pick() {
  if adb connect "$TS:$PORT" >/dev/null 2>&1; then echo "$TS:$PORT"; return; fi
  if adb connect "$LAN:$PORT" >/dev/null 2>&1; then echo "$LAN:$PORT"; return; fi
  echo "0123456789ABCDEF"
}
S=$(pick)
cmd=${1:-shell}
shift || true
case "$cmd" in
  devices) adb devices -l ;;
  shell) adb -s "$S" shell "$@" ;;
  scrcpy) scrcpy -s "$S" "$@" ;;
  home) adb -s "$S" shell input keyevent KEYCODE_HOME ;;
  unlock) adb -s "$S" shell input keyevent KEYCODE_WAKEUP; adb -s "$S" shell wm dismiss-keyguard ;;
  ts-status) adb -s "$S" shell dumpsys connectivity | head -5; adb -s "$S" shell ip -4 addr show tun0 ;;
  *) adb -s "$S" "$cmd" "$@" ;;
esac
