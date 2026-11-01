@echo off
chcp 65001 > nul
title BoutiqueGest
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo [ERREUR] Dossier BoutiqueGest introuvable : "%PROJECT_ROOT%"
    pause
    exit /b 1
)
if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    echo [ERREUR] Environnement virtuel manquant.
    echo Lancez 00_INSTALLER_BOUTIQUEGEST.bat depuis INSTALL_BOUTIQUEGEST
    pause
    exit /b 1
)
"%PROJECT_ROOT%\.venv\Scripts\python.exe" "%PROJECT_ROOT%\run_waitress.py"
set "APP_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %APP_EXIT_CODE%
