@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute instalar_windows.bat primeiro.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" "configurar_telegram.py" --verificar
if errorlevel 1 (
  echo.
  echo O bot Telegram nao pode ser iniciado sem token valido.
  echo Abrindo assistente para configurar sem revelar o token...
  call "%~dp0configurar_telegram.bat"
  ".venv\Scripts\python.exe" "configurar_telegram.py" --verificar
  if errorlevel 1 (
    echo Configure o Telegram antes de tentar novamente.
    echo Para usar apenas o painel, execute iniciar_somente_painel.bat
    pause
    exit /b 2
  )
)
".venv\Scripts\python.exe" "assistente_pc.py"
if errorlevel 1 (
 echo O bot nao iniciou. Leia o erro acima e revise a configuracao.
 pause
)
