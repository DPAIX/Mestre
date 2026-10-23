@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "MEUCONTROLEPC_MANUTENCAO=%~dp0manutencao_assistente.py"
if not exist "%MEUCONTROLEPC_MANUTENCAO%" goto incompleto
if exist "%~dp0.venv\Scripts\python.exe" goto python_codigo
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" goto python_externo
where py >nul 2>nul
if not errorlevel 1 goto python_py
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Python nao encontrado. Instale Python 3.11 ou superior e execute este arquivo novamente.
goto falha

:python_codigo
"%~dp0.venv\Scripts\python.exe" "%MEUCONTROLEPC_MANUTENCAO%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:python_externo
"F:\MeuControlePC_v2\.venv\Scripts\python.exe" "%MEUCONTROLEPC_MANUTENCAO%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:python_py
py -3 "%MEUCONTROLEPC_MANUTENCAO%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:python_path
python "%MEUCONTROLEPC_MANUTENCAO%" --codigo "%~dp0." --env "F:\MeuControlePC_v2\.env"
goto resultado

:resultado
if errorlevel 1 goto falha
echo Manutencao concluida. O assistente foi iniciado; o inicio automatico existente foi preservado.
pause
exit /b 0

:incompleto
echo Atualize todas as fontes do pacote antes de executar esta manutencao.
:falha
echo A manutencao nao foi concluida. Configuracao, dados, modelos e fontes foram preservados.
pause
exit /b 2
