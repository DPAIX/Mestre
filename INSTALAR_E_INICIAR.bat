@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_RESULTADO=0"
echo MeuControlePC - preparar e iniciar automaticamente
echo A janela local mostrara o progresso. Configuracao e dados existentes serao preservados.
if not exist "%~dp0preparacao_autonoma.py" goto incompleto
if exist "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" (
  "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] < (3, 11))" >nul 2>nul
  if not errorlevel 1 goto existente
)
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" (
  "F:\MeuControlePC_v2\.venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] < (3, 11))" >nul 2>nul
  if not errorlevel 1 goto externo
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; sys.exit(sys.version_info[:2] < (3, 11))" >nul 2>nul
  if not errorlevel 1 goto py
)
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; sys.exit(sys.version_info[:2] < (3, 11))" >nul 2>nul
  if not errorlevel 1 goto python
)
where winget >nul 2>nul
if errorlevel 1 goto sem_python
echo Preparando Python 3.12 pelo instalador oficial...
winget install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" goto novo
goto sem_python
:existente
"%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
:externo
"F:\MeuControlePC_v2\.venv\Scripts\python.exe" "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
:py
py -3 "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
:python
python "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
:novo
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
:sem_python
set "MEUCONTROLEPC_RESULTADO=2"
echo Python nao foi localizado. Conclua o instalador oficial em https://www.python.org/downloads/windows/ e abra este arquivo novamente.
goto fim
:incompleto
set "MEUCONTROLEPC_RESULTADO=2"
echo Extraia o pacote completo antes de abrir este arquivo.
:fim
if not "%MEUCONTROLEPC_RESULTADO%"=="0" pause
exit /b %MEUCONTROLEPC_RESULTADO%
