param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8009,
    [string]$BindIp = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$condaHook = 'D:\miniconda3\shell\condabin\conda-hook.ps1'
$condaEnvironment = 'D:\miniconda3_envs\novelaipay'

if (-not (Test-Path -LiteralPath $condaHook)) {
    throw "Conda hook not found: $condaHook"
}
if (-not (Test-Path -LiteralPath $condaEnvironment)) {
    throw "Conda environment not found: $condaEnvironment"
}
foreach ($requiredFile in @('.env', 'config.yaml')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $requiredFile))) {
        throw "Missing $requiredFile in $projectRoot"
    }
}

& $condaHook
conda activate $condaEnvironment
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate Conda environment: $condaEnvironment"
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owners = $listener | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $owners) {
        Write-Host "Stopping process $processId on port $Port"
        Stop-Process -Id $processId -Force -ErrorAction Stop
    }
    Start-Sleep -Seconds 1
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port is still in use after stopping its listener."
    }
}

$python = (Get-Command python -ErrorAction Stop).Source
if (-not $python.StartsWith($condaEnvironment, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Activated Python is outside the expected environment: $python"
}

Push-Location $backendRoot
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }

    & $python -m app.bootstrap
    if ($LASTEXITCODE -ne 0) { throw 'Administrator bootstrap failed.' }

    $logDirectory = Join-Path $projectRoot 'data\logs'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $worker = Start-Process -FilePath $python -ArgumentList '-m', 'app.worker' `
        -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory 'worker.out.log') `
        -RedirectStandardError (Join-Path $logDirectory 'worker.err.log')
    try {
        Write-Host "Novelaipay: http://${BindIp}:$Port/ (worker PID $($worker.Id))"
        & $python -m uvicorn app.main:app --host $BindIp --port $Port
        if ($LASTEXITCODE -ne 0) { throw "API exited with code $LASTEXITCODE." }
    }
    finally {
        if ($worker -and -not $worker.HasExited) {
            Stop-Process -Id $worker.Id
        }
    }
}
finally {
    Pop-Location
}
