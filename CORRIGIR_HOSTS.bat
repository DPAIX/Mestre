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
if not exist "%~dp0corrigir_hosts_spotify.py" goto incompleto
echo Operacao limitada ao bloqueio de wl.spotify.com, com backup local.
echo Para editar o hosts do Windows, use Executar como administrador neste arquivo.
"%MEUCONTROLEPC_REDE_PYTHON%" -I -S "%~dp0corrigir_hosts_spotify.py" --corrigir
set "MEUCONTROLEPC_REDE_RESULTADO=%ERRORLEVEL%"

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
