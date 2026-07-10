@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" tools\startup_guard.py
if errorlevel 1 (
  echo.
  echo Startup guard failed. Fix the error above before exposing the site through Cloudflare Tunnel.
  pause
  exit /b 1
)

set "HOST="
if not defined PORT set "PORT=5000"
if not defined TUNNEL_HOST set "TUNNEL_HOST=127.0.0.1"
if not defined WAITRESS_THREADS set "WAITRESS_THREADS=12"
if not defined WAITRESS_CONNECTION_LIMIT set "WAITRESS_CONNECTION_LIMIT=200"
if not defined WAITRESS_CHANNEL_TIMEOUT set "WAITRESS_CHANNEL_TIMEOUT=120"

echo.
echo Tunnel origin:
echo   http://%TUNNEL_HOST%:%PORT%
echo.
echo Cloudflare Tunnel should point to:
echo   http://127.0.0.1:%PORT%
echo.

".venv\Scripts\python.exe" serve_tunnel.py
