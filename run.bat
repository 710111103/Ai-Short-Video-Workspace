@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "PYTHON="
set "PYTHONW="
set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "CODEX_PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
set "LEGACY_PYTHON=%ROOT%..\.venv\Scripts\python.exe"
set "LEGACY_PYTHONW=%ROOT%..\.venv\Scripts\pythonw.exe"
set "HEALTH_URL=http://127.0.0.1:8765/"
set "APP_URL=http://127.0.0.1:8765/studio/"
set "OUT_LOG=%ROOT%logs\server.out.log"
set "ERR_LOG=%ROOT%logs\server.err.log"
set "PID_FILE=%ROOT%logs\server.pid"

if exist "%CODEX_PYTHON%" (
  set "PYTHON=%CODEX_PYTHON%"
  if exist "%CODEX_PYTHONW%" set "PYTHONW=%CODEX_PYTHONW%"
)
if not defined PYTHON if exist "%LEGACY_PYTHON%" (
  "%LEGACY_PYTHON%" -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON=%LEGACY_PYTHON%"
    if exist "%LEGACY_PYTHONW%" set "PYTHONW=%LEGACY_PYTHONW%"
  )
)

if not defined PYTHONW set "PYTHONW=%PYTHON%"

if not defined PYTHON (
  echo [ERROR] No working Python runtime was found.
  echo Checked:
  echo %CODEX_PYTHON%
  echo %LEGACY_PYTHON%
  echo.
  echo Please create .venv first.
  exit /b 1
)

curl.exe --silent --show-error --fail --max-time 2 "%HEALTH_URL%" >nul 2>nul
if %errorlevel%==0 (
  echo Backend is already running. Opening the app...
  explorer "%APP_URL%" >nul 2>nul
  exit /b 0
)

echo Starting Short Video Studio backend...
"%PYTHON%" "launch_server_runtime.py" "%PYTHONW%" "%OUT_LOG%" "%ERR_LOG%" "%PID_FILE%"
if errorlevel 1 (
  echo [ERROR] Failed to launch the detached backend process.
  exit /b 1
)
echo Waiting for backend to become ready...

for /l %%i in (1,1,20) do (
  curl.exe --silent --show-error --fail --max-time 2 "%HEALTH_URL%" >nul 2>nul
  if not errorlevel 1 goto open_app
  ping 127.0.0.1 -n 2 >nul
)

echo [ERROR] Backend did not become ready.
if exist "%ERR_LOG%" (
  echo.
  echo ---- server.err.log ----
  type "%ERR_LOG%"
)
if exist "%OUT_LOG%" (
  echo.
  echo ---- server.out.log ----
  type "%OUT_LOG%"
)
exit /b 1

:open_app
echo Backend is ready. Opening the app...
explorer "%APP_URL%" >nul 2>nul
exit /b 0
