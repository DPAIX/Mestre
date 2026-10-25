@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_ENV=F:\MeuControlePC_v2\.env"
set "MEUCONTROLEPC_DADOS=F:\MeuControlePC_v2\dados"
echo Retomada de Ollama, 9Router, Gemini e agentes. Encerre o bot antes de preparar o servico.
echo Dependencias, Telegram e inicio automatico ja preparados serao preservados.
if not exist "%~dp0configuracao_assistente.py" goto incompleto
if exist "%~dp0.venv\Scripts\python.exe" goto codigo
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" goto externo
where py >nul 2>nul
if not errorlevel 1 goto python_py
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Instale Python 3.11 ou superior e atualize as fontes completas.
goto fim
:codigo
"%~dp0.venv\Scripts\python.exe" "%~dp0configuracao_assistente.py" --retomar
goto fim
:externo
"F:\MeuControlePC_v2\.venv\Scripts\python.exe" "%~dp0configuracao_assistente.py" --retomar
goto fim
:python_py
py -3 "%~dp0configuracao_assistente.py" --retomar
goto fim
:python_path
python "%~dp0configuracao_assistente.py" --retomar
goto fim
:incompleto
echo Copie o pacote completo antes de abrir o gerenciador.
:fim
pause
