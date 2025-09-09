@echo on
setlocal ENABLEDELAYEDEXPANSION

REM === Resolve repo dir from this .bat ===
set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"

REM === Scripts & configs ===
set "FETCH_SCRIPT=working_fetcher.py"
set "DEPLOY_SCRIPT=deploy-wallpaper.py"
set "COMP_SCRIPT=companion_selector.py"
set "VIEWS_CFG=views_config.json"
set "PROJ_CFG=projects.json"

REM === Use project venv explicitly ===
set "VENV_DIR=%REPO_DIR%\satellite-wallpaper-env"
set "PYEXE=%VENV_DIR%\Scripts\python.exe"
set "ACTIVATE=%VENV_DIR%\Scripts\activate.bat"

if not exist "%PYEXE%" (
  echo [FATAL] Expected venv python at: %PYEXE%
  echo Create it:  py -3 -m venv "%VENV_DIR%"
  pause & exit /b 1
)

REM === Logging ===
if not exist "%REPO_DIR%\logs" mkdir "%REPO_DIR%\logs"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"`) do set RUNTS=%%i
set "LOG=%REPO_DIR%\logs\run-%RUNTS%.log"
echo REPO_DIR=%REPO_DIR% > "%LOG%"
echo PYEXE=%PYEXE% >> "%LOG%"

cd /d "%REPO_DIR%"
call "%ACTIVATE%" >> "%LOG%" 2>&1
"%PYEXE%" -V >> "%LOG%" 2>&1

REM === Sanity: required files present ===
for %%F in ("%FETCH_SCRIPT%" "%DEPLOY_SCRIPT%" "%COMP_SCRIPT%" "%VIEWS_CFG%" "%PROJ_CFG%") do (
  if not exist "%REPO_DIR%\%%~F" (
    echo [FATAL] Missing %%~F >> "%LOG%"
    type "%LOG%" | more & pause & exit /b 1
  )
)

REM === Step 1: Fetch ===
echo [1/3] Fetching... >> "%LOG%"
"%PYEXE%" "%FETCH_SCRIPT%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Fetch failed. See "%LOG%".
  type "%LOG%" | more & pause & exit /b 1
)

REM === Step 2: Deploy ===
echo [2/3] Deploying... >> "%LOG%"
"%PYEXE%" "%DEPLOY_SCRIPT%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Deploy failed. See "%LOG%".
  type "%LOG%" | more & pause & exit /b 1
)

REM === Step 3: Companions ===
echo [3/3] Companions... >> "%LOG%"
"%PYEXE%" "%COMP_SCRIPT%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Companions failed. See "%LOG%".
  type "%LOG%" | more & pause & exit /b 1
)

echo [OK] All steps finished. Log: "%LOG%"
type "%LOG%" | more
pause
exit /b 0
