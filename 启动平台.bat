@echo off
setlocal
cd /d "%~dp0"

echo.
echo   ==========================================
echo     AI College - Practice Platform
echo   ==========================================
echo.

set "PY="
set "PYW="
set "DSHPY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if exist "%DSHPY%" (
  set "PY=%DSHPY%"
  set "PYW=%DSHPY:python.exe=pythonw.exe%"
)
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY=py -3"
    for /f "delims=" %%i in ('where pythonw 2^>nul') do set "PYW=%%i"
  )
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "PY=python"
    for /f "delims=" %%i in ('where pythonw 2^>nul') do set "PYW=%%i"
  )
)
if not defined PY (
  echo   [X] Python not found. Install Python 3 first.
  pause
  exit /b 1
)

echo   Python: %PY%
echo   Starting... browser opens automatically.
echo.

%PY% server.py
set "CODE=%errorlevel%"

echo.
if not "%CODE%"=="0" (
  echo   [X] Server exited with code %CODE%
) else (
  echo   Server stopped.
)
echo.
pause
