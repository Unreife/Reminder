@echo off
setlocal
pushd "%~dp0"

REM Prefer venv Python if present
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

if "%PY%"=="" (
  where python >nul 2>nul && set "PY=python"
)
if "%PY%"=="" (
  where py >nul 2>nul && set "PY=py"
)

if "%PY%"=="" (
  echo Python not found. Install from https://www.python.org/downloads/ and re-run this file.
  pause
  exit /b 1
)

"%PY%" gui.py

popd
endlocal

