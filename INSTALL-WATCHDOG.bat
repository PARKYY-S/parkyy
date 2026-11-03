@echo off
cd /d "%~dp0"
echo Installing the PARKYY watchdog (starts with Windows, lets your phone wake PARKYY)...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%STARTUP%\PARKYY-watchdog.vbs" echo CreateObject("WScript.Shell").Run """%~dp0watchdog-run.vbs""", 0, False
wscript "%~dp0watchdog-run.vbs"
echo.
echo Done. The watchdog is running now and will start automatically when Windows starts.
echo To remove it later, delete PARKYY-watchdog.vbs from your Startup folder.
pause
