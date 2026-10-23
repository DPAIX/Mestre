@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_PREPARADOR=%~dp0preparar_inicio_automatico.py"
if not exist "%MEUCONTROLEPC_PREPARADOR%" goto incompleto
if exist "%~dp0.venv\Scripts\python.exe" goto python_codigo
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" goto python_externo
where py >nul 2>nul
if not errorlevel 1 goto python_py
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Python nao encontrado. Instale Python 3.11 ou superior e execute este arquivo novamente.
goto falha

:python_codigo
"%~dp0.venv\Scripts\python.exe" "%MEUCONTROLEPC_PREPARADOR%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:python_externo
"F:\MeuControlePC_v2\.venv\Scripts\python.exe" "%MEUCONTROLEPC_PREPARADOR%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:python_py
py -3 "%MEUCONTROLEPC_PREPARADOR%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:python_path
python "%MEUCONTROLEPC_PREPARADOR%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:resultado
if errorlevel 1 goto falha
echo Preparacao concluida. O assistente inicia agora e nos proximos logons.
pause
exit /b 0

:incompleto
echo Atualize todas as fontes do pacote antes de executar esta preparacao.
:falha
echo A preparacao nao foi concluida. Nenhum dado ou arquivo .env foi apagado.
pause
exit /b 2
