@echo off
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo First run: preparing the program, please wait...
    py -3 -m venv .venv 2>nul || python -m venv .venv 2>nul || goto nopython
)

.venv\Scripts\python -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing Flask, please wait...
    .venv\Scripts\python -m pip install -q --disable-pip-version-check flask || goto noflask
)

echo.
echo   SmartCare is running at http://127.0.0.1:5000
echo   Keep this window open while using the site. Close it to stop the program.
echo.
rem Open the browser a few seconds later, once the server is ready.
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000"
.venv\Scripts\python app.py
pause
exit /b

:nopython
echo.
echo   Python 3 is not installed.
echo   Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo   then run this file again.
echo.
pause
exit /b 1

:noflask
echo.
echo   Could not install Flask. Check the internet connection and run this file again.
echo.
pause
exit /b 1
