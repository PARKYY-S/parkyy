@echo off
cd /d "%~dp0"
rem Saud's rule: nothing on C: - temp + pip cache stay in PARKYY's folder on D:
set "TEMP=%~dp0data\tmp"
set "TMP=%~dp0data\tmp"
set "PIP_CACHE_DIR=%~dp0data\tmp\pip-cache"
if not exist "%~dp0data\tmp" mkdir "%~dp0data\tmp"
title PARKYY studio setup
echo.
echo  === Setting up PARKYY's studio (websites, Blender, Android) ===
echo.
echo  [1/2] Installing website control (Playwright)...
"venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check playwright
if errorlevel 1 (
  echo  Install failed - check your internet and run this again.
  pause
  exit /b 1
)
echo  [2/2] PARKYY uses your installed Google Chrome, with its OWN separate profile
echo        (your normal Chrome, logins and history are not touched).
echo.
"venv\Scripts\python.exe" -c "from tools import studio; print(studio.studio_status())"
echo.
echo  Blender not found? Install it free from blender.org.
echo  Now restart PARKYY (RELOAD-BACKEND.bat).
pause
