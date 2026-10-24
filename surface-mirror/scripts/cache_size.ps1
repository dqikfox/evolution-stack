Get-ChildItem 'C:\Users\KING\.cache\huggingface\hub\models--Qwen--Qwen2.5-7B-Instruct' -Recurse -File | Measure-Object Length -Sum | Select-Object @{N='GB';E={[math]::Round($_.Sum/1GB,2)}}
