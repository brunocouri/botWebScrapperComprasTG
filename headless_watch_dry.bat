@echo off
REM Teste sem enviar - so loga MATCH (para testar regex A57 vs A570)
cd /d "%~dp0"
python bot.py --watch --dry-run
pause
