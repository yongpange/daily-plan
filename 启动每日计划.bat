@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo 没有找到 Python。请先安装 Python 3.10 或更高版本。
  pause
  exit /b 1
)

py -3 server.py
if errorlevel 1 (
  echo.
  echo 每日计划未能启动，请查看 data\daily_plan.log。
  pause
)
