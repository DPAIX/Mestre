@echo off
setlocal EnableExtensions
chcp 65001 >nul
if not exist "%~dp0preparar_27b_leve.py" goto incompleto
if exist "%~dp0.venv\Scripts\python.exe" goto python_local
if exist "%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" goto python_instalado
if exist "F:\MeuControlePC_v2\.venv\Scripts\python.exe" goto python_externo
where py >nul 2>nul
if not errorlevel 1 goto python_py
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Python nao encontrado. Use a instalacao existente do assistente.
set "MCP_RESULTADO=2"
goto fim
:python_local
"%~dp0.venv\Scripts\python.exe" "%~dp0preparar_27b_leve.py" --restaurar
set "MCP_RESULTADO=%ERRORLEVEL%"
goto fim
:python_instalado
"%USERPROFILE%\Documents\GitHub\Mestre\.venv\Scripts\python.exe" "%~dp0preparar_27b_leve.py" --restaurar
set "MCP_RESULTADO=%ERRORLEVEL%"
goto fim
:python_externo
"F:\MeuControlePC_v2\.venv\Scripts\python.exe" "%~dp0preparar_27b_leve.py" --restaurar
set "MCP_RESULTADO=%ERRORLEVEL%"
goto fim
:python_py
py -3 "%~dp0preparar_27b_leve.py" --restaurar
set "MCP_RESULTADO=%ERRORLEVEL%"
goto fim
:python_path
python "%~dp0preparar_27b_leve.py" --restaurar
set "MCP_RESULTADO=%ERRORLEVEL%"
goto fim
:incompleto
echo Extraia o pacote completo antes de abrir este arquivo.
set "MCP_RESULTADO=2"
:fim
echo.
echo Depois, abra INSTALAR_E_INICIAR.bat para iniciar com as opcoes restauradas.
pause
exit /b %MCP_RESULTADO%
