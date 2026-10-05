@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist .env (
  copy .env.example .env >nul
  echo 請在記事本中填入 BOT_TOKEN，儲存後再執行一次。
  notepad .env
  pause
  exit /b
)
.venv\Scripts\python.exe bot.py
:failed
pause
