Get-Process | Where-Object { $_.Name -eq 'python' -and $_.WorkingSet64 -gt 1GB } | Format-Table Id,@{N='RAM_GB';E={[math]::Round($_.WorkingSet64/1GB,1)}},StartTime -AutoSize
Write-Host '--- python procs <1GB but running long ---'
Get-Process | Where-Object { $_.Name -eq 'python' -and $_.WorkingSet64 -lt 1GB -and (Get-Date) - $_.StartTime -gt [TimeSpan]::FromMinutes(30) } | Format-Table Id,@{N='RAM_GB';E={[math]::Round($_.WorkingSet64/1GB,2)}},StartTime -AutoSize
