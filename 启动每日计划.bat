@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo 没有找到 Python。请先安装 Python 3.10 或更高版本。
  pause
  exit /b 1
)

where npm >nul 2>nul
if not errorlevel 1 (
  echo 正在构建前端...
  call npm --prefix frontend run build
  if errorlevel 1 (
    echo.
    echo 前端构建失败，仍尝试用已有的 web\ 构建产物启动。
  )
) else (
  echo 未找到 Node.js，跳过前端构建，使用已有的 web\ 构建产物。
)

echo.
echo 启动每日计划，浏览器将自动打开 http://127.0.0.1:8765
echo 关闭本窗口即停止服务。
echo.
py -3 -m app.main
if errorlevel 1 (
  echo.
  echo 每日计划未能启动，请查看 data\daily_plan.log。
  pause
)
