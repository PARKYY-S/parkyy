@echo off
title PARKYY - publish to GitHub
cd /d "%~dp0"
rem Uploads PARKYY's code (never your keys or personal data) to a PRIVATE GitHub repo, then asks before making it public.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\publish_github.ps1"
echo.
pause
