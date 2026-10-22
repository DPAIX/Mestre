@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto falta_python
".venv\Scripts\python.exe" -c "import google_auth_oauthlib.flow, googleapiclient.discovery" >nul 2>nul
if not errorlevel 1 goto autorizar
".venv\Scripts\python.exe" -m pip install --no-cache-dir --disable-pip-version-check -r requirements-google.txt
if errorlevel 1 goto falha_pacotes
:autorizar
".venv\Scripts\python.exe" autorizar_google.py %*
set "RESULTADO_GOOGLE=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %RESULTADO_GOOGLE%
:falta_python
echo Execute instalar_windows.bat antes de autorizar Google Calendar.
pause
exit /b 2
:falha_pacotes
echo As dependencias Google nao foram instaladas. A autorizacao nao foi iniciada.
pause
exit /b 1
