@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r requirements-google.txt
".venv\Scripts\python.exe" autorizar_google.py
pause
