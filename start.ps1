param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8009,
    [string]$BindIp = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$condaEnvironment = 'novelaipay'
$condaExe = if ($env:CONDA_EXE -and (Test-Path -LiteralPath $env:CONDA_EXE)) {
    $env:CONDA_EXE
} else {
    (Get-Command conda.exe -ErrorAction Stop).Source
}
$condaBase = (& $condaExe info --base).Trim()
if ($LASTEXITCODE -ne 0 -or -not $condaBase) {
    throw 'Unable to locate the Conda installation.'
}
$condaHook = Join-Path $condaBase 'shell\condabin\conda-hook.ps1'

if (-not (Test-Path -LiteralPath $condaHook)) {
    throw "Conda hook not found: $condaHook"
}
foreach ($requiredFile in @('.env', 'config.yaml')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $requiredFile))) {
        throw "Missing $requiredFile in $projectRoot"
    }
}

& $condaHook
conda activate $condaEnvironment
if ($env:CONDA_DEFAULT_ENV -ne $condaEnvironment -or -not $env:CONDA_PREFIX) {
    throw "Failed to activate Conda environment: $condaEnvironment"
}
$env:PYTHONNOUSERSITE = '1'

$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($owner in $owners) {
        if ($owner -le 4 -or $owner -eq $PID) {
            throw "Port $Port is owned by protected process $owner; stop it manually."
        }
        Write-Host "Stopping process $owner on port $Port..."
        Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } while ($listeners.Count -gt 0 -and (Get-Date) -lt $deadline)
    if ($listeners.Count -gt 0) {
        $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
        throw "Port $Port is still in use by process(es) $owners."
    }
}

$python = Join-Path $env:CONDA_PREFIX 'python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python not found in Conda environment: $env:CONDA_PREFIX"
}

Push-Location $backendRoot
try {
    & $python -m app.prepare_db
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
