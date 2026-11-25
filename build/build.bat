
@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."

echo.
echo ========================================
echo          SYNAPSE BUILD SYSTEM
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found.
    pause
    exit /b 1
)

if not exist "Application\version.txt" (
    echo ERROR: Application\version.txt not found.
    pause
    exit /b 1
)

set "VERSION="
for /f "usebackq delims=" %%V in ("Application\version.txt") do set "VERSION=%%V"

echo Building Synapse version %VERSION%
echo.

".venv\Scripts\python.exe" -c "import re,sys; sys.exit(0 if re.fullmatch(r'\d+\.\d+\.\d+', sys.argv[1]) else 1)" "%VERSION%"
if errorlevel 1 (
    echo ERROR: Invalid version. Expected Major.Minor.Patch.
    pause
    exit /b 1
)

if not exist "build\launcher\Synapse.spec" (
    echo ERROR: PyInstaller spec not found.
    pause
    exit /b 1
)

if not exist "Application\updater_helper.py" (
    echo ERROR: updater_helper.py not found.
    pause
    exit /b 1
)

if not exist "Application\assets\synapse_logo.ico" (
    echo ERROR: Application icon not found.
    pause
    exit /b 1
)

echo Cleaning previous build output...

if exist "build\dist\Synapse" rmdir /s /q "build\dist\Synapse"
if exist "build\work\synapse" rmdir /s /q "build\work\synapse"

echo.
echo [1/2] Building Synapse...
echo.

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "build\dist" --workpath "build\work\synapse" "build\launcher\Synapse.spec"
if errorlevel 1 (
    echo.
    echo ERROR: Synapse build failed.
    pause
    exit /b 1
)

if not exist "build\dist\Synapse\Synapse.exe" (
    echo ERROR: Synapse.exe was not created.
    pause
    exit /b 1
)

if not exist "build\dist\Synapse\_internal\version.txt" (
    echo ERROR: version.txt was not bundled into the application.
    pause
    exit /b 1
)

echo.
echo [2/2] Building updater helper...
echo.

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name SynapseUpdater --distpath "build\dist\Synapse" --workpath "build\work\updater" --specpath "build\work\updater" "Application\updater_helper.py"
if errorlevel 1 (
    echo.
    echo ERROR: Updater helper build failed.
    pause
    exit /b 1
)

if not exist "build\dist\Synapse\SynapseUpdater.exe" (
    echo ERROR: SynapseUpdater.exe was not created.
    pause
    exit /b 1
)

echo.
echo ========================================
echo             BUILD COMPLETE
echo ========================================
echo.
echo Version: %VERSION%
echo.
echo Application:
echo build\dist\Synapse\
echo.
echo Installer script:
echo build\Synapse.iss
echo.
pause
exit /b 0
