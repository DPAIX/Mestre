@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
echo Este instalador usa Ollama local. O modelo qwen2.5:3b baixa alguns GB.
echo O processamento usa a memoria e o processador do seu PC, sem credito de API.
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
where ollama >nul 2>nul
if not errorlevel 1 goto iniciar_servico
where winget >nul 2>nul
if errorlevel 1 goto instalacao_manual
echo Instalando Ollama pelo catalogo do Windows ...
winget install --id Ollama.Ollama --exact
if errorlevel 1 goto falha
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
where ollama >nul 2>nul
if errorlevel 1 goto instalacao_manual
:iniciar_servico
start "" /b ollama serve >nul 2>nul
timeout /t 3 /nobreak >nul
call configurar_ia_local.bat --baixar-modelo qwen2.5:3b
if errorlevel 1 goto falha
echo Reinicie somente o assistente para carregar a configuracao da IA local.
exit /b 0
:instalacao_manual
echo Instale Ollama em https://ollama.com/download e execute novamente este arquivo.
pause
exit /b 2
:falha
echo A instalacao nao terminou. Seus dados e as chaves de APIs foram preservados.
echo Confira o erro e tente configurar_ia_local.bat --verificar.
pause
exit /b 1
