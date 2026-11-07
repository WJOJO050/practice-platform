@echo off
setlocal
cd /d "%~dp0"

echo.
echo   ==========================================
echo     Install autostart (login, silent)
echo   ==========================================
echo.

set "PY="
set "PYW="
set "DSHPY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if exist "%DSHPY%" set "PY=%DSHPY%"
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo   [X] Python not found.
  pause
  exit /b 1
)

rem locate pythonw.exe (no console window)
for /f "delims=" %%i in ('where pythonw 2^>nul') do (
  if not defined PYW set "PYW=%%i"
)
if not defined PYW (
  if exist "%DSHPY%" (
    set "PYW=%DSHPY:python.exe=pythonw.exe%"
  )
)
if not defined PYW (
  echo   [X] pythonw.exe not found; will use python.exe instead.
  set "PYW=%PY%"
)

echo   pythonw: %PYW%
echo   folder : %CD%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$startup = [Environment]::GetFolderPath('Startup');" ^
  "$lnk = Join-Path $startup 'practice-platform.lnk';" ^
  "$s = $ws.CreateShortcut($lnk);" ^
  "$s.TargetPath = '%PYW%';" ^
  "$s.Arguments = '\"%CD%\server.py\" --silent';" ^
  "$s.WorkingDirectory = '%CD%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Practice Platform';" ^
  "$s.Save();" ^
  "Write-Host ('  [OK] shortcut created: ' + $lnk)"

if errorlevel 1 (
  echo   [X] Failed to create shortcut.
  pause
  exit /b 1
)

echo.
echo   Autostart installed. Next login it will run silently.
echo   Open now: http://127.0.0.1:7788/
echo.
echo   To remove autostart later, delete:
echo     %%APPDATA%%\Microsoft\Windows\Start Menu\Programs\Startup\practice-platform.lnk
echo.
pause
