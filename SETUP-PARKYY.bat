@echo off
title PARKYY setup
cd /d "%~dp0"
rem Saud's rule: nothing on C: - temp + pip cache stay in PARKYY's folder on D:
set "TEMP=%~dp0data\tmp"
set "TMP=%~dp0data\tmp"
set "PIP_CACHE_DIR=%~dp0data\tmp\pip-cache"
if not exist "%~dp0data\tmp" mkdir "%~dp0data\tmp"
echo ============================================
echo   PARKYY setup - built into your desktop
echo ============================================

where node >nul 2>nul
if not errorlevel 1 goto havenode
if not exist "D:\Downloads\node-v24.21.0-x64.msi" goto nonode
echo Installing Node.js - click Yes if Windows asks...
msiexec /i "D:\Downloads\node-v24.21.0-x64.msi" /passive
set "PATH=%PATH%;C:\Program Files\nodejs"
goto havenode
:nonode
echo Node.js is missing. Install it from nodejs.org, then run this again.
pause
exit /b 1
:havenode

echo.
echo [1/3] Installing PARKYY's Python packages...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Python packages failed - send Claude a photo of this window. & pause & exit /b 1 )

echo.
echo [2/3] Installing the desktop layer (about 150 MB, saved on D:)...
set "npm_config_cache=%~dp0.npm-cache"
set "ELECTRON_CACHE=%~dp0.electron-cache"
cd desktop
call npm install --no-fund --no-audit
if errorlevel 1 ( echo Desktop layer install failed - send Claude a photo of this window. & pause & exit /b 1 )
if not exist "node_modules\electron\dist\electron.exe" echo Downloading Electron itself...
if not exist "node_modules\electron\dist\electron.exe" node node_modules\electron\install.js
if not exist "node_modules\electron\dist\electron.exe" ( echo Electron download failed - send Claude a photo of this window. & pause & exit /b 1 )
cd ..

echo.
echo [3/3] Starting PARKYY...
call "%~dp0START-PARKYY.bat"
echo Done! PARKYY now starts with Windows. Press Ctrl+Space any time.
timeout /t 8
