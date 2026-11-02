@echo off
REM Solicita parada cooperativa somente deste monitor.
cd /d "%~dp0"
python bot.py --stop
