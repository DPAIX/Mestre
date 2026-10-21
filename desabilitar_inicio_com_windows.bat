@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
 ".venv\Scripts\python.exe" startup_windows.py --desativar
) else (
 py -3 startup_windows.py --desativar
)
pause
