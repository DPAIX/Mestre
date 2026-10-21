@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem Nao usar o cache global: evita Errno 13 Permission denied em pip\cache\wheels.
rem As variaveis valem apenas para este processo; nada e apagado do sistema.
set "PIP_NO_CACHE_DIR=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"

echo.
echo [MeuControlePC v2] Instalacao ou reparo de dependencias

echo Pasta: %CD%
echo Nenhum arquivo em dados\ ou .env sera sobrescrito.
echo.

if exist ".venv\Scripts\python.exe" goto instalar

echo Ambiente Python nao encontrado; criando .venv ...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv ".venv"
    if errorlevel 1 goto falha_venv
    goto instalar
)
where python >nul 2>nul
if errorlevel 1 goto sem_python
python -m venv ".venv"
if errorlevel 1 goto falha_venv

:instalar
if not exist ".venv\Scripts\python.exe" goto falha_venv
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if not errorlevel 1 goto instalar_pacotes
echo Reparando pip do ambiente virtual ...
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto falha

:instalar_pacotes
echo Instalando bibliotecas sem utilizar o cache global do pip ...
".venv\Scripts\python.exe" -m pip install --no-cache-dir --disable-pip-version-check --prefer-binary -r "requirements.txt"
if errorlevel 1 goto falha

if not exist ".env" (
    copy /y ".env.exemplo" ".env" >nul
    if errorlevel 1 goto falha
    echo Arquivo .env criado; configure credenciais NOVAS.
)
if not exist "dados" mkdir "dados"
if errorlevel 1 goto falha

echo.
echo Executando testes locais ...
".venv\Scripts\python.exe" -m unittest discover -s testes -q
if errorlevel 1 goto falha_teste

echo.
echo [OK] Dependencias instaladas e testes locais aprovados.
echo Revise o .env e depois execute iniciar_windows.bat.
echo.
pause
exit /b 0

:sem_python
echo [ERRO] Python nao encontrado. Instale Python 3.11+ e tente novamente.
goto falha

:falha_venv
echo [ERRO] Nao foi possivel criar ou localizar .venv.
goto falha

:falha_teste
echo [ERRO] Dependencias instaladas, mas algum teste local falhou.
echo Confira a mensagem acima antes de iniciar o bot.
goto falha

:falha
echo.
echo [ERRO] Instalacao nao concluida. Copie a mensagem de erro exibida acima.
echo Se persistir o problema de permissao, feche outros processos Python,
echo verifique a seguranca do Windows e tente novamente.
echo Seus arquivos em dados\ e .env foram preservados.
echo.
pause
exit /b 1
