@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Esta opcao criara um atalho de inicializacao APOS o login do seu usuario Windows.
echo Nao e um servico e nao inicia na tela de bloqueio, antes do login.
choice /m "Voce autoriza iniciar o MeuControlePC automaticamente apos fazer login no Windows"
if errorlevel 2 exit /b 1
if exist ".venv\Scripts\python.exe" (
 ".venv\Scripts\python.exe" startup_windows.py --ativar
) else (
 py -3 startup_windows.py --ativar
)
pause
