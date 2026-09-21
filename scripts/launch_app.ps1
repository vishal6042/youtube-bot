<#
.SYNOPSIS
    Launches the Data in Motion mission control app (frontend + backend) and
    opens it in the browser. This is what the desktop shortcut runs.

.DESCRIPTION
    Default (production) mode serves the prebuilt React bundle straight from the
    FastAPI server on 8787, so there is one process and no Node at runtime. The
    bundle is rebuilt automatically when dashboard/frontend is newer than
    dashboard/static.

    -Dev additionally starts the Vite dev server on 5173 (hot reload, /api
    proxied to 8787) and opens that instead.

.EXAMPLE
    .\scripts\launch_app.ps1
    .\scripts\launch_app.ps1 -Dev
#>
[CmdletBinding()]
param(
    [switch]$Dev,        # Vite dev server with hot reload instead of the bundle
    [switch]$Rebuild,    # force a frontend rebuild even if the bundle is current
    [switch]$NoBrowser,  # start the servers but do not open a browser
    [switch]$Stop        # stop an app left running by an earlier launch, then exit
)

$ErrorActionPreference = "Stop"

$root     = Split-Path -Parent $PSScriptRoot
$py       = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "dashboard\frontend"
$static   = Join-Path $root "dashboard\static"
$apiPort  = 8787
$devPort  = 5173
$children = @()

# Pipeline output contains Unicode; without UTF-8 mode cp1252 pipes crash renders.
$env:PYTHONUTF8 = "1"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$Host.UI.RawUI.WindowTitle = "Data in Motion - mission control"

# Vite binds "localhost", which resolves to ::1 on this machine, so the probe
# has to use the same name the server bound rather than a hardcoded 127.0.0.1.
function Test-Port([int]$Port, [string]$HostName = "127.0.0.1") {
    $client = New-Object Net.Sockets.TcpClient
    try { $client.Connect($HostName, $Port); return $true }
    catch { return $false }
    finally { $client.Close() }
}

function Wait-Port([int]$Port, [int]$TimeoutSec = 90, [string]$HostName = "127.0.0.1") {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $Port $HostName) { return $true }
        Start-Sleep -Milliseconds 300
    }
    return $false
}

function Get-NewestWrite([string[]]$Paths) {
    $newest = [DateTime]::MinValue
    foreach ($p in $Paths) {
        if (-not (Test-Path $p)) { continue }
        $item = Get-Item $p
        if ($item.PSIsContainer) {
            $hit = Get-ChildItem -Path $p -Recurse -File -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
            if ($hit -and $hit.LastWriteTimeUtc -gt $newest) { $newest = $hit.LastWriteTimeUtc }
        } elseif ($item.LastWriteTimeUtc -gt $newest) {
            $newest = $item.LastWriteTimeUtc
        }
    }
    return $newest
}

function Build-Frontend([string]$Npm) {
    if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
        Write-Host "  installing frontend dependencies (npm install)..." -ForegroundColor DarkGray
        Push-Location $frontend
        try { & $Npm install --no-fund --no-audit } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw "npm install failed (exit $LASTEXITCODE)" }
    }
    Push-Location $frontend
    try { & $Npm run build } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "frontend build failed (exit $LASTEXITCODE)" }
}

# The venv's python.exe re-execs the base interpreter, so the process that
# actually holds the port is a grandchild - always kill the whole tree.
function Stop-Tree([int]$ProcessId) {
    $self = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $self) { return }
    $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
    foreach ($kid in $kids) {
        # Guard against PID reuse: a real child cannot predate its parent.
        if ($kid.CreationDate -ge $self.CreationDate) { Stop-Tree ([int]$kid.ProcessId) }
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-Children {
    foreach ($proc in $children) {
        if ($proc -and -not $proc.HasExited) { Stop-Tree $proc.Id }
    }
}

function Stop-PortOwner([int]$Port, [string]$Label) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host ("  {0} was not running (port {1} free)" -f $Label, $Port) -ForegroundColor DarkGray
        return
    }
    foreach ($owner in ($conns.OwningProcess | Select-Object -Unique)) {
        Stop-Tree ([int]$owner)
        Write-Host ("  stopped {0} (pid {1}, port {2})" -f $Label, $owner, $Port) -ForegroundColor Yellow
    }
}

try {
    if ($Stop) {
        Stop-PortOwner $apiPort "backend"
        Stop-PortOwner $devPort "dev server"
        return
    }

    if (-not (Test-Path $py)) {
        throw "virtualenv missing: $py (run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
    }
    Set-Location $root
    # npm.cmd specifically: "npm" resolves to npm.ps1 / an extensionless shell
    # script first, and Start-Process cannot execute either of those.
    $npm = $null
    foreach ($candidate in @("npm.cmd", "npm.exe")) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { $npm = $found.Source; break }
    }

    Write-Host ""
    Write-Host "  DATA IN MOTION / mission control" -ForegroundColor Cyan
    Write-Host "  $root" -ForegroundColor DarkGray
    Write-Host ""

    # --- frontend ---------------------------------------------------------- #
    if (-not $Dev) {
        $bundle = Get-NewestWrite @($static)
        $source = Get-NewestWrite @(
            (Join-Path $frontend "src"),
            (Join-Path $frontend "public"),
            (Join-Path $frontend "index.html"),
            (Join-Path $frontend "vite.config.js"),
            (Join-Path $frontend "package.json")
        )
        $stale = $Rebuild -or (-not (Test-Path (Join-Path $static "index.html"))) -or ($source -gt $bundle)
        if ($stale -and $npm) {
            Write-Host "  [1/3] frontend bundle is stale - rebuilding" -ForegroundColor Yellow
            Build-Frontend $npm
        } elseif ($stale) {
            Write-Host "  [1/3] frontend bundle is stale but npm is not on PATH - serving the existing bundle" -ForegroundColor Yellow
        } else {
            Write-Host "  [1/3] frontend bundle is current" -ForegroundColor Green
        }
    } else {
        if (-not $npm) { throw "-Dev needs Node/npm on PATH" }
        Write-Host "  [1/3] dev mode - Vite will serve the frontend from source" -ForegroundColor Green
    }

    # --- backend ----------------------------------------------------------- #
    if (Test-Port $apiPort) {
        Write-Host "  [2/3] backend already listening on $apiPort - reusing it" -ForegroundColor Green
    } else {
        Write-Host "  [2/3] starting backend  http://127.0.0.1:$apiPort" -ForegroundColor Green
        $backend = Start-Process -FilePath $py -ArgumentList "-m", "dashboard.server" `
                                 -WorkingDirectory $root -NoNewWindow -PassThru
        $children += $backend
        if (-not (Wait-Port $apiPort)) { throw "backend did not come up on port $apiPort" }
    }

    # --- dev server -------------------------------------------------------- #
    $url = "http://127.0.0.1:$apiPort/"
    if ($Dev) {
        if (Test-Port $devPort "localhost") {
            Write-Host "  [3/3] dev server already listening on $devPort - reusing it" -ForegroundColor Green
        } else {
            Write-Host "  [3/3] starting Vite dev server  http://127.0.0.1:$devPort" -ForegroundColor Green
            $vite = Start-Process -FilePath $npm -ArgumentList "run", "dev" `
                                  -WorkingDirectory $frontend -NoNewWindow -PassThru
            $children += $vite
            if (-not (Wait-Port $devPort 90 "localhost")) { throw "Vite dev server did not come up on port $devPort" }
        }
        # vite.config.js sets base "/static/", so the dev shell lives there.
        $url = "http://localhost:$devPort/static/"
    } else {
        Write-Host "  [3/3] serving the bundle from the backend" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "  READY -> $url" -ForegroundColor Cyan
    Write-Host "  Close this window or press Ctrl+C to stop the app." -ForegroundColor DarkGray
    Write-Host ""

    if (-not $NoBrowser) { Start-Process $url | Out-Null }

    if ($children.Count -gt 0) {
        Wait-Process -Id ($children | ForEach-Object { $_.Id }) -ErrorAction SilentlyContinue
    } else {
        Write-Host "  Nothing was started by this window (servers were already running)." -ForegroundColor DarkGray
        Start-Sleep -Seconds 3
    }
}
catch {
    Write-Host ""
    Write-Host "  FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    # Keep the window readable when launched from a desktop shortcut.
    Write-Host "  Press Enter to close..." -ForegroundColor DarkGray
    Read-Host | Out-Null
    exit 1
}
finally {
    Stop-Children
}
