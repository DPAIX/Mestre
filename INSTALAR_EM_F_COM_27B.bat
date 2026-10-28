@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "MEUCONTROLEPC_PREPARAR_27B=1"
call "%~dp0INSTALAR_E_INICIAR.bat"
exit /b %ERRORLEVEL%
