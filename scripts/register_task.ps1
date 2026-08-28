# Registers a Windows Task Scheduler job that runs daily_run.ps1 every day.
# Usage:   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time 08:00
# Remove:  Unregister-ScheduledTask -TaskName "graph_bot-daily" -Confirm:$false
param(
    [string]$Time = "08:00",
    [string]$TaskName = "graph_bot-daily"
)
$script = Join-Path $PSScriptRoot "daily_run.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "graph_bot: render daily statistics video" -Force

Write-Output "Registered '$TaskName' to run daily at $Time."
Write-Output "It renders + queues a draft; approve/publish stays manual."
