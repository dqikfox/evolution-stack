$ollama = Get-Process | Where-Object { $_.Name -eq 'ollama' }
Write-Host "=== ollama.exe ==="
$ollama | Format-Table Name,Id,@{N='RAM_MB';E={[math]::Round($_.WorkingSet64/1MB,1)}} -AutoSize
Write-Host "=== child processes ==="
$ollama | ForEach-Object {
    $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($_.Id)"
    $kids | Where-Object { $_.Name -ne 'flock' } | Select-Object Name,Id,@{N='RAM_MB';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Format-Table -AutoSize
}
Write-Host "=== /api/ps ==="
try { (Invoke-WebRequest http://localhost:11434/api/ps -UseBasicParsing -TimeoutSec 5).Content } catch { Write-Host "timeout" }
Write-Host "=== /api/tags (count) ==="
try { $tags = (Invoke-WebRequest http://localhost:11434/api/tags -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json; Write-Host "models:" $tags.models.Count } catch { Write-Host "timeout" }
