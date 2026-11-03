@echo off
title PARKYY - installing the desktop layer
cd /d "%~dp0desktop"
set "ELECTRON_CACHE=%~dp0.electron-cache"
echo Downloading Electron (about 100 MB)...
node node_modules\electron\install.js
if not exist "node_modules\electron\dist\electron.exe" (
  echo.
  echo Electron download failed - send Claude a photo of this window.
  pause
  exit /b 1
)
echo Installed! Starting PARKYY...
call "%~dp0START-PARKYY.bat"
timeout /t 6
