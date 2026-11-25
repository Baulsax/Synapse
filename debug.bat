
@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Python virtual environment not found.
    echo Expected: %~dp0.venv\Scripts\activate.bat
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

cd /d "%~dp0Application"

echo.
echo Starting Synapse in development mode...
echo.

python main.py

set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Synapse exited with code %EXIT_CODE%.
pause

exit /b %EXIT_CODE%
