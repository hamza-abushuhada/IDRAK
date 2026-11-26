@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found. Please install Python 3.10 or newer.
    echo Open README_AR.md for help.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=python"
)
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765/"
echo =========================================
echo      IDRAK Connect Lab - LOCAL ONLY
 echo =========================================
echo POS:          http://127.0.0.1:8765/pos
echo Online Store: http://127.0.0.1:8765/shop
echo Simulator:    http://127.0.0.1:8766/
echo Press Ctrl+C to stop.
echo.
%PYTHON_CMD% demo_server.py
pause
