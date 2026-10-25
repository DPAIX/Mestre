@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_ENV=F:\MeuControlePC_v2\.env"
set "MEUCONTROLEPC_DADOS=F:\MeuControlePC_v2\dados"
if not exist "%~dp0configurar_gemini.py" goto incompleto
if exist "%~dp0.venv\Scripts\python.exe" goto codigo
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" goto externo
where py >nul 2>nul
if not errorlevel 1 goto python_py
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Instale Python 3.11 ou superior e atualize as fontes completas.
goto fim
:codigo
"%~dp0.venv\Scripts\python.exe" "%~dp0configurar_gemini.py"
goto fim
:externo
"F:\MeuControlePC_v2\.venv\Scripts\python.exe" "%~dp0configurar_gemini.py"
goto fim
:python_py
py -3 "%~dp0configurar_gemini.py"
goto fim
:python_path
python "%~dp0configurar_gemini.py"
goto fim
:incompleto
echo Copie o pacote completo antes de abrir o gerenciador.
:fim
pause
