@echo off
cd /d "%~dp0"
rem Saud's rule: nothing on C: - temp + pip cache stay in PARKYY's folder on D:
set "TEMP=%~dp0data\tmp"
set "TMP=%~dp0data\tmp"
set "PIP_CACHE_DIR=%~dp0data\tmp\pip-cache"
if not exist "%~dp0data\tmp" mkdir "%~dp0data\tmp"
title Connect PARKYY to Gmail + Google Calendar
echo.
echo  === Connect PARKYY to your Gmail + Google Calendar ===
echo.
if not exist "google-credentials.json" (
  echo  Missing google-credentials.json in this folder.
  echo  Follow the steps PARKYY/Claude gave you to download it from Google Cloud,
  echo  rename it to google-credentials.json and put it here:
  echo    %~dp0
  echo.
  pause
  exit /b 1
)
echo  [1/2] Installing Google libraries (one time)...
"venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check google-api-python-client google-auth-oauthlib google-auth-httplib2
if errorlevel 1 (
  echo  Install failed - check your internet and run this again.
  pause
  exit /b 1
)
echo  [2/2] A browser window will open. Sign in with your Google account and press Allow.
echo        If Google says "Google hasn't verified this app", click Continue - it's your own app.
echo.
"venv\Scripts\python.exe" -m tools.gsuite connect
echo.
echo  Now restart PARKYY (RELOAD-BACKEND.bat) and ask: "PARKYY, check my inbox".
pause
