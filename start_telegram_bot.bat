@echo off
REM Script para ejecutar el bot de Telegram como servicio en Windows
REM Ejecutar este archivo para iniciar el bot automáticamente

echo Iniciando Bot de Telegram...
cd /d "%~dp0"

REM Activar entorno virtual y ejecutar bot
call venv_new\Scripts\activate.bat
python telegram_bot.py

pause
