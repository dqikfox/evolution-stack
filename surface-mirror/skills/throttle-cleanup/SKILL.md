---
name: throttle-cleanup
description: Kill Windows throttling processes safely.
---

# Windows Throttle Cleanup Playbook

## When to load
- CPU% stays high at idle (>20%)
- User says "PC is lagging", "MAKE SURE NOTHING IS THROTTLING", "PC slow"
- `powercfg /getactivescheme` returns anything other than "High performance"
- Top 10 CPU procs include: PhoneExperienceHost, CrossDeviceService, CCleaner autostart, duplicate ChatGPT/Grok instances, multiple Shadow PC procs

## Throttle source checklist (read first, don't kill blindly)
1. **Power plan**: `powercfg /getactivescheme` and `powercfg /query SCHEME_CURRENT SUB_PROCESSOR`. DC min must be 100%, AC min 100%, AC/DC max 100%.
2. **GPU**: `nvidia-smi --query-gpu=clocks.current.sm,clocks.max.sm,temperature.gpu,power.draw,power.limit --format=csv`. Throttled if `current/max < 0.5` or temp > 83.
3. **Top processes**: `Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name,Id,CPU,@{N='MemMb';E={[int]($_.WorkingSet/1MB)}}`.
4. **Autostart bloat**: `Get-CimInstance Win32_StartupCommand`.

## Browser/WebView/ChatGPT multi-instance pattern (real-world RAM killer)

`chrome.exe` x2, `msedgewebview2.exe` x2, `ChatGPT.exe` (Codex) x2, plus a Hermes-controlled Chromium are all common on this host and can pin 6–10 GB of RAM between them. Killing them blindly closes the user's active tabs.

**MainWindowHandle guard — required before any kill:**

```powershell
$proc = Get-Process -Name 'msedgewebview2' -ErrorAction SilentlyContinue
foreach ($p in $proc) {
  if ($p.MainWindowHandle -ne [IntPtr]::Zero -or $p.MainWindowTitle) {
    Write-Host "SKIP $($p.ProcessName) PID=$($p.Id) -- window '$($p.MainWindowTitle)'"
  } else {
    Write-Host "END  $($p.ProcessName) PID=$($p.Id) WS=$([int]($p.WS/1MB))MB"
    Stop-Process -Id $p.Id -Force
  }
}
```

The check `MainWindowHandle -ne [IntPtr]::Zero` separates foreground/in-focus processes from background spawns. WebView2 helpers and idle ChatGPT instances have no main window; the live user-facing ones do. Apply the same guard to `chrome.exe`, `msedge.exe`, `firefox.exe`, `ChatGPT.exe`, `Codex.exe`.

**Rule:** never kill a process whose `MainWindowHandle` is non-zero unless the user has confirmed the tab is unwanted. WebView2 helpers that host Hermes's browser-tools process are not always obvious from the executable name.

## Safe-kill whitelist (run without asking)
- PhoneExperienceHost (Microsoft Phone Link)
- CrossDeviceService (Windows Cross Device)
- CCleaner autostart entries
- OneDrive / GoogleDrive (if user disabled cloud sync preference)
- Docker Desktop (set to manual start)
- Steam / Discord / Gemini launcher (if user reports idle)
- Background `msedgewebview2.exe` instances (no `MainWindowHandle`, no `MainWindowTitle`)
- Background `ChatGPT.exe` (Codex) instances (no `MainWindowHandle`, no `MainWindowTitle`)

## NEVER kill (ask user first or it's the user's active work)
- Taskmgr (the audit tool itself)
- MsMpEng (Defender)
- python.exe with >1GB RAM (likely Ollama/Hermes server)
- cyberstrike.exe (Hermes sub-dep, debug first)
- Shadow PC instances (user may be remoted in)
- Any `chrome.exe` / `msedge.exe` / `firefox.exe` / `ChatGPT.exe` with a non-zero `MainWindowHandle` — the user is in it right now

## Fix script (non-destructive)
```powershell
# Phone Link + Cross Device - Microsoft-shipped telemetry
schtasks /Change /TN "\Microsoft\Windows\PhoneLink\PhoneExperienceHostTask" /Disable | Out-Null
schtasks /Change /TN "\Microsoft\Windows\CrossDevice\CrossDeviceServiceTask" /Disable | Out-Null

# CCleaner Browser autostart
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "CCleaner Browser" -ErrorAction SilentlyContinue

# Confirm power plan is High Performance AC
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
```

## Verify after fix
- Top CPU proc should be <3000 (was 21705 for PhoneExperienceHost)
- Free RAM +20% typical
- 30s idle CPU average <5%

## Do not
- Disable Defender
- Touch service registry for MS-shipped services without listing them
- Kill by taskkill /F without first verifying process is not UserWork

## Report format
"Cleared N processes: list. CPU dropped from X% to Y%. Safe-kill whitelist only."