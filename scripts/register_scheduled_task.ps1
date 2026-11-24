# Registers a weekly Windows scheduled task that runs the update pipeline for the current user.
# NSO publishes its yearbook tables a few times a year; a weekly check costs ~15 s when nothing changed.
#   Register:   powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1
#   Remove:     Unregister-ScheduledTask -TaskName "VN Lubricant Demand - NSO refresh" -Confirm:$false
param(
    [string]$Day = "Monday",
    [string]$At = "07:00"
)

$root = Split-Path -Parent $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\run_pipeline.ps1`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "VN Lubricant Demand - NSO refresh" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Downloads NSO tables, rebuilds the lubricant demand model if any changed" -Force
