@echo off
rem Start the Roshan Mustaqbil demo on this PC.
rem
rem   scripts\start_demo.bat [dev-tunnel-id]
rem
rem Adds today's check-ins so far, checks the data, starts the app on
rem http://127.0.0.1:8001 in its own window and, given a dev tunnel ID (or
rem RM_TUNNEL_ID), shares it through that tunnel in a second window. Keep both
rem windows open during the demo; close them to stop.
setlocal
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
set "TUNNEL=%~1"
if "%TUNNEL%"=="" set "TUNNEL=%RM_TUNNEL_ID%"

if not exist "%PY%" (
    echo Can't find %PY%. Set up the app first: see README.md, "Local demo".
    pause
    exit /b 1
)

echo.
echo  Roshan Mustaqbil demo
echo  ---------------------
echo  Adding today's check-ins so far...
"%PY%" manage.py seed_youth_centre_demo
echo.
echo  Checking the data...
"%PY%" manage.py review_rm
if errorlevel 1 (
    echo.
    echo  The data check found a problem, listed above. The demo will still start.
)

netstat -ano | findstr /r /c:":8001 .*LISTENING" >nul
if errorlevel 1 (
    start "RM demo server - keep open" cmd /k ""%PY%" manage.py runserver 0.0.0.0:8001 --noreload"
) else (
    echo.
    echo  The app is already running on port 8001.
)

if "%TUNNEL%"=="" goto open
tasklist /fi "imagename eq devtunnel.exe" | findstr /i devtunnel >nul
if not errorlevel 1 (
    echo  The public link is already running.
    goto open
)
where devtunnel >nul 2>nul
if errorlevel 1 (
    echo  Can't find devtunnel, so there's no public link. Install it with: winget install Microsoft.devtunnel
    goto open
)
start "RM public link - keep open" cmd /k "devtunnel host %TUNNEL%"

:open
echo.
echo  Opening the app...
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:8001/
echo  Ready. Sign in as admin.
timeout /t 5 >nul
endlocal
