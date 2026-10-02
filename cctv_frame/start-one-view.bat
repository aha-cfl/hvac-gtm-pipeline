@echo off
REM Visual Radio - one-view template. Double-click to start; close this window to stop.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
echo Installing the two Python packages it needs (first run only takes a minute)...
%PY% -m pip install --quiet -r requirements.txt
if errorlevel 1 (echo. & echo Python is missing. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
echo.
echo Checking the live camera...
%PY% web.py --one --check
echo.
echo Starting Visual Radio in your browser. Keep this window open; close it to stop.
%PY% web.py --one --open
pause
