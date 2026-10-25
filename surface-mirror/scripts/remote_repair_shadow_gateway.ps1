# Repair the SHADOW remote Hermes gateway.
#
# State found on 2026-10-25: FOUR gateway processes alive (two instances:
# a venv python parent + its uv cpython child each), the platform port
# :8644 not bound, and gateway_state.json pointing at a pid that is long
# dead. The agent session that was using it finished at 03:30 and left
# the processes orphaned.
#
# Rules honoured here:
#   - stop the PARENT before the child, or the child is reparented and
#     the kill lands on the wrong thing
#   - kill by PID, never by a name pattern
#   - one instance after the repair, and the port proves it
$ErrorActionPreference = 'SilentlyContinue'
$h = Join-Path $env:LOCALAPPDATA "hermes"
$py = Join-Path $h "hermes-agent\venv\Scripts\python.exe"

"=== BEFORE ==="
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'hermes_cli\.main gateway' })
"gateway processes: " + $procs.Count
foreach ($p in $procs) { "  pid=" + $p.ProcessId + " ppid=" + $p.ParentProcessId }
$c = Get-NetTCPConnection -State Listen -LocalPort 8644 -ErrorAction SilentlyContinue
"port 8644 bound: " + [bool]$c

if ($procs.Count -gt 0) {
  "=== STOPPING THE ORPHANS (parents first) ==="
  $parents = $procs | Where-Object { $_.ParentProcessId -notin $procs.ProcessId }
  $children = $procs | Where-Object { $_.ParentProcessId -in $procs.ProcessId }
  foreach ($p in $parents) { "  stopping parent pid=" + $p.ProcessId; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 2
  foreach ($p in $children) { "  stopping child pid=" + $p.ProcessId; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 3
}
$left = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'hermes_cli\.main gateway' })
"remaining gateway processes: " + $left.Count

"=== STARTING ONE ==="
$stdout = Join-Path $h "logs\gateway_remote_stdout.log"
$stderr = Join-Path $h "logs\gateway_remote_stdout.log.err"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $py
$psi.Arguments = "-m hermes_cli.main gateway run"
$psi.WorkingDirectory = (Split-Path $py)
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
$psi.EnvironmentVariables["PYTHONUTF8"] = "1"
$proc = [System.Diagnostics.Process]::Start($psi)
"started pid=" + $proc.Id

# Drain the streams to files, so a full pipe buffer cannot wedge the
# gateway. A child that fills its stdout pipe and blocks is a child
# that looks alive and is not.
$outTask = $proc.StandardOutput.ReadToEndAsync()
$errTask = $proc.StandardError.ReadToEndAsync()
$proc.EnableRaisingEvents = $true
Register-ObjectEvent -InputObject $proc -EventName Exited -Action {
  $p = $Event.Sender
  Set-Content -Path (Join-Path $env:LOCALAPPDATA "hermes\logs\gateway_remote_stdout.log") -Value $p.StandardOutput.ReadToEnd() -Encoding UTF8
  Set-Content -Path (Join-Path $env:LOCALAPPDATA "hermes\logs\gateway_remote_stdout.log.err") -Value $p.StandardError.ReadToEnd() -Encoding UTF8
} | Out-Null

Start-Sleep -Seconds 25
"=== AFTER ==="
$now = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'hermes_cli\.main gateway' })
"gateway processes: " + $now.Count
foreach ($p in $now) { "  pid=" + $p.ProcessId + " ppid=" + $p.ParentProcessId }
foreach ($port in @(8644, 18789)) {
  $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  "port $port bound: " + [bool]$conn
}
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8644/health" -TimeoutSec 8 -UseBasicParsing
  "health: HTTP " + [int]$r.StatusCode + "  " + ($r.Content -replace '\s+',' ')
} catch { "health: " + $_.Exception.Message.Substring(0, [Math]::Min(80, $_.Exception.Message.Length)) }
