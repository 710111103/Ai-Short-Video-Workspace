@echo off
setlocal
cd /d "%~dp0"

call "%~dp0stop.bat"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2"
call "%~dp0run.bat"

endlocal
