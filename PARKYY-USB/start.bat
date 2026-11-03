@echo off
title PARKYY
cd /d "%~dp0"

rem PARKYY decides by itself what to use:
rem   internet + keys.env  -> free cloud brains (instant start)
rem   no internet          -> offline Hermes from the models folder (parkyy.ps1 starts llamafile only when needed)

rem The little PARKYY pet walks on your windows. Turn it off:  set PARKYY_PET=0  before running this file.
if not "%PARKYY_PET%"=="0" if exist "%~dp0pet.ps1" (
  del "%~dp0pet-state.txt" >nul 2>&1
  start "" /b powershell -NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0pet.ps1" -Root "%~dp0." 
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0parkyy.ps1" -Port 8080

rem safety net: make sure no brain is left running on this PC
for %%f in (llamafile*.exe) do taskkill /im "%%f" /f >nul 2>&1
