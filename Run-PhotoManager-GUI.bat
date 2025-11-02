@echo off
REM === Run-PhotoManager-GUI.bat ===
REM Lance l'interface graphique PhotoManager (Tkinter) avec venv local
REM Supporte le "glisser-deposer" d'un dossier sur ce .bat (transmis en argument)

setlocal EnableDelayedExpansion
cd /d %~dp0

where py >nul 2>nul
if errorlevel 1 (
  echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
  echo Rendez-vous sur https://www.python.org/ pour l'installer, puis relancez.
  pause
  exit /b
)

if not exist .venv (
  echo [SETUP] Creation de l'environnement virtuel...
  py -m venv .venv
)

call .venv\Scripts\activate.bat

python -m pip install --upgrade pip >nul
python -m pip install pillow >nul

echo [RUN] Lancement de l'application PhotoManager GUI...
if "%~1"=="" (
  python photomanager_gui.py
) else (
  python photomanager_gui.py "%~1"
)

echo.
echo [OK] Application fermee.
pause
