@echo off
REM Inicia monitoramento headless - alerta A57/Galaxy em Mensagens Salvas (ate 60s)
cd /d "%~dp0"
python bot.py --watch
