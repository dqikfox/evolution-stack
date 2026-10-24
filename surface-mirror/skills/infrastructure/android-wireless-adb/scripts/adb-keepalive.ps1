# Hermes Wireless ADB Keepalive (Android 14+)
# Maintains a persistent wireless ADB connection. Google's adbd drops idle TCP
# sessions after ~5 minutes; this script pings the device every 30s to keep
# the connection warm and auto-reconnects if it drops.
#
# Usage:
#   1. Edit $DeviceTarget below to your phone's routable IP:port
#   2. powershell -ExecutionPolicy Bypass -File adb-keepalive.ps1
#   3. Ctrl+C to stop
#
# To find $DeviceTarget:
#   adb -s <usb-serial> shell "ip -4 addr show wlan0 | grep -oE 'inet [0-9.]+'"
#   or use Tailscale: "C:/Program Files/Tailscale/tailscale.exe" status --json
#   Then pair via Settings > Developer Options > Wireless debugging.

$ErrorActionPreference = 'Stop'
$DeviceTarget = '100.120.82.1:38515'
$PingIntervalSec = 30
$MaxReconnectAttempts = 3

function Log([string]$msg) {
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$ts] $msg"
}

function Test-AdbConnection {
    try {
        $out = & adb -s $DeviceTarget shell echo ping 2>&1
        return ($LASTEXITCODE -eq 0) -and ($out -match 'ping')
    } catch {
        return $false
    }
}

function Connect-Device {
    for ($i = 1; $i -le $MaxReconnectAttempts; $i++) {
        Log "connect attempt $i/$MaxReconnectAttempts ..."
        $out = & adb connect $DeviceTarget 2>&1
        Log "  $out"
        if ($out -match 'connected to') {
            Start-Sleep -Seconds 2
            if (Test-AdbConnection) { return $true }
        }
    }
    return $false
}

Log "adb-keepalive started; target=$DeviceTarget ping=$PingIntervalSec s"
Log "  PID: $PID   (Ctrl+C to stop)"

while ($true) {
    if (-not (Test-AdbConnection)) {
        Log "connection lost - reconnecting"
        if (-not (Connect-Device)) {
            Log "reconnect failed, will retry in $PingIntervalSec s"
        } else {
            Log "connection restored"
        }
    } else {
        Log "ping OK"
    }
    Start-Sleep -Seconds $PingIntervalSec
}
