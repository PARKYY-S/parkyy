@echo off
cd /d "%~dp0"
set PARKYY_LAN=1
echo Starting PARKYY backend (with stay-awake)...
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
