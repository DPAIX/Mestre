@echo off
rem Este arquivo e chamado dentro do setlocal dos iniciadores.
if /I not "%~d0"=="F:" (
  echo Salve e extraia este pacote no disco F: antes de iniciar.
  exit /b 2
)
if not exist "F:\" (
  echo O disco F: nao esta disponivel. Nenhuma instalacao sera feita em C:.
  exit /b 2
)
set "MEUCONTROLEPC_SOMENTE_F=1"
set "MEUCONTROLEPC_RAIZ_F=F:\MeuControlePC_v2"
set "MEUCONTROLEPC_ENV=F:\MeuControlePC_v2\.env"
set "MEUCONTROLEPC_DADOS=F:\MeuControlePC_v2\dados"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
set "TEMP=F:\MeuControlePC_v2\temporarios"
set "TMP=F:\MeuControlePC_v2\temporarios"
set "TMPDIR=F:\MeuControlePC_v2\temporarios"
set "PIP_CACHE_DIR=F:\MeuControlePC_v2\cache\pip"
set "HF_HOME=F:\MeuControlePC_v2\cache\huggingface"
set "HUGGINGFACE_HUB_CACHE=F:\MeuControlePC_v2\cache\huggingface\hub"
set "XDG_CACHE_HOME=F:\MeuControlePC_v2\cache"
set "NPM_CONFIG_CACHE=F:\MeuControlePC_v2\cache\npm"
set "CUDA_CACHE_PATH=F:\MeuControlePC_v2\cache\cuda"
set "PATH=F:\PROGRAMAS\nodejs;%PATH%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%TEMP%" exit /b 2
exit /b 0
