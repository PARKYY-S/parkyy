@echo off
cd /d "%~dp0"
rem Saud's rule: nothing on C: - temp + pip cache stay in PARKYY's folder on D:
set "TEMP=%~dp0data\tmp"
set "TMP=%~dp0data\tmp"
set "PIP_CACHE_DIR=%~dp0data\tmp\pip-cache"
if not exist "%~dp0data\tmp" mkdir "%~dp0data\tmp"
title Connect PARKYY to your LG TV
echo.
echo  === Connect PARKYY to your LG TV ===
echo  1. Turn the TV ON and make sure it's on the same Wi-Fi as this laptop.
echo  2. Watch the TV - when it asks, press ALLOW / ACCEPT with the remote.
echo.
"venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check aiowebostv
"venv\Scripts\python.exe" -m tools.lgtv setup %1
echo.
echo  Tip: for "turn on the TV", switch on in the TV: Settings - General - Devices - "Turn on via Wi-Fi".
echo  Now restart PARKYY (RELOAD-BACKEND.bat) and say: "open YouTube on the TV".
pause
