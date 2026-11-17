@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.12 or newer first.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)

echo Installing or updating Forma dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Creating or updating the local SQLite database...
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto failed

echo Starting Forma at http://127.0.0.1:8000
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
exit /b %errorlevel%

:failed
echo Setup failed. Check the error above and try again.
pause
exit /b 1
