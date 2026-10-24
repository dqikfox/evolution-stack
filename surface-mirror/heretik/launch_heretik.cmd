@echo off
REM HERETIK launcher — Windows desktop icon target
set HERETK_DIR=%LOCALAPPDATA%\hermes\heretik
set HERETIK_HOME=%HERETK_DIR%
REM Source THRONE canonical endpoints (HERETIK_BASE_URL, OLLAMA_BASE, ...)
if exist "%USERPROFILE%\.ultron\endpoints.env" (
  for /F "usebackq tokens=1,2 delims==" %%a in ("%USERPROFILE%\.ultron\endpoints.env") do (
    if not "%%a"=="#" set %%a=%%b
  )
)
set PYTHON=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe

REM Ensure llama-server (Qwen2.5-7B) is running on :8080 via PowerShell check without path expansion issues inside the string.
powershell -NoProfile -Command "$c = Test-NetConnection -ComputerName 127.0.0.1 -Port 8080 -ErrorAction SilentlyContinue; if (-not $c.TcpTestSucceeded) { echo 'Starting Qwen...'; Start-Process -FilePath '%HERETIK_HOME%\start_llama_qwen.cmd' -WindowStyle Hidden } else { echo 'Llama server already active.' }"

echo Waiting for llama-server to come up on :8080...
set COUNT=0
:wait_loop
if %COUNT% GEQ 60 goto :timeout_error
ping -n 2 127.0.0.1 > NUL
powershell -NoProfile -Command "if ((Test-Net-Connection -ComputerName 127.0.0.1 -Port 8080 -ErrorAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }" >NUL 2>&1 || (
    set /a COUNT+=1
    goto :wait_loop
)
goto :ready

:timeout_error
echo ERROR: llama-server failed to start or timeout reached. Check logs.
pause
exit /b 1

:ready
echo llama-server ready.
echo.

REM Run the agent REPL
"%PYTHON%" -u "%HERETIK_HOME%\heretik.py"
