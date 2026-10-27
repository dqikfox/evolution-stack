# Repair the two THRONE Scheduled Tasks whose triggers had expired.
#
# THRONE_Watchdog_5min
#   Trigger: OneTime, StartBoundary 2026-09-22, Duration P9DT2H40M, and
#   StopAtDurationEnd = TRUE. The task therefore stopped repeating on
#   2026-10-01 and has had an EMPTY NextRunTime ever since. The task's own
#   file even documents the earlier 0x80070002 failure, so this task has
#   been quietly broken twice over. The estate had no automatic recovery
#   for 26 days - which is why the gateway was found dead for three days
#   with nothing to restart it.
#
# Hermes_Gateway
#   Action ran a DETACHING VBS (wscript -> Hermes_Gateway.vbs). The task's
#   own process therefore exited immediately reporting SUCCESS, so its
#   RestartOnFailure never fired. The action now points at the idempotent
#   launcher, which STAYS IN THE FOREGROUND and returns a real exit code,
#   so a gateway that dies is actually restarted.
#
# Both tasks are re-registered with a trigger that does not expire, and both
# are given RestartOnFailure so a crash is retried instead of going dark.

$ErrorActionPreference = 'Stop'

$watchdogName = 'THRONE_Watchdog_5min'
$gatewayName  = 'Hermes_Gateway'

# ---------------------------------------------------------------- watchdog
$watchdogScript = 'C:\Users\KING\AppData\Local\hermes\scripts\watchdog_5min.cmd'

$wdAction = New-ScheduledTaskAction -Execute $watchdogScript -WorkingDirectory 'C:\Users\KING\AppData\Local\hermes'

# A repeating trigger with a long finite Duration and NO StopAtDurationEnd.
# The old trigger carried Duration=P9DT2H40M, so it expired on 2026-10-01.
# Ten years is a practical "never expires" and stays inside the task XML's
# duration range (TimeSpan.MaxValue is rejected as out of range).
$wdTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$wdPrincipal = New-ScheduledTaskPrincipal -UserId 'KING' -LogonType Interactive -RunLevel Limited

$wdSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Unregister-ScheduledTask -TaskName $watchdogName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $watchdogName `
    -Action $wdAction -Trigger $wdTrigger -Principal $wdPrincipal -Settings $wdSettings `
    -Description 'Estate watchdog: every 5 min, heals anything in SERVICES.json that is down. Trigger intentionally has no Duration so it never expires.' | Out-Null
Write-Host "re-registered $watchdogName"

# ---------------------------------------------------------------- gateway
$gatewayScript = 'C:\Users\KING\AppData\Local\hermes\scripts\start_hermes_gateway.cmd'

$gwAction = New-ScheduledTaskAction -Execute $gatewayScript -WorkingDirectory 'C:\Users\KING\AppData\Local\hermes'

# AtLogOn so the gateway - and therefore the cron tick - is up after a reboot.
$gwTrigger = New-ScheduledTaskTrigger -AtLogOn -User 'KING'
$gwTrigger.Delay = 'PT1M'

$gwPrincipal = New-ScheduledTaskPrincipal -UserId 'KING' -LogonType Interactive -RunLevel Limited

$gwSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Unregister-ScheduledTask -TaskName $gatewayName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $gatewayName `
    -Action $gwAction -Trigger $gwTrigger -Principal $gwPrincipal -Settings $gwSettings `
    -Description 'Hermes gateway via the idempotent launcher. Owns the cron tick: when it is down, every scheduled automation on THRONE stops. Foreground launcher so RestartOnFailure actually fires.' | Out-Null
Write-Host "re-registered $gatewayName"

# ---------------------------------------------------------------- verify
foreach ($name in @($watchdogName, $gatewayName)) {
    $t = Get-ScheduledTask -TaskName $name
    $i = Get-ScheduledTaskInfo -TaskName $name
    Write-Host ''
    Write-Host "== $name"
    Write-Host "   state        : $($t.State)"
    Write-Host "   next run     : $($i.NextRunTime)"
    Write-Host "   last run     : $($i.LastRunTime)  result=$($i.LastTaskResult)"
    Write-Host "   action       : $($t.Actions[0].Execute)"
    Write-Host "   restart count: $($t.Settings.RestartCount)"
}
