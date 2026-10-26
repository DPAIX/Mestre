@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_PYTHON="
if exist "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" set "MEUCONTROLEPC_PYTHON=%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_PYTHON goto executar
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" set "MEUCONTROLEPC_PYTHON=F:\MeuControlePC_v2\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_PYTHON goto executar
where python >nul 2>nul
if errorlevel 1 goto sem_python
set "MEUCONTROLEPC_PYTHON=python"
:executar
set "PYTHONUTF8=1"
"%MEUCONTROLEPC_PYTHON%" "%~dp0reparar_conexao_9remote.py" --reverter
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
pause
exit /b %MEUCONTROLEPC_RESULTADO%
:sem_python
echo O Python do assistente nao foi localizado.
pause
exit /b 2
