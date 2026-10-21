@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Ambiente virtual nao encontrado. Execute instalar_windows.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "verificacao_ambiente.py"
if errorlevel 1 (
  echo [ERRO] A verificacao nao foi concluida. Veja a mensagem acima.
)
pause
