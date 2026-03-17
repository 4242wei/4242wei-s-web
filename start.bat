@echo off
setlocal
cd /d "%~dp0"

set "CODEX_CLI_PATH="
for /f "delims=" %%I in ('where.exe codex 2^>nul') do (
  if not defined CODEX_CLI_PATH set "CODEX_CLI_PATH=%%~fI"
)
if not defined CODEX_CLI_PATH (
  for /d %%D in ("%USERPROFILE%\.vscode\extensions\openai.chatgpt-*-win32-x64") do (
    if not defined CODEX_CLI_PATH if exist "%%~fD\bin\windows-x86_64\codex.exe" set "CODEX_CLI_PATH=%%~fD\bin\windows-x86_64\codex.exe"
  )
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" tools\startup_guard.py
if errorlevel 1 (
  echo.
  echo 启动前体检失败，网页没有启动。请先修复上面的报错。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
