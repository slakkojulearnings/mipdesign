@echo off
setlocal EnableExtensions

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "API_PORT=%~1"
set "UI_PORT=%~2"

if "%API_PORT%"=="" set "API_PORT=8000"
if "%UI_PORT%"=="" set "UI_PORT=5174"

powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%scripts\ui-control.ps1" -Action stop -ApiPort %API_PORT% -UiPort %UI_PORT%
exit /b %errorlevel%
