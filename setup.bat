@echo off
REM SF-NVR Setup Script for Windows
REM This script sets up the virtual environment and installs dependencies

echo ================================================
echo   SF-NVR - Network Video Recorder Setup
echo ================================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%

REM Check for FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Warning: FFmpeg is not installed or not in PATH
    echo FFmpeg is required for video processing
    echo.
    echo Download FFmpeg from: https://ffmpeg.org/download.html
    echo Add it to your system PATH
    echo.
    choice /C YN /M "Continue without FFmpeg"
    if errorlevel 2 exit /b 1
) else (
    echo Found FFmpeg
)

REM Create virtual environment
echo.
echo Creating virtual environment...
if exist venv (
    echo Virtual environment already exists
    choice /C YN /M "Recreate it"
    if errorlevel 1 (
        rmdir /s /q venv
        python -m venv venv
    )
) else (
    python -m venv venv
)

REM Activate virtual environment
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo Installing Python dependencies...
pip install -r requirements.txt

REM Create .env if it doesn't exist
if not exist .env (
    echo.
    echo Creating .env file...
    copy .env.example .env
    echo Created .env - you can edit this file to set camera credentials
)

REM Success message
echo.
echo ================================================
echo   Setup Complete!
echo ================================================
echo.
echo To start the NVR:
echo   1. Activate the virtual environment:
echo      venv\Scripts\activate.bat
echo.
echo   2. Run the application:
echo      python main.py
echo.
echo   3. Open your browser to:
echo      http://localhost:8080
echo.
echo To deactivate the virtual environment:
echo   deactivate
echo.
echo Configuration:
echo   - Edit config\config.yaml for settings
echo   - Edit .env for camera credentials
echo.
pause