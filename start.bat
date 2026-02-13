@echo off
REM Receipt Automation Dashboard - Windows Start Script
REM Run from project root so api.py finds python-service/app
cd /d "%~dp0"

echo.
echo Starting Receipt Automation Dashboard...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
pip install -r requirements.txt --quiet

REM Start API server in new window
echo Starting API server on http://localhost:8000...
start "Receipt API Server" python api.py

REM Wait a bit for API to start
timeout /t 3 /nobreak >nul

REM Start web server in new window
echo Starting web server on http://localhost:3000...
start "Receipt Web Server" python -m http.server 3000

REM Wait for web server to start
timeout /t 2 /nobreak >nul

echo.
echo Dashboard is ready!
echo.
echo Open your browser to: http://localhost:3000
echo API running at: http://localhost:8000
echo.
echo Close the terminal windows to stop the servers.
echo.
pause