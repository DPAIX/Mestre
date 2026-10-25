@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
echo Este fluxo registra gemma4:31b-cloud pelo Ollama local.
echo E um modelo de NUVEM: precisa de Internet, conta Ollama e cota.
echo As consultas ao modelo enviam seu pedido ao provedor.
echo Nenhuma conversa do assistente sera enviada neste registro.
echo O modelo padrao, o perfil CPU, o .env e os dados nao serao alterados por este script.
choice /C SN /N /M "Deseja registrar o modelo? [S/N]: "
if errorlevel 2 goto fim
where ollama.exe >nul 2>nul
if errorlevel 1 goto ausente
set "OLLAMA_HOST=http://127.0.0.1:11434"
ollama.exe pull gemma4:31b-cloud
if errorlevel 1 goto falha
echo Registro solicitado com sucesso. Isso nao comprova geracao ou cota na conta.
echo No painel, atualize os modelos. Para a equipe CPU, revise e use Permitir nuvem no perfil CPU.
echo A equipe automatica inclui os modelos registrados na proxima pergunta que precisar de IA.
goto fim
:ausente
echo Ollama nao encontrado. Instale ou abra o Ollama e execute novamente este arquivo.
goto fim
:falha
echo O registro nao foi concluido. Confira o erro do Ollama e o login na sua conta.
echo Nenhuma nova tentativa foi enviada por este script.
:fim
pause
