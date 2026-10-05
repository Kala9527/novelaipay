@echo off
setlocal

set "CONDA_BAT=D:\miniconda3\condabin\conda.bat"
set "CONDA_ENV=D:\miniconda3_envs\novelaipay"

if not exist "%CONDA_BAT%" (
    echo Conda launcher not found: %CONDA_BAT% 1>&2
    exit /b 1
)
if not exist "%CONDA_ENV%\python.exe" (
    echo Conda environment not found: %CONDA_ENV% 1>&2
    exit /b 1
)

call "%CONDA_BAT%" activate "%CONDA_ENV%"
if errorlevel 1 (
    echo Failed to activate Conda environment. 1>&2
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Port 8009
exit /b %ERRORLEVEL%
