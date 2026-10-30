@echo off
cd /d "%~dp0"
if exist "%~dp0releases\ControlGestual-V5.3\ControlGestual-V5.3.exe" (
  start "" "%~dp0releases\ControlGestual-V5.3\ControlGestual-V5.3.exe"
) else (
  start "" pyw -3 "%~dp0desktop_app.py"
)
