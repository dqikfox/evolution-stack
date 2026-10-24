$payload = @{
    model    = 'qwen2.5-7b-instruct'
    messages = @(
        @{role='system'; content='You are HERETIK, an elite local AI agent on Windows THRONE (RTX 3090 24GB, Xeon W-2235, 64GB RAM). Hitchy has full trust. Be terse, technical. Lead with the result.'},
        @{role='user'; content="Quick check: what's the current VRAM use on this host, and is the starscream-64k model still loaded in ollama?"}
    )
    max_tokens = 200
    temperature = 0.2
} | ConvertTo-Json -Depth 6

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$r = Invoke-WebRequest http://127.0.0.1:8080/v1/chat/completions -Method POST -ContentType 'application/json' -Body $payload -UseBasicParsing -TimeoutSec 90
$sw.Stop()
$j = $r.Content | ConvertFrom-Json
Write-Host ('HTTP ' + $r.StatusCode + ' in ' + $sw.Elapsed.TotalSeconds + 's')
Write-Host ('usage: prompt=' + $j.usage.prompt_tokens + ' completion=' + $j.usage.completion_tokens)
Write-Host '---'
Write-Host $j.choices[0].message.content
