@echo off
REM Lista grupos da SUA conta e gera watched_groups.json
cd /d "%~dp0"
python bot.py --list-groups
pause
