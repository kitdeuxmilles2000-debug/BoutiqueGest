@echo off
REM Script d'installation facile pour BoutiqueGest
REM Double-cliquez sur ce fichier pour démarrer l'installation

echo ====================================================================
echo           INSTALLATION BOUTIQUEGEST
echo           Systeme de gestion commerciale
echo ====================================================================
echo.

REM Vérifier si PowerShell est disponible
where powershell >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] PowerShell n'est pas disponible sur ce systeme
    echo Ce script necessite Windows PowerShell
    pause
    exit /b 1
)

echo [INFO] Lancement de l'installation...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "INSTALL_EXIT_CODE=%ERRORLEVEL%"

if "%INSTALL_EXIT_CODE%" EQU "0" (
    echo.
    echo ====================================================================
    echo           INSTALLATION TERMINEE
    echo ====================================================================
    echo.
    echo Un raccourci "BoutiqueGest" a ete cree sur votre bureau.
    echo Double-cliquez dessus pour lancer l'application.
    echo.
    echo URL: http://127.0.0.1:5000
    echo Utilisateur: admin
    echo Mot de passe: admin123
    echo.
    echo IMPORTANT: Changez le mot de passe apres la premiere connexion!
    echo.
) else (
    echo.
    echo [ERREUR] L'installation a echoue
    echo Consultez le fichier INSTALLATION.txt pour plus d'informations
    echo.
)

pause
