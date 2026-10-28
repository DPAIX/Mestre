@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0AMBIENTE_F.bat"
if errorlevel 1 goto falha_f
set "MEUCONTROLEPC_RESULTADO=0"
echo MeuControlePC - preparar e iniciar automaticamente
echo A janela local mostrara o progresso. Configuracao e dados existentes serao preservados.
if not exist "%~dp0preparacao_autonoma.py" goto incompleto
if exist "F:\MeuControlePC_v2\aplicativo\.venv\Scripts\python.exe" goto instalado_f
if exist "F:\MeuControlePC_v2\python\python.exe" goto python_f
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
goto sem_python
:instalado_f
"F:\MeuControlePC_v2\aplicativo\.venv\Scripts\python.exe" "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
:python_f
"F:\MeuControlePC_v2\python\python.exe" "%~dp0preparacao_autonoma.py"
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto fim
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
:sem_python
set "MEUCONTROLEPC_RESULTADO=2"
echo Python 3.11+ nao localizado. Instale o Python oficial em F:\MeuControlePC_v2\python e abra novamente.
echo Este pacote nao usa instaladores com destino padrao em C:.
goto fim
:falha_f
set "MEUCONTROLEPC_RESULTADO=2"
goto fim
:incompleto
set "MEUCONTROLEPC_RESULTADO=2"
echo Extraia o pacote completo antes de abrir este arquivo.
:fim
if not "%MEUCONTROLEPC_RESULTADO%"=="0" pause
exit /b %MEUCONTROLEPC_RESULTADO%
