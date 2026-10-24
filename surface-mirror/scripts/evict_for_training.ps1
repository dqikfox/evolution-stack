Write-Host "=== BEFORE ==="
& 'C:\Windows\System32\nvidia-smi.exe' --query-gpu=memory.used,memory.free --format=csv,noheader

# Stop ollama.exe + child llama-servers (Ollama workers)
Write-Host "=== Stopping ollama + llama-servers ==="
$ollamaProcs = Get-Process ollama -ErrorAction SilentlyContinue
foreach ($p in $ollamaProcs) {
    Write-Host "  killing ollama PID $($p.Id) (RAM $([math]::Round($p.WorkingSet64/1MB,0)) MB)"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
$llamaProcs = Get-Process llama-server -ErrorAction SilentlyContinue
foreach ($p in $llamaProcs) {
    Write-Host "  killing llama-server PID $($p.Id) (RAM $([math]::Round($p.WorkingSet64/1MB,0)) MB)"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

Start-Sleep 3

Write-Host "=== AFTER ==="
& 'C:\Windows\System32\nvidia-smi.exe' --query-gpu=memory.used,memory.free --format=csv,noheader
Write-Host "=== ollama running? ==="
(Get-Process ollama -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "=== llama-server running? ==="
(Get-Process llama-server -ErrorAction SilentlyContinue | Measure-Object).Count
