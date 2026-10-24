#!/bin/bash
# Start vLLM 0.27.1 with Mistral-7B-Instruct + tool-calling enabled
# Usage: bash start_vllm27_daemon.sh

set -e
export CUDA_HOME=/usr/local/cuda-13.4
export PATH=$CUDA_HOME/bin:$PATH
export VLLM_WSL2_ENABLE_PIN_MEMORY=1
export VLLM_USE_V1=1

cd /root/vllm26
source .venv/bin/activate

# Kill any prior vllm
pkill -f 'vllm serve' 2>/dev/null || true
sleep 3

# Daemonize: setsid creates new session so vLLM survives our parent shell exit
setsid /root/vllm26/.venv/bin/vllm serve mistralai/Mistral-7B-Instruct-v0.3 \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 \
  --max-model-len 8192 \
  --download-dir /root/models \
  --enable-auto-tool-choice \
  --tool-call-parser mistral \
  > /root/vllm26/server.log 2>&1 < /dev/null &

echo $! > /root/vllm26/server.pid
disown
echo "vLLM started in detached session, PID=$(cat /root/vllm26/server.pid)"
echo "Wait ~90s for model load, then curl http://127.0.0.1:8000/v1/models"
