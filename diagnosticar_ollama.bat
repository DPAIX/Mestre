@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto usar_venv
where py >nul 2>nul
if not errorlevel 1 goto usar_py
where python >nul 2>nul
if not errorlevel 1 goto usar_python
echo [ERRO] Python 3.11 ou superior nao encontrado. Use o Python do assistente.
set "RESULTADO_DIAGNOSTICO_OLLAMA=2"
goto finalizar

:usar_venv
".venv\Scripts\python.exe" -I -B "%~dp0diagnostico_ollama.py" %*
set "RESULTADO_DIAGNOSTICO_OLLAMA=%ERRORLEVEL%"
goto finalizar

:usar_py
py -3 -I -B "%~dp0diagnostico_ollama.py" %*
set "RESULTADO_DIAGNOSTICO_OLLAMA=%ERRORLEVEL%"
goto finalizar

:usar_python
python -I -B "%~dp0diagnostico_ollama.py" %*
set "RESULTADO_DIAGNOSTICO_OLLAMA=%ERRORLEVEL%"

:finalizar
if "%~1"=="" pause
exit /b %RESULTADO_DIAGNOSTICO_OLLAMA%
