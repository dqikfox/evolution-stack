@echo off
REM THRONE — Launch llama-server (OpenAI-compatible API on :8080)
REM Mistral-7B-Instruct-v0.3 Q4_K_M, GPU-accelerated via CUDA 13.3
set LLAMA_HOME=C:\Users\KING\AppData\Local\hermes\scripts\llama
if not exist "%LLAMA_HOME%" mkdir "%LLAMA_HOME%"
set MODEL=D:\ai\models\Mistral-7B-Instruct-v0.3-Q4_K_M.gguf
set SERVER=D:\ai\llama.cpp\llama-server.exe
set LOG=%LLAMA_HOME%\server.log

REM Check model exists
if not exist "%MODEL%" (
  echo ERROR: Model not found at %MODEL%
  echo Run: hf download bartowski/Mistral-7B-Instruct-v0.3-GGUF/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf --local-dir D:\ai\models
  exit /b 1
)

REM Check if already running (avoid kill-and-restart race that loses the port)
curl -sS --max-time 2 http://127.0.0.1:8080/v1/models >NUL 2>&1 && (
  echo llama-server already running on :8080 (PID:
  powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Get-Process -Id \$_.OwningProcess -ErrorAction SilentlyContinue | Select-Object Id }" 2>&1 | findstr /R "[0-9]"
  echo ^).
  echo OpenAI-compatible endpoint: http://127.0.0.1:8080/v1
  echo Model: mistral-7b-instruct
  exit /b 0
)

REM Not running - kill any zombie and start fresh
taskkill /F /IM llama-server.exe >NUL 2>&1
timeout /t 2 /NOBREAK >NUL

REM Start server (window will close; use --detach on Linux; on Windows use START /B)
echo Starting llama-server on http://127.0.0.1:8080 ...
echo Log: %LOG%
start "llama-server" /B "%SERVER%" ^
  --model "%MODEL%" ^
  --alias mistral-7b-instruct ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --ctx-size 8192 ^
  --n-gpu-layers 99 ^
  --batch-size 512 ^
  --threads 8 ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --flash-attn auto ^
  > "%LOG%" 2>&1

REM Wait for ready
echo Waiting for server ...
for /L %%i in (1,1,30) do (
  timeout /t 1 /NOBREAK >NUL
  curl -sS --max-time 1 http://127.0.0.1:8080/v1/models >NUL 2>&1 && (
    echo Server is READY.
    echo.
    echo OpenAI-compatible endpoint: http://127.0.0.1:8080/v1
    echo Model: mistral-7b-instruct
    echo.
    echo Example:
    echo   curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" -d ^
    echo     "{\"model\":\"mistral-7b-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
    exit /b 0
  )
)
echo Server did NOT start within 30s. Check %LOG%
exit /b 1
