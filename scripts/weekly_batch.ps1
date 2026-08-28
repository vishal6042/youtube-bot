# Weekly unattended batch:
#   render N least-recently-used topics -> auto-approve -> export by series.
# Leaves ready-to-upload folders in export\<date>\<series>\<key>\.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\weekly_batch.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\weekly_batch.ps1 -Count 5 -Series ml_concept
param(
    [int]$Count = 7,
    [string]$Series = ""
)

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("batch-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Log($msg) {
    ("[{0}] {1}" -f (Get-Date -Format "s"), $msg) |
        Out-File -FilePath $logFile -Append -Encoding utf8
}

Set-Location $root
Log "weekly batch starting (count=$Count series='$Series')"

# 1. Render + auto-approve
$renderArgs = @("-m", "graph_bot.pipeline", "--batch", $Count, "--auto-approve")
if ($Series -ne "") { $renderArgs += @("--series", $Series) }
& $py @renderArgs 2>&1 | ForEach-Object { $_.ToString() } |
    Out-File -FilePath $logFile -Append -Encoding utf8
$renderExit = $LASTEXITCODE
Log "render finished (exit $renderExit)"

# 2. Export every approved item into series folders
& $py -m graph_bot.publish.manual --all 2>&1 | ForEach-Object { $_.ToString() } |
    Out-File -FilePath $logFile -Append -Encoding utf8
Log "export finished (exit $LASTEXITCODE)"
Log "done - ready to upload from export\$(Get-Date -Format 'yyyy-MM-dd')"
