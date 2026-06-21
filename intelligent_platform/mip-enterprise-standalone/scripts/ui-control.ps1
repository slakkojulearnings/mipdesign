param(
    [ValidateSet("start", "stop", "check")]
    [string]$Action,
    [string]$DbPath = "data\mip-intel.db",
    [int]$ApiPort = 8000,
    [int]$UiPort = 5174
)

$ErrorActionPreference = "Stop"
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $AppDir "runtime"
$LogDir = Join-Path $AppDir "logs"
$ApiPidFile = Join-Path $RuntimeDir "mip-api.pid"
$UiPidFile = Join-Path $RuntimeDir "mip-ui.pid"

function Ensure-Dirs {
    New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir, (Join-Path $AppDir "data") | Out-Null
}

function Get-Python {
    $venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    $python = (Get-Command python -ErrorAction SilentlyContinue)
    if ($null -eq $python) {
        throw "Python was not found. Install Python 3.11+ or create .venv first."
    }
    return $python.Source
}

function Test-RunningPid([string]$PidFile) {
    if (-not (Test-Path $PidFile)) {
        return $false
    }
    $processId = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $processId) {
        return $false
    }
    return $null -ne (Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue)
}

function Stop-PidFile([string]$PidFile, [string]$Name) {
    if (-not (Test-Path $PidFile)) {
        return
    }
    $processId = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($processId) {
        $process = Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping $Name process $processId"
            Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-Port([int]$Port) {
    try {
        $owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($owner in $owners) {
            if ($owner -and $owner -ne $PID) {
                Write-Host "Stopping listener on port $Port, process $owner"
                Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-Host "Port fallback check skipped for $Port: $($_.Exception.Message)"
    }
}

function Test-Http([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Start-Ui {
    Ensure-Dirs
    if (Test-RunningPid $ApiPidFile -or Test-RunningPid $UiPidFile) {
        Write-Host "MIP UI already appears to be running. Use check_ui.bat or stop_ui.bat."
        return
    }

    $python = Get-Python
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        throw "npm was not found. Install Node.js 18+ first."
    }
    if (-not (Test-Path (Join-Path $AppDir "frontend\node_modules"))) {
        throw "frontend\node_modules was not found. Run: cd frontend && npm install"
    }

    $resolvedDb = if ([System.IO.Path]::IsPathRooted($DbPath)) { $DbPath } else { Join-Path $AppDir $DbPath }
    $env:PYTHONPATH = (Join-Path $AppDir "src")
    $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"

    $api = Start-Process -FilePath $python `
        -ArgumentList @("-m", "mip_intel.cli", "--db", $resolvedDb, "serve", "--host", "127.0.0.1", "--port", [string]$ApiPort) `
        -WorkingDirectory $AppDir `
        -RedirectStandardOutput (Join-Path $LogDir "api.out.log") `
        -RedirectStandardError (Join-Path $LogDir "api.err.log") `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -Path $ApiPidFile -Value $api.Id

    $ui = Start-Process -FilePath $npm.Source `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", [string]$UiPort) `
        -WorkingDirectory (Join-Path $AppDir "frontend") `
        -RedirectStandardOutput (Join-Path $LogDir "ui.out.log") `
        -RedirectStandardError (Join-Path $LogDir "ui.err.log") `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -Path $UiPidFile -Value $ui.Id

    Write-Host "Started MIP API on http://127.0.0.1:$ApiPort"
    Write-Host "Started MIP UI  on http://127.0.0.1:$UiPort"
    Write-Host "Logs: $LogDir"
}

function Stop-Ui {
    Stop-PidFile $UiPidFile "UI"
    Stop-PidFile $ApiPidFile "API"
    Stop-Port $UiPort
    Stop-Port $ApiPort
    Write-Host "Stopped MIP UI/API if they were running."
}

function Check-Ui {
    $apiPid = Test-RunningPid $ApiPidFile
    $uiPid = Test-RunningPid $UiPidFile
    $apiOk = Test-Http "http://127.0.0.1:$ApiPort/openapi.json"
    $uiOk = Test-Http "http://127.0.0.1:$UiPort/"

    Write-Host "API PID file running: $apiPid"
    Write-Host "UI  PID file running: $uiPid"
    Write-Host "API HTTP check:      $apiOk  http://127.0.0.1:$ApiPort/openapi.json"
    Write-Host "UI  HTTP check:      $uiOk  http://127.0.0.1:$UiPort/"

    if ($apiOk -and $uiOk) {
        Write-Host "MIP UI is ready: http://127.0.0.1:$UiPort"
        exit 0
    }
    Write-Host "MIP UI/API is not fully ready. Check logs under: $LogDir"
    exit 1
}

switch ($Action) {
    "start" { Start-Ui }
    "stop" { Stop-Ui }
    "check" { Check-Ui }
}
