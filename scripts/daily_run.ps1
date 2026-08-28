# Renders the day's rotating topic (auto-selected) and queues it as a draft.
# Publishing stays behind your approval (see graph_bot.review).
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$logFile = Join-Path $logDir "$stamp.log"

Set-Location $root
("[{0}] starting daily render" -f (Get-Date -Format "s")) | Out-File -FilePath $logFile -Append -Encoding utf8
# Capture all output as plain UTF-8 text (ToString avoids stderr ErrorRecord wrapping).
& $py -m graph_bot.pipeline 2>&1 | ForEach-Object { $_.ToString() } |
    Out-File -FilePath $logFile -Append -Encoding utf8
$code = $LASTEXITCODE
("[{0}] done (exit {1})" -f (Get-Date -Format "s"), $code) | Out-File -FilePath $logFile -Append -Encoding utf8
