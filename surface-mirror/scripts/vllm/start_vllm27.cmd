@echo off
REM THRONE — Launch vLLM 0.27.1 server in WSL2 (OpenAI-compatible API on :8000)
REM Model: Mistral-7B-Instruct-v0.3, GPU-accelerated via CUDA 13.3 (WSL2 passthrough)

REM Check if already running
wsl -d Ubuntu --exec /bin/bash -c "curl -sS --max-time 2 http://127.0.0.1:8000/v1/models >/dev/null 2>&1" >NUL 2>&1 && (
  echo vLLM 0.27.1 already running on :8000
  echo OpenAI-compatible endpoint: http://127.0.0.1:8000/v1
  echo Model: mistralai/Mistral-7B-Instruct-v0.3
  echo.
  echo Example:
  echo   curl http://127.0.0.1:8000/v1/chat/completions -H "Content-Type: application/json" -d ^
  echo     "{\"model\":\"mistralai/Mistral-7B-Instruct-v0.3\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
  exit /b 0
)

REM Not running - launch the daemon script in WSL
echo Starting vLLM 0.27.1 (this can take 3-5 minutes for model load + warmup)...
wsl -d Ubuntu --exec /bin/bash /root/start_vllm27_daemon.sh

REM Poll for readiness
echo Waiting for server to become ready...
for /L %%i in (1,1,40) do (
  timeout /t 5 /NOBREAK >NUL
  wsl -d Ubuntu --exec /bin/bash -c "curl -sS --max-time 2 http://127.0.0.1:8000/v1/models >/dev/null 2>&1" >NUL 2>&1 && (
    echo Server READY after approximately %%i*5s.
    echo.
    echo OpenAI-compatible endpoint: http://127.0.0.1:8000/v1
    echo Model: mistralai/Mistral-7B-Instruct-v0.3
    echo.
    echo Example:
    echo   curl http://127.0.0.1:8000/v1/chat/completions -H "Content-Type: application/json" -d ^
    echo     "{\"model\":\"mistralai/Mistral-7B-Instruct-v0.3\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
    exit /b 0
  )
)
echo Server did NOT start within 200s. Check WSL: wsl -d Ubuntu -- tail -50 /root/vllm26/server.log
exit /b 1
