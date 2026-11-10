@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install_offline.cmd first to prepare the local Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u python\server.py
if errorlevel 1 pause
