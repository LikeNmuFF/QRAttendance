@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    "%LocalAppData%\Programs\Python\Python313\python.exe" -m venv .venv
  ) else (
    py -3.13 -m venv .venv
  )
  if errorlevel 1 (
    echo Install 64-bit Python 3.13, then run this file again.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip --disable-pip-version-check install --no-index --find-links=offline\wheels -r offline\requirements-lock.txt
if errorlevel 1 (
  echo Offline installation failed. This package targets 64-bit Windows and Python 3.13.
  pause
  exit /b 1
)
echo Offline setup complete. Double-click start.cmd to run QR Attendance.
pause
