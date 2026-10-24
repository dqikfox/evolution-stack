@echo off
set MODEL=D:\ai\models\Qwen2.5-7B-Instruct.Q4_K_M.gguf
set LOG=D:\ai\llama.cpp\qwen.log
echo [%date% %time%] Starting llama-server with Qwen2.5-7B-Instruct (best 7B tool-caller)... > "%LOG%"
start "llama-qwen" /B "D:\ai\llama.cpp\llama-server.exe" ^
  --model "%MODEL%" ^
  --alias qwen2.5-7b-instruct ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --ctx-size 8192 ^
  --n-gpu-layers 99 ^
  --batch-size 512 ^
  --threads 8 ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --flash-attn auto ^
  --jinja ^
  >> "%LOG%" 2>&1
echo started
