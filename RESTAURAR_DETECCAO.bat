@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0ajustar_autodeteccao_proxy.py" goto incompleto
set "MEUCONTROLEPC_PROXY_PYTHON="
if exist "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" set "MEUCONTROLEPC_PROXY_PYTHON=%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_PROXY_PYTHON goto executar
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" set "MEUCONTROLEPC_PROXY_PYTHON=F:\MeuControlePC_v2\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_PROXY_PYTHON goto executar
where python >nul 2>nul
if errorlevel 1 goto sem_python
set "MEUCONTROLEPC_PROXY_PYTHON=python"
:executar
echo Restaurando a deteccao automatica a partir do registro local deste teste.
"%MEUCONTROLEPC_PROXY_PYTHON%" -I -S "%~dp0ajustar_autodeteccao_proxy.py" --restaurar
set "MEUCONTROLEPC_PROXY_RESULTADO=%ERRORLEVEL%"
pause
exit /b %MEUCONTROLEPC_PROXY_RESULTADO%
:sem_python
echo O Python do assistente nao foi localizado neste computador.
pause
exit /b 2
:incompleto
echo Extraia todos os arquivos do ZIP em uma pasta antes de abrir este arquivo.
pause
exit /b 2
