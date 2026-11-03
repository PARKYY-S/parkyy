@echo off
cd /d "%~dp0"
echo Reloading PARKYY backend...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reload.ps1"
