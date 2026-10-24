$ErrorActionPreference = 'Stop'
$payload = @{
  model = 'megatron-agent'
  prompt = 'Reply with exactly: OK'
  stream = $false
  keep_alive = '24h'
  options = @{ num_predict = 8; temperature = 0.1 }
} | ConvertTo-Json -Compress
try {
  $r = Invoke-WebRequest http://localhost:11434/api/generate -Method POST -ContentType 'application/json' -Body $payload -UseBasicParsing -TimeoutSec 90
  Write-Host "HTTP" $r.StatusCode
  Write-Host $r.Content
} catch {
  Write-Host "ERR:" $_.Exception.Message
}
Write-Host "--- /api/ps ---"
try { (Invoke-WebRequest http://localhost:11434/api/ps -UseBasicParsing -TimeoutSec 5).Content } catch { "timeout" }
