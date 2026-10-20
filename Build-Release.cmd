@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Build-Release.ps1"
if errorlevel 1 (
    echo.
    echo BUILD FAILED. Do not deploy the old files in Release.
    pause
    exit /b 1
)
echo.
pause
