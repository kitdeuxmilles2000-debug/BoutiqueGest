@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"

cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo [ERREUR] Impossible d'acceder au dossier du projet : "%PROJECT_ROOT%"
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    echo [ERREUR] Environnement Python manquant dans "%PROJECT_ROOT%\.venv"
    pause
    exit /b 1
)

echo [INFO] Demarrage de BoutiqueGest avec Waitress...
"%PROJECT_ROOT%\.venv\Scripts\python.exe" "%PROJECT_ROOT%\run_waitress.py"
set "APP_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %APP_EXIT_CODE%
