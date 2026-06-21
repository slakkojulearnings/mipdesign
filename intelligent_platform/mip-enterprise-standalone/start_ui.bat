@echo off
setlocal EnableExtensions

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "DB_PATH=%~1"
set "API_PORT=%~2"
set "UI_PORT=%~3"

if "%DB_PATH%"=="" set "DB_PATH=data\mip-intel.db"
if "%API_PORT%"=="" set "API_PORT=8000"
if "%UI_PORT%"=="" set "UI_PORT=5174"

powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%scripts\ui-control.ps1" -Action start -DbPath "%DB_PATH%" -ApiPort %API_PORT% -UiPort %UI_PORT%
exit /b %errorlevel%
