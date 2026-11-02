@echo off
REM Bot ComprasTG - Headless (sem TUI, so bot.py)
cd /d "%~dp0"
python bot.py --watch
pause
