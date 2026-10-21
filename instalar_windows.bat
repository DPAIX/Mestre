@echo off
setlocal
cd /d "%~dp0"
rem O instalador tambem funciona como reparo, sem reconfigurar os dados.
call "%~dp0corrigir_instalacao_windows.bat"
exit /b %errorlevel%
