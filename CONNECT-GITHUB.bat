@echo off
cd /d "%~dp0"
rem Saud's rule: nothing on C: - temp + pip cache stay in PARKYY's folder on D:
set "TEMP=%~dp0data\tmp"
set "TMP=%~dp0data\tmp"
set "PIP_CACHE_DIR=%~dp0data\tmp\pip-cache"
if not exist "%~dp0data\tmp" mkdir "%~dp0data\tmp"
title Connect PARKYY to GitHub
echo.
echo  === Connect PARKYY to GitHub ===
echo  Paste the GitHub token Claude made for you (right-click to paste). It stays hidden.
echo.
"venv\Scripts\python.exe" -m tools.github connect
echo.
echo  Now restart PARKYY (RELOAD-BACKEND.bat) and ask: "show my GitHub repos".
pause
