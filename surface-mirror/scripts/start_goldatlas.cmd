@echo off
REM ---------------------------------------------------------------------------
REM Idempotent launcher for the GOLD AU Evidence Atlas (:8767) and its public
REM exposure.
REM
REM WHY 8767 AND NOT 8766
REM
REM   8766 belongs to QMS. The atlas's original serve.py hard-codes 8766, and
REM   the "public gateway" that used to sit in front of it PROXIED 8767 back to
REM   8766. That is the trap this launcher exists to close: if QMS holds 8766,
REM   the gateway happily proxies the PUBLIC URL to QMS and the external link
REM   serves the wrong application while every local probe says "200 OK".
REM
REM   So the atlas serves itself on 8767, and the probe is BODY-AWARE. QMS
REM   answers 200 on 8766; only the atlas answers 200 with "Evidence Atlas" in
REM   the body. A port check alone cannot tell the two apart.
REM
REM THE ORDER IN THIS FILE IS THE WHOLE POINT:
REM
REM   1. DEPENDENCIES FIRST. Every tool this launcher needs is checked before
REM      it touches anything.
REM
REM   2. THE DECISION BEFORE THE DESTRUCTION. service_control.prepare probes
REM      the service first and only ever destroys something when that is the
REM      only correct action. A healthy service is never torn down to be
REM      rebuilt, and a port held by a stranger is never reclaimed.
REM
REM   3. THE SERVER MUST NOT INHERIT THE CALLER'S STDOUT. spawn_detached.py
REM      uses close_fds=True, so the child inherits nothing but its log file.
REM
REM   4. THE PUBLIC URL IS VERIFIED, NOT ASSUMED. A tunnel that is running but
REM      pointing at the wrong port is worse than no tunnel, so the external
REM      URL is fetched and its body compared against the local body.
REM
REM Usage:  start_goldatlas.cmd
REM ---------------------------------------------------------------------------
setlocal
REM Clear the agent's import path: a service must use its own packages.
set PYTHONPATH=
set PYTHONHOME=
set PYTHONSTARTUP=
set VIRTUAL_ENV=

set GA_ATLAS=C:\Users\KING\Documents\GOLD AU\Gold_Atlas_2026-09-30
set GA_PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set GA_PORT=8767
set GA_LOG=%LOCALAPPDATA%\hermes\logs\goldatlas_stdout.log
set SPAWNER=%LOCALAPPDATA%\hermes\scripts\spawn_detached.py
set PROBE=%LOCALAPPDATA%\hermes\scripts\probe_http.py
set WAITER=%LOCALAPPDATA%\hermes\scripts\wait_for_http.py
set RECLAIMER=%LOCALAPPDATA%\hermes\scripts\service_control.py
REM The health route answers JSON, not the page. A route that serves HTML is a
REM static file being served, not a service reporting itself ready, and the
REM estate's own gate reads HTML as DOWN. The body still carries "Evidence
REM Atlas", so the body-aware probe below is unchanged.
set GA_HEALTH=http://127.0.0.1:%GA_PORT%/health
REM The marker names our own process. The house tooling identifies a service
REM by a command line that ENDS with the script name.
set GA_MARKER=gold_atlas_8767.py
REM The body marker. QMS also answers 200, so the port check is not enough.
set GA_BODY=Evidence Atlas
set CLOUDFLARED=C:\Program Files (x86)\cloudflared\cloudflared.exe
set TAILSCALE=C:\Program Files\Tailscale\tailscale.exe
set URLFILE=%LOCALAPPDATA%\hermes\state\gold_atlas_public_url.txt

REM --- 1. DEPENDENCIES FIRST. Nothing is destroyed before this block passes.
if not exist "%GA_PY%" (
    echo [goldatlas] FAILED: interpreter missing at %GA_PY%
    exit /b 1
)
if not exist "%GA_ATLAS%\%GA_MARKER%" (
    echo [goldatlas] FAILED: the atlas server missing at %GA_ATLAS%\%GA_MARKER%
    exit /b 1
)
if not exist "%SPAWNER%" (
    echo [goldatlas] FAILED: spawner missing at %SPAWNER%
    exit /b 1
)
if not exist "%WAITER%" (
    echo [goldatlas] FAILED: waiter missing at %WAITER%
    exit /b 1
)
if not exist "%RECLAIMER%" (
    echo [goldatlas] FAILED: reclaimer missing at %RECLAIMER%
    exit /b 1
)
if not exist "%PROBE%" (
    echo [goldatlas] FAILED: probe missing at %PROBE%
    exit /b 1
)
if not exist "%LOCALAPPDATA%\hermes\logs" mkdir "%LOCALAPPDATA%\hermes\logs" 2>nul
if not exist "%LOCALAPPDATA%\hermes\state" mkdir "%LOCALAPPDATA%\hermes\state" 2>nul

REM --- 2. THE DECISION. The atlas is probed before anything is destroyed.
echo [goldatlas] checking port %GA_PORT%...
"%GA_PY%" "%RECLAIMER%" prepare --port %GA_PORT% --marker "%GA_MARKER%" --health "%GA_HEALTH%" --contains "%GA_BODY%"
set RC=%ERRORLEVEL%
if "%RC%"=="2" (
    echo [goldatlas] already up on :%GA_PORT% - healthy, nothing to do.
    goto :expose
)
if "%RC%"=="1" (
    echo [goldatlas] FAILED: :%GA_PORT% is held by a process that is not ours
    exit /b 1
)
REM RC=0: the port is free, or an orphan of ours was reclaimed.

echo [goldatlas] starting (server log: %GA_LOG%)...
cd /d "%GA_ATLAS%"
"%GA_PY%" "%SPAWNER%" --log "%GA_LOG%" --err "%GA_LOG%.err" --cwd "%GA_ATLAS%" -- "%GA_PY%" "%GA_ATLAS%\%GA_MARKER%"
if errorlevel 1 (
    echo [goldatlas] FAILED: spawner returned an error - see %GA_LOG%.err
    exit /b 1
)

echo [goldatlas] waiting for :%GA_PORT%...
"%GA_PY%" "%WAITER%" "%GA_HEALTH%" 120 2
if errorlevel 1 (
    echo [goldatlas] FAILED: the endpoint did not answer within 120s - see %GA_LOG%
    exit /b 1
)
echo [goldatlas] up on :%GA_PORT%

:expose
REM --- 3. THE PUBLIC URL. Tailscale Funnel is the stable one: it survives a
REM reboot, it uses a name the user can be given, and it is already proven on
REM this host. The cloudflared quick tunnel is the secondary, and its URL
REM changes every time it restarts, so it is recorded rather than promised.
if exist "%TAILSCALE%" (
    "%TAILSCALE%" funnel --bg http://127.0.0.1:%GA_PORT% >nul 2>&1
    if errorlevel 1 (
        echo [goldatlas] WARNING: the tailscale funnel did not take
    ) else (
        echo [goldatlas] the public URL: https://throne-1.tail886dbb.ts.net/
    )
)

REM The tunnel is probed BY ITS BODY, not by the presence of a process. A
REM cloudflared that is running but pointing at the wrong port is the exact
REM failure this launcher exists to prevent, and a stale URL file would
REM otherwise keep a dead tunnel alive forever.
set GA_TUNNELLOG=%LOCALAPPDATA%\hermes\logs\goldatlas_tunnel.log
set GA_TUNNELOK=
if exist "%URLFILE%" (
    "%GA_PY%" -c "import urllib.request,pathlib,sys;u=pathlib.Path(r'%URLFILE%').read_text(encoding='utf-8').strip();sys.exit(0 if u and b'Evidence Atlas' in urllib.request.urlopen(u,timeout=30).read() else 1)" >nul 2>&1
    if not errorlevel 1 set GA_TUNNELOK=1
)
if not defined GA_TUNNELOK (
    echo [goldatlas] starting the cloudflare quick tunnel...
    REM spawn_detached.py, NOT "start /b". A child started with start /b
    REM inherits the console handles, so a caller that captured stdout into
    REM a pipe waits for the TUNNEL to exit instead of for the launcher, and
    REM the whole pipeline hangs forever. spawn_detached.py uses
    REM close_fds=True, so the child keeps nothing but its log file.
    "%GA_PY%" "%SPAWNER%" --log "%GA_TUNNELLOG%" --err "%GA_TUNNELLOG%.err" --cwd "%GA_ATLAS%" -- "%CLOUDFLARED%" tunnel --url http://127.0.0.1:%GA_PORT% --no-autoupdate
    if errorlevel 1 (
        echo [goldatlas] WARNING: the cloudflare tunnel did not start
    ) else (
        timeout /t 20 /nobreak >nul
        REM The quick tunnel prints its URL. It is RECORDED, not relied on:
        REM it changes on every restart.
        "%GA_PY%" -c "import re,pathlib;p=pathlib.Path(r'%GA_TUNNELLOG%');s=p.read_text(errors='replace') if p.exists() else '';m=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',s);pathlib.Path(r'%URLFILE%').write_text(m.group(0) if m else '',encoding='utf-8')" >nul 2>&1
    )
) else (
    echo [goldatlas] the cloudflare tunnel is already serving the atlas
)

REM --- 4. VERIFY THE PUBLIC URL SERVES THE MAP. A tunnel that answers 200
REM with the wrong application is the exact failure this launcher exists to
REM prevent, so the body is compared, not the status code.
echo [goldatlas] verifying the public URL serves the atlas...
"%GA_PY%" -c "import urllib.request,hashlib,sys;u='https://throne-1.tail886dbb.ts.net/app/';l='http://127.0.0.1:%GA_PORT%/app/';g=lambda x: hashlib.sha256(urllib.request.urlopen(x,timeout=45).read()).hexdigest();p=g(u);q=g(l);print('   the public body == the local body:',p==q);sys.exit(0 if p==q else 1)" 2>nul
if errorlevel 1 (
    echo [goldatlas] WARNING: the public URL did not match the local atlas
) else (
    echo [goldatlas] VERIFIED: the public URL serves the atlas
)
exit /b 0
