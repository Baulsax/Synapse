
@echo off
setlocal

title Synapse Build

cd /d "%~dp0\.."

echo.
echo ========================================
echo          SYNAPSE BUILD SYSTEM
echo ========================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Python virtual environment not found.
    echo Expected: %CD%\.venv\Scripts\activate.bat
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller is not installed in the virtual environment.
    echo Install it with: pip install pyinstaller
    pause
    exit /b 1
)

if not exist "Application\version.txt" (
    echo ERROR: Could not find Application\version.txt
    pause
    exit /b 1
)

python -c "import re; from pathlib import Path; v=Path('Application/version.txt').read_text(encoding='utf-8').strip(); exit(0 if re.fullmatch(r'\d+\.\d+\.\d+', v) else 1)"
if errorlevel 1 (
    echo ERROR: Application\version.txt must contain a valid Major.Minor.Patch version.
    echo Example: 0.1.0
    pause
    exit /b 1
)

for /f "usebackq delims=" %%V in ("Application\version.txt") do set "APP_VERSION=%%V"

if not exist "build\launcher\Synapse.spec" (
    echo ERROR: Could not find build\launcher\Synapse.spec
    pause
    exit /b 1
)

if not exist "Application\updater_helper.py" (
    echo ERROR: Could not find Application\updater_helper.py
    pause
    exit /b 1
)

if not exist "Application\assets\synapse_logo.ico" (
    echo ERROR: Could not find Application\assets\synapse_logo.ico
    pause
    exit /b 1
)

echo.
echo Building Synapse version %APP_VERSION%
echo.

echo Cleaning previous build output...
echo.

if exist "build\dist\Synapse" (
    rmdir /s /q "build\dist\Synapse"
)

if exist "build\work\synapse" (
    rmdir /s /q "build\work\synapse"
)

if exist "build\work\updater" (
    rmdir /s /q "build\work\updater"
)

echo.
echo [1/2] Building Synapse...
echo.

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --distpath "build\dist" ^
    --workpath "build\work\synapse" ^
    "build\launcher\Synapse.spec"

if errorlevel 1 (
    echo.
    echo ERROR: Synapse build failed.
    pause
    exit /b 1
)

if not exist "build\dist\Synapse\Synapse.exe" (
    echo.
    echo ERROR: Synapse.exe was not created.
    pause
    exit /b 1
)

if not exist "build\dist\Synapse\version.txt" (
    echo.
    echo ERROR: version.txt was not bundled into the application.
    pause
    exit /b 1
)

echo.
echo [2/2] Building Synapse updater helper...
echo.

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "SynapseUpdater" ^
    --icon "Application\assets\synapse_logo.ico" ^
    --distpath "build\dist\Synapse" ^
    --workpath "build\work\updater" ^
    --specpath "build\launcher" ^
    "Application\updater_helper.py"

if errorlevel 1 (
    echo.
    echo ERROR: Updater helper build failed.
    pause
    exit /b 1
)

if not exist "build\dist\Synapse\SynapseUpdater.exe" (
    echo.
    echo ERROR: SynapseUpdater.exe was not created.
    pause
    exit /b 1
)

echo.
echo Verifying final build...
echo.

for %%F in (
    "build\dist\Synapse\Synapse.exe"
    "build\dist\Synapse\SynapseUpdater.exe"
    "build\dist\Synapse\version.txt"
) do (
    if not exist "%%~F" (
        echo ERROR: Missing build output: %%~F
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo             BUILD COMPLETE
echo ========================================
echo.
echo Version: %APP_VERSION%
echo.
echo Synapse:
echo   build\dist\Synapse\Synapse.exe
echo.
echo Updater:
echo   build\dist\Synapse\SynapseUpdater.exe
echo.
echo This folder is ready to be packaged by
echo the Inno Setup installer.
echo.

pause
exit /b 0
