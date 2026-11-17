@echo off
title Aid Station Resource Management Simulator - OS Group 2
cls
echo ======================================================================
echo    Aid Station Resource Management Simulator (OS Group 2)
echo    Core Concepts: Concurrency, Semaphores, & Deadlock Avoidance
echo ======================================================================
echo.

set PY_CMD=

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PY_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto RUN
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=py
    goto RUN
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=python
    goto RUN
)

echo [ERROR] Python not found in PATH or standard directory!
pause
exit /b 1

:RUN
echo [OK] Using Python: %PY_CMD%
echo [INFO] Starting Web Server on http://localhost:5000 ...
echo [INFO] Press Ctrl+C in this terminal window to stop the server.
echo.
start http://localhost:5000
%PY_CMD% app.py 5000
pause
