$body = @{
  model = 'starscream-64k:latest'
  prompt = 'Reply with exactly: STARScream OK'
  stream = $false
  options = @{ num_predict = 12; temperature = 0.1 }
} | ConvertTo-Json -Compress

$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $r = Invoke-WebRequest http://localhost:11434/api/generate -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing -TimeoutSec 60
  $sw.Stop()
  Write-Host "HTTP" $r.StatusCode "in" $sw.Elapsed.TotalSeconds "s"
  $j = $r.Content | ConvertFrom-Json
  Write-Host "Response:" $j.response
  Write-Host "Eval count:" $j.eval_count "tokens"
  Write-Host "Total duration:" ([math]::Round($j.total_duration/1e9,2)) "s"
} catch {
  $sw.Stop()
  Write-Host "ERR after" $sw.Elapsed.TotalSeconds "s:" $_.Exception.Message
}

Write-Host ""
Write-Host "=== /api/ps ==="
(Invoke-WebRequest http://localhost:11434/api/ps -UseBasicParsing -TimeoutSec 5).Content
Write-Host ""
Write-Host "=== VRAM ==="
& 'C:\Windows\System32\nvidia-smi.exe' --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader
