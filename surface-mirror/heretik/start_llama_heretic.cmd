@echo off
set MODEL=D:\ai\models\HERETICSEEK-7B-Ditill.Q4_K_M.gguf
set LOG=D:\ai\llama.cpp\heretic.log
echo [%date% %time%] Starting llama-server with HereticSeek... > "%LOG%"
start "llama-heretic" /B "D:\ai\llama.cpp\llama-server.exe" ^
  --model "%MODEL%" ^
  --alias hereticseek-7b-ditill ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --ctx-size 8192 ^
  --n-gpu-layers 99 ^
  --batch-size 512 ^
  --threads 8 ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --flash-attn auto ^
  >> "%LOG%" 2>&1
echo started
