
$target_workdir = "C:\Users\KING\AppData\Local\hermes\scripts\"
$taskName = "THRONE_Discovery_10min"
$cmdArgs = 'C:\Users\KING\AppData\Local\hermes\scripts\throne_discovery.py --http-port 8660'

try {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Write-Host "Found existing task: $taskName"
    
    $action = $task.Actions[0]
    $action.Arguments = $cmdArgs
    
    # Update the Task with a new settings object that has the correct WorkingDirectory (Start In)
    $newSettings = New-ScheduledTaskSettingsSet -WorkingDirectory $target_workdir
    Register-ScheduledTask -TaskName $taskName -Action $action -Settings $newSettings -User "KING" -Force
    
    Write-Host "SUCCESS: Re-registered $taskName with fixed working directory."
} catch {
    Write-Error "Failed to fix task: $_"
    exit 1
}
