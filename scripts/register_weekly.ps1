# Registers a WEEKLY Windows scheduled task that renders + exports a batch.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\register_weekly.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register_weekly.ps1 -Day Sunday -Time 03:00 -Count 7
#
# Remove:
#   Unregister-ScheduledTask -TaskName "graph_bot-weekly" -Confirm:$false
param(
    [string]$Day = "Sunday",
    [string]$Time = "03:00",
    [int]$Count = 7,
    [string]$Series = "",
    [string]$TaskName = "graph_bot-weekly"
)

$script = Join-Path $PSScriptRoot "weekly_batch.ps1"
$inner = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Count $Count"
if ($Series -ne "") { $inner += " -Series $Series" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $inner
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time
# StartWhenAvailable: still runs if the PC was asleep at the scheduled time.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "graph_bot: weekly render + export batch" -Force

Write-Output "Registered '$TaskName': every $Day at $Time, $Count videos."
Write-Output "Output lands in export\<date>\<series>\<key>\ ; logs in logs\batch-<date>.log"
Write-Output "Run it now to test:  Start-ScheduledTask -TaskName $TaskName"
