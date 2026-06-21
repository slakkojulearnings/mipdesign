@echo off
setlocal EnableExtensions

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

if "%~1"=="" goto usage

set "SOURCE_ROOT=%~1"
set "DB_PATH=%~2"
set "RUN_ID=%~3"

if "%DB_PATH%"=="" set "DB_PATH=data\mip-intel.db"
if "%RUN_ID%"=="" set "RUN_ID=manual-scan"

if not exist "%SOURCE_ROOT%" (
  echo Source folder not found: "%SOURCE_ROOT%"
  exit /b 2
)

if not exist "data" mkdir "data"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

set "PYTHONPATH=%APP_DIR%src;%PYTHONPATH%"
set "SCAN_CONFIG={run_id:%RUN_ID%,batch_size:1000,max_workers:4,parse_timeout_seconds:60,incremental:true,collect_telemetry:true,exclude_dirs:.git}"

echo.
echo Scanning source:
echo   %SOURCE_ROOT%
echo Database:
echo   %DB_PATH%
echo Run id:
echo   %RUN_ID%
echo.

"%PYTHON_EXE%" -m mip_intel.cli --db "%DB_PATH%" analyze "%SOURCE_ROOT%" --config "%SCAN_CONFIG%"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Validating graph facts...
"%PYTHON_EXE%" -m mip_intel.cli --db "%DB_PATH%" validate --run-id "%RUN_ID%"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Scan complete. Useful next commands:
echo   start_ui.bat "%DB_PATH%"
echo   "%PYTHON_EXE%" -m mip_intel.cli --db "%DB_PATH%" roots --run-id "%RUN_ID%" --limit 50
echo   "%PYTHON_EXE%" -m mip_intel.cli --db "%DB_PATH%" search CUST --run-id "%RUN_ID%"
exit /b 0

:usage
echo Usage:
echo   scan_codebase.bat "F:\path\to\source_code" [data\mip-intel.db] [run-id]
echo.
echo Example:
echo   scan_codebase.bat "F:\mainframe\source" data\bank.db bank-scan-001
exit /b 1
