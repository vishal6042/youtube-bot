<#
.SYNOPSIS
    Creates (or refreshes) the desktop shortcut that launches the Data in Motion
    mission control app.

.DESCRIPTION
    Writes "Data in Motion.lnk" to the desktop, pointing at
    scripts\launch_app.ps1. Run it again any time to update the shortcut.

.EXAMPLE
    .\scripts\make_shortcut.ps1
    .\scripts\make_shortcut.ps1 -Dev -Name "Data in Motion (dev)"
    .\scripts\make_shortcut.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$Name = "Data in Motion",
    [switch]$Dev,        # shortcut runs the launcher in hot-reload dev mode
    [switch]$StartMenu,  # also place a copy in the Start Menu
    [switch]$Remove      # delete the shortcut instead of creating it
)

$ErrorActionPreference = "Stop"

$root     = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root "scripts\launch_app.ps1"
$icon     = Join-Path $root "assets\brand\dashboard.ico"
$desktop  = [Environment]::GetFolderPath("Desktop")
$programs = [Environment]::GetFolderPath("Programs")

$targets = @((Join-Path $desktop "$Name.lnk"))
if ($StartMenu) { $targets += (Join-Path $programs "$Name.lnk") }

if ($Remove) {
    foreach ($lnk in $targets) {
        if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "removed $lnk" }
        else { Write-Host "not present: $lnk" -ForegroundColor DarkGray }
    }
    return
}

if (-not (Test-Path $launcher)) { throw "launcher missing: $launcher" }

# powershell.exe (not pwsh) so the shortcut works on a stock Windows install.
$powershell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments  = "-NoLogo -ExecutionPolicy Bypass -File `"$launcher`""
if ($Dev) { $arguments += " -Dev" }

$shell = New-Object -ComObject WScript.Shell
foreach ($lnk in $targets) {
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath       = $powershell
    $sc.Arguments        = $arguments
    $sc.WorkingDirectory = $root
    $sc.Description      = "Start the Data in Motion mission control app (frontend + backend)"
    $sc.WindowStyle      = 1
    if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
    $sc.Save()
    Write-Host "created $lnk" -ForegroundColor Green
}

Write-Host ""
Write-Host "Double-click it to start the app; it opens http://127.0.0.1:8787/ once the backend is up." -ForegroundColor DarkGray
