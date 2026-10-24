$ErrorActionPreference = 'Stop'

Write-Host "=== STEP 1: Evict megatron-agent ==="
$evictBody = '{"model":"megatron-agent","keep_alive":0}'
try {
  $r = Invoke-WebRequest http://localhost:11434/api/generate -Method POST -ContentType 'application/json' -Body $evictBody -UseBasicParsing -TimeoutSec 30
  Write-Host "Evict:" $r.StatusCode
} catch { Write-Host "Evict ERR:" $_.Exception.Message }

Start-Sleep 2
Write-Host "VRAM after evict:"
& 'C:\Windows\System32\nvidia-smi.exe' --query-gpu=memory.used,memory.free --format=csv,noheader

Write-Host ""
Write-Host "=== STEP 2: Load starscream-64k (262K ctx) ==="
$body = @{
  model    = 'starscream-64k:latest'
  prompt   = 'Reply with exactly: STARScream OK'
  stream   = $false
  keep_alive = '24h'
  options  = @{ num_predict = 16; temperature = 0.1; num_ctx = 262144 }
} | ConvertTo-Json -Compress

$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $r = Invoke-WebRequest http://localhost:11434/api/generate -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing -TimeoutSec 180
  $sw.Stop()
  Write-Host "HTTP" $r.StatusCode "in" $sw.Elapsed.TotalSeconds "s"
  Write-Host $r.Content
} catch {
  $sw.Stop()
  Write-Host "ERR after" $sw.Elapsed.TotalSeconds "s:" $_.Exception.Message
}

Write-Host ""
Write-Host "=== STEP 3: VRAM after load ==="
& 'C:\Windows\System32\nvidia-smi.exe' --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader

Write-Host ""
Write-Host "=== STEP 4: /api/ps ==="
(Invoke-WebRequest http://localhost:11434/api/ps -UseBasicParsing -TimeoutSec 5).Content
