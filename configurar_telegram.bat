@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "configurar_telegram.py"
) else (
  py -3 "configurar_telegram.py"
)
if errorlevel 1 echo Configuracao nao concluida. O .env existente foi mantido.
pause
