@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0diagnosticar_conexao_telegram.py" goto incompleto
if not exist "%~dp0encerrar_teste_telegram.py" goto incompleto
if not exist "%~dp0controlar_instancia_preparacao.py" goto incompleto
if not exist "%~dp0instancia_assistente.py" goto incompleto
set "MEUCONTROLEPC_DIAG_PYTHON="
if exist "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" set "MEUCONTROLEPC_DIAG_PYTHON=%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_DIAG_PYTHON goto executar
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" set "MEUCONTROLEPC_DIAG_PYTHON=F:\MeuControlePC_v2\.venv\Scripts\python.exe"
if defined MEUCONTROLEPC_DIAG_PYTHON goto executar
where python >nul 2>nul
if errorlevel 1 goto sem_python
set "MEUCONTROLEPC_DIAG_PYTHON=python"
:executar
set "PYTHONUTF8=1"
echo Conferindo somente a consulta de teste anterior...
"%MEUCONTROLEPC_DIAG_PYTHON%" "%~dp0encerrar_teste_telegram.py" --confirmar
echo Consultando a conexao publica do Telegram...
"%MEUCONTROLEPC_DIAG_PYTHON%" "%~dp0diagnosticar_conexao_telegram.py" --salvar
set "MEUCONTROLEPC_DIAG_RESULTADO=%ERRORLEVEL%"
if not "%MEUCONTROLEPC_DIAG_RESULTADO%"=="0" goto falha
echo Resultado salvo em RESULTADO_TELEGRAM.txt.
start "" "%SYSTEMROOT%\System32\notepad.exe" "%~dp0RESULTADO_TELEGRAM.txt"
exit /b 0
:falha
echo A consulta nao foi concluida. Copie apenas a mensagem DIAGNOSTICO exibida acima.
pause
exit /b %MEUCONTROLEPC_DIAG_RESULTADO%
:sem_python
echo O Python do assistente nao foi localizado neste computador.
pause
exit /b 2
:incompleto
echo Extraia todos os arquivos do ZIP em uma pasta antes de abrir DIAGNOSTICAR_TELEGRAM.bat.
pause
exit /b 2
