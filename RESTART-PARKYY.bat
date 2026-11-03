@echo off
rem Restarts PARKYY so updates (like the pet) load. Double-click me.
cd /d "%~dp0desktop"
taskkill /im electron.exe /f
timeout /t 2 /nobreak
start "" "node_modules\electron\dist\electron.exe" .
