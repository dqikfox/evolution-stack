$py = "C:\Users\KING\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$pipe = "E:\ultron-training"

$tasks = @(
    @{Name="THRONE_Model_Backup"; Desc="Mirror trained models to D"; Time="04:00"; Script="07_backup_models.py"; Trigger="Daily"},
    @{Name="THRONE_Eval_Daily"; Desc="Eval suite against served model"; Time="06:00"; Script="09_eval.py"; Trigger="Daily"},
    @{Name="THRONE_ContinuousTrain"; Desc="Re-harvest + retrain on new content"; Time="02:00"; Script="10_continuous_train.py"; Trigger="Weekly"},
    @{Name="THRONE_Alerts"; Desc="Probe services + alert on failure"; Time="00:05"; Script="14_alerts.py"; Trigger="Minutes"}
)

foreach ($t in $tasks) {
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false | Out-Null }

    $action = New-ScheduledTaskAction -Execute $py -Argument "-u `"$pipe\scripts\$($t.Script)`""
    if ($t.Trigger -eq "Daily") {
        $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time
    } elseif ($t.Trigger -eq "Weekly") {
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $t.Time
    } elseif ($t.Trigger -eq "Minutes") {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes [int]$t.Time.Substring(3)) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
    }
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType S4U
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Description $t.Desc | Out-Null

    Write-Host ("registered: " + $t.Name + " (" + $t.Trigger + " " + $t.Time + ")")
}

Write-Host ""
Write-Host "=== all THRONE_* scheduled tasks ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like "THRONE_*" } |
    Select-Object TaskName, State, @{N="Next"; E={$_.NextRunTime}} |
    Format-Table -AutoSize
