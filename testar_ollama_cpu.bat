@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
echo Teste solicitado: uma geracao curta do llama3.2:latest em CPU.
echo Pare novas mensagens para a equipe antes de executar este teste.
echo O modelo precisa estar instalado como local; nenhum download sera feito.
call "%~dp0diagnosticar_ollama.bat" --testar-cpu
set "RESULTADO_TESTE_CPU_OLLAMA=%ERRORLEVEL%"
pause
exit /b %RESULTADO_TESTE_CPU_OLLAMA%
