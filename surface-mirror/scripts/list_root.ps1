param([string]$Root = "E:\")
if (Test-Path $Root) {
    Get-ChildItem $Root -Directory -ErrorAction SilentlyContinue |
        Select-Object Name, @{N='MB';E={[math]::Round(((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB),1)}} |
        Sort-Object MB -Descending |
        Format-Table -AutoSize
} else {
    Write-Host "not mounted: $Root"
}
