# ---------------------------------------------------------------------------
# Repair a uv-managed Hermes venv on a remote Windows host.
#
# THE FAULT THIS REPAIRS
#
# uv renames its managed interpreter directories when it upgrades
# (cpython-3.11-... -> cpython-3.11.15-...). A venv's pyvenv.cfg keeps
# naming the OLD path, so the venv's python cannot start:
#
#     error: uv trampoline failed to spawn Python child process
#     Caused by: entity not found (os error 2)
#
# It reads like a missing package and is not one - every dependency is
# still installed and intact. Editing pyvenv.cfg alone does NOT fix it,
# because the trampoline in Scripts\python.exe has the old target
# EMBEDDED in it. A copied python.exe is not enough either: the DLLs
# live beside the base executable.
#
# The repair, in order:
#   1. `uv python install <version>` - restore the managed interpreter
#   2. repoint pyvenv.cfg's `home` at what is ON DISK now
#   3. put a real interpreter (and its DLLs) in the venv's Scripts
#   4. prove it: import the packages the gateway actually needs
#
# It is IDEMPOTENT. Run it on a healthy venv and it reports healthy and
# changes nothing.
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Continue'

$venv = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent\venv'
$cfg  = Join-Path $venv 'pyvenv.cfg'
$scripts = Join-Path $venv 'Scripts'

Write-Output "=== hermes venv on $env:COMPUTERNAME ==="
if (-not (Test-Path $cfg)) {
    Write-Output "  FAILED: no venv at $venv"
    exit 1
}

$homeLine = Get-Content $cfg | Where-Object { $_ -like 'home =*' } | Select-Object -First 1
if (-not $homeLine) {
    Write-Output "  FAILED: pyvenv.cfg has no home key"
    exit 1
}
$home = $homeLine.Substring(6).Trim()
Write-Output "  venv      : $venv"
Write-Output "  home says : $home"

$version = $null
if ($home -match 'cpython-(\d+)\.(\d+)') { $version = "$($Matches[1]).$($Matches[2])" }
if (-not $version) { $version = '3.11' }
Write-Output "  version   : $version"

function Test-VenvHealthy {
    $py = Join-Path $scripts 'python.exe'
    if (-not (Test-Path $py)) { return $false }
    $out = & $py -c "import sys, mcp, pydantic, httpx; print(sys.version.split()[0])" 2>&1
    return ($LASTEXITCODE -eq 0)
}

if (Test-VenvHealthy) {
    Write-Output "  VERDICT: healthy - nothing to do"
    exit 0
}

Write-Output "  the venv cannot run. repairing."

# --- 1. restore the managed interpreter -------------------------------------
$uv = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
if (-not (Test-Path $uv)) {
    $found = Get-Command uv -ErrorAction SilentlyContinue
    if ($found) { $uv = $found.Source }
}
if (-not (Test-Path $uv)) {
    Write-Output "  FAILED: uv is not on this host; install it or copy an interpreter in by hand"
    exit 1
}
Write-Output "  installing the managed interpreter with $uv"
& $uv python install $version 2>&1 | ForEach-Object { "    $_" }

# --- 2. find what is on disk now -------------------------------------------
$uvRoot = Join-Path $env:APPDATA 'uv\python'
$target = Get-ChildItem $uvRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "cpython-$version*" -and (Test-Path (Join-Path $_.FullName 'python.exe')) } |
    Sort-Object Name -Descending |
    Select-Object -First 1
if (-not $target) {
    Write-Output "  FAILED: no managed cpython-$version interpreter is present after the install"
    exit 1
}
Write-Output "  managed interpreter: $($target.FullName)"

# --- 3. repoint pyvenv.cfg --------------------------------------------------
$lines = Get-Content $cfg
$out = foreach ($l in $lines) {
    if ($l -like 'home =*') { "home = $($target.FullName)" } else { $l }
}
[IO.File]::WriteAllText($cfg, ($out -join "`r`n"))

# --- 4. the trampoline has the OLD target embedded; put a real one there ---
$baseExe = Join-Path $target.FullName 'python.exe'
Copy-Item $baseExe (Join-Path $scripts 'python.exe') -Force
foreach ($dll in Get-ChildItem $target.FullName -Filter '*.dll' -ErrorAction SilentlyContinue) {
    Copy-Item $dll.FullName (Join-Path $scripts $dll.Name) -Force
}
Write-Output "  pyvenv.cfg repointed and the interpreter placed in Scripts"

# --- 5. prove it -------------------------------------------------------------
if (Test-VenvHealthy) {
    $ver = & (Join-Path $scripts 'python.exe') -c "import sys; print(sys.version.split()[0])"
    Write-Output "  VERDICT: repaired - the venv runs again (python $ver)"
    exit 0
}
Write-Output "  FAILED: the venv still does not run"
exit 1
