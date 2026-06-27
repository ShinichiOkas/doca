@echo off
rem ====================================================================
rem Build script for Doca (Windows 11)
rem Note: This script is written in pure ASCII to prevent CP932 issues.
rem ====================================================================

echo [1/3] Checking virtual environment...
if exist .venv\Scripts\activate.bat (
    echo Activating .venv...
    call .venv\Scripts\activate.bat
) else (
    echo Warning: .venv not found. Running with global python environment.
)

echo [2/3] Checking and installing PyInstaller...
python -m pip install --upgrade pip
pip install pyinstaller

echo [3/3] Compiling to onefile executable using PyInstaller...
rem Excluding large unused scientific/GUI packages to keep binary small
pyinstaller --onefile ^
            --name doca ^
            --exclude-module numpy ^
            --exclude-module pandas ^
            --exclude-module matplotlib ^
            --exclude-module tkinter ^
            --exclude-module scipy ^
            --exclude-module sympy ^
            --exclude-module notebook ^
            --exclude-module IPython ^
            src/doca/__main__.py

if %ERRORLEVEL% equ 0 (
    echo =================================================
    echo Build SUCCESS!
    echo Executable generated at: dist\doca.exe
    echo =================================================
) else (
    echo =================================================
    echo Build FAILED with exit code %ERRORLEVEL%
    echo =================================================
)
pause
