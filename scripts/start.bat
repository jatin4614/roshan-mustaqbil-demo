@echo off
rem Start Roshan Mustaqbil on this PC (the desktop shortcut runs this).
rem
rem   scripts\start.bat [dev-tunnel-id]
rem
rem With demo data loaded, adds today's check-ins and check-outs so far. Checks
rem the data, starts the app on http://127.0.0.1:8001 (RM_PORT changes the
rem port) in its own window and, given a dev tunnel ID (or RM_TUNNEL_ID),
rem shares it through that tunnel in a second window. Keep the windows open
rem while the app is in use; close them to stop it.
setlocal
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
set "TUNNEL=%~1"
if "%TUNNEL%"=="" set "TUNNEL=%RM_TUNNEL_ID%"
set "PORT=%RM_PORT%"
if "%PORT%"=="" set "PORT=8001"

if not exist "%PY%" (
    echo Can't find %PY%. Set up the app first: double-click setup.bat.
    pause
    exit /b 1
)

echo.
echo  Roshan Mustaqbil
echo  ---------------
echo  Adding today's demo check-ins so far (only if demo data is loaded)...
"%PY%" manage.py seed_youth_centre_demo --top-up
echo.
echo  Checking the data...
"%PY%" manage.py review_rm
if errorlevel 1 (
    echo.
    echo  The data check found a problem, listed above. The app will still start.
)

netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if errorlevel 1 (
    start "Roshan Mustaqbil app - keep open" cmd /k ""%PY%" manage.py runserver 0.0.0.0:%PORT% --noreload"
) else (
    echo.
    echo  The app is already running on port %PORT%.
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
start "Roshan Mustaqbil public link - keep open" cmd /k "devtunnel host %TUNNEL%"

:open
echo.
echo  Opening the app...
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:%PORT%/
echo  Ready. Sign in as admin.
timeout /t 5 >nul
endlocal
