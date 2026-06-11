@echo off
cd /d %~dp0
echo Iniciando Proyecto Compras...
.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8082 --reload
