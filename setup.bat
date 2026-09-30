@echo off
rem Set up Roshan Mustaqbil on this Windows PC: double-click this file.
rem See scripts\setup.ps1 for what it does, and for unattended options.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
rem Setup explains its own stops (exit code 2); anything else is shown here.
if errorlevel 1 if not errorlevel 2 (
    echo.
    echo Setup couldn't run. The message above says why.
    pause
)
