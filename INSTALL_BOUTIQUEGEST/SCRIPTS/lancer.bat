@echo off
chcp 65001 > nul
title BoutiqueGest
cd /d C:\BoutiqueGest
if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement virtuel manquant.
    echo Lancez 00_INSTALLER_BOUTIQUEGEST.bat depuis INSTALL_BOUTIQUEGEST
    pause
    exit /b 1
)
start "" http://127.0.0.1:5000
".venv\Scripts\python.exe" run_waitress.py
pause
