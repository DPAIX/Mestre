@echo off
setlocal EnableExtensions
chcp 65001 >nul
if "%~1"=="" if exist "%~dp0INSTALAR_E_INICIAR.bat" goto preparar_automatico
set "MEUCONTROLEPC_CODIGO=C:\Users\Mestre\Documents\GitHub\Mestre"
set "MEUCONTROLEPC_CONFIGURACAO=F:\MeuControlePC_v2"
if not exist "%MEUCONTROLEPC_CODIGO%\redirecionar_assistente.py" goto codigo_ausente
if exist "%MEUCONTROLEPC_CODIGO%\.venv\Scripts\python.exe" goto python_codigo
if exist "%MEUCONTROLEPC_CONFIGURACAO%\.venv\Scripts\python.exe" goto python_existente
where py >nul 2>nul
if not errorlevel 1 goto python_py
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Python nao encontrado. Use Python 3.11+ ou reaproveite a .venv da instalacao existente.
exit /b 2

:python_codigo
"%MEUCONTROLEPC_CODIGO%\.venv\Scripts\python.exe" "%MEUCONTROLEPC_CODIGO%\redirecionar_assistente.py" %*
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto finalizar

:python_existente
"%MEUCONTROLEPC_CONFIGURACAO%\.venv\Scripts\python.exe" "%MEUCONTROLEPC_CODIGO%\redirecionar_assistente.py" %*
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto finalizar

:python_py
py -3 "%MEUCONTROLEPC_CODIGO%\redirecionar_assistente.py" %*
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto finalizar

:python_path
python "%MEUCONTROLEPC_CODIGO%\redirecionar_assistente.py" %*
set "MEUCONTROLEPC_RESULTADO=%ERRORLEVEL%"
goto finalizar

:codigo_ausente
echo Codigo atualizado nao encontrado em %MEUCONTROLEPC_CODIGO%.
echo Atualize essa pasta e mantenha o .env e os dados na instalacao externa.
exit /b 2

:finalizar
exit /b %MEUCONTROLEPC_RESULTADO%

:preparar_automatico
call "%~dp0INSTALAR_E_INICIAR.bat"
exit /b %ERRORLEVEL%
