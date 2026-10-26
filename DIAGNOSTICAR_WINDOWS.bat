@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_REDE_PYTHON="
if exist "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" set "MEUCONTROLEPC_REDE_PYTHON=%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_REDE_PYTHON goto executar
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" set "MEUCONTROLEPC_REDE_PYTHON=F:\MeuControlePC_v2\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_REDE_PYTHON goto executar
where python >nul 2>nul
if errorlevel 1 goto sem_python
set "MEUCONTROLEPC_REDE_PYTHON=python"
:executar
if not exist "%~dp0ajustar_autodeteccao_proxy.py" goto incompleto
if not exist "%~dp0diagnosticar_ncsi.py" goto incompleto
echo Consulta finita, sem alteracao de proxy ou de rede.
echo Conferindo em que etapa o componente de proxy deixa de responder...
"%MEUCONTROLEPC_REDE_PYTHON%" -I -S "%~dp0ajustar_autodeteccao_proxy.py" --diagnosticar
echo.
echo Conferindo as sondas publicas de conectividade do Windows...
"%MEUCONTROLEPC_REDE_PYTHON%" -I -S "%~dp0diagnosticar_ncsi.py"
set "MEUCONTROLEPC_REDE_RESULTADO=%ERRORLEVEL%"
echo Envie as linhas de resultado desta janela. Elas nao incluem enderecos ou chaves.

echo.
pause
exit /b %MEUCONTROLEPC_REDE_RESULTADO%
:sem_python
echo O Python do assistente nao foi localizado neste computador.
pause
exit /b 2
:incompleto
echo Extraia todos os arquivos do ZIP em uma pasta antes de abrir este arquivo.
pause
exit /b 2
