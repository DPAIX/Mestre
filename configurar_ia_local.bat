@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto usar_venv
where py >nul 2>nul
if not errorlevel 1 goto usar_py
where python >nul 2>nul
if not errorlevel 1 goto usar_python
echo [ERRO] Python nao encontrado. Instale Python 3.11+ ou execute instalar_windows.bat.
set "RESULTADO_IA_LOCAL=2"
goto finalizar

:usar_venv
".venv\Scripts\python.exe" "configurar_ia_local.py" %*
set "RESULTADO_IA_LOCAL=%ERRORLEVEL%"
goto finalizar

:usar_py
py -3 "configurar_ia_local.py" %*
set "RESULTADO_IA_LOCAL=%ERRORLEVEL%"
goto finalizar

:usar_python
python "configurar_ia_local.py" %*
set "RESULTADO_IA_LOCAL=%ERRORLEVEL%"

:finalizar
if not "%RESULTADO_IA_LOCAL%"=="0" echo Consulte as instrucoes acima e tente novamente.
if "%~1"=="" pause
exit /b %RESULTADO_IA_LOCAL%
