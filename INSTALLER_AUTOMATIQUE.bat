@echo off
REM ============================================================================
REM INSTALLATEUR AUTOMATIQUE BOUTIQUEGEST - UN SEUL CLIC
REM ============================================================================
REM Ce script fait TOUT automatiquement:
REM - Télécharge et installe Python si nécessaire
REM - Crée l'environnement virtuel
REM - Installe les dépendances
REM - Initialise la base de données
REM - Crée le raccourci bureau
REM - Lance l'application
REM ============================================================================

setlocal enabledelayedexpansion

echo ====================================================================
echo           INSTALLATEUR AUTOMATIQUE BOUTIQUEGEST
echo           Installation en un seul clic
echo ====================================================================
echo.

REM Configuration
set PYTHON_VERSION=3.12.3
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set PYTHON_INSTALLER=%TEMP%\python-%PYTHON_VERSION%-amd64.exe
set PROJECT_ROOT=%~dp0
set VENV_PATH=%PROJECT_ROOT%.venv
set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT=%DESKTOP%\BoutiqueGest.lnk
set PYTHON_CMD=python

REM Vérifier les droits administrateur
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Demande des droits administrateur...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo [INFO] Verification de Python...
%PYTHON_CMD% --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Python est deja installe
    for /f "tokens=2" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set PYTHON_INSTALLED=%%i
    echo [INFO] Version: !PYTHON_INSTALLED!
) else (
    echo [INFO] Python non trouve, telechargement en cours...
    echo [INFO] Cela peut prendre quelques minutes...
    echo.

    REM Télécharger Python
    powershell -Command "& {Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'}"

    if not exist "%PYTHON_INSTALLER%" (
        echo [ERREUR] Echec du telechargement de Python
        echo [INFO] Veuillez verifier votre connexion internet
        pause
        exit /b 1
    )

    echo [OK] Python telecharge avec succes
    echo [INFO] Installation de Python en cours...

    REM Installer Python silencieusement
    "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0

    if %ERRORLEVEL% NEQ 0 (
        echo [ERREUR] Echec de l'installation de Python
        pause
        exit /b 1
    )

    echo [OK] Python installe avec succes

    REM Trouver le chemin de Python après installation
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_VERSION:~0,1%%PYTHON_VERSION:~2,1%\python.exe"
    if not exist "%PYTHON_CMD%" (
        set "PYTHON_CMD=C:\Python%PYTHON_VERSION:~0,1%%PYTHON_VERSION:~2,1%\python.exe"
    )

    REM Supprimer l'installateur
    del "%PYTHON_INSTALLER%" >nul 2>&1
)

echo.
echo [INFO] Creation de l'environnement virtuel...
if exist "%VENV_PATH%" (
    echo [OK] Environnement virtuel deja existent
) else (
    "%PYTHON_CMD%" -m venv "%VENV_PATH%"
    if %ERRORLEVEL% NEQ 0 (
        echo [ERREUR] Echec de la creation de l'environnement virtuel
        pause
        exit /b 1
    )
    echo [OK] Environnement virtuel cree
)

echo.
echo [INFO] Activation de l'environnement virtuel...
call "%VENV_PATH%\Scripts\activate.bat"

echo.
echo [INFO] Installation des dependances...
echo [INFO] Cela peut prendre quelques minutes...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%PROJECT_ROOT%requirements.txt" --quiet

if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Echec de l'installation des dependances
    pause
    exit /b 1
)
echo [OK] Dependances installees

echo.
echo [INFO] Installation de Waitress...
python -m pip install waitress --quiet
echo [OK] Waitress installe

echo.
echo [INFO] Initialisation de la base de donnees...
cd /d "%PROJECT_ROOT%"
python -m flask --app run db upgrade
if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Echec de la mise a jour de la base de donnees
    pause
    exit /b 1
)
python -m flask --app run seed
if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Echec de l'initialisation des donnees de reference
    pause
    exit /b 1
)
echo [OK] Base de donnees initialisee

echo.
echo [INFO] Creation du raccourci bureau...
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%PROJECT_ROOT%installer\start_app.bat'; $Shortcut.WorkingDirectory = '%PROJECT_ROOT%'; $Shortcut.Description = 'BoutiqueGest - Systeme de gestion commerciale'; if (Test-Path '%PROJECT_ROOT%installer\icon.ico') { $Shortcut.IconLocation = '%PROJECT_ROOT%installer\icon.ico' }; $Shortcut.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [OK] Raccourci cree sur le bureau
) else (
    echo [WARN] Echec de la creation du raccourci (non critique)
)

echo.
echo ====================================================================
echo           INSTALLATION TERMINEE AVEC SUCCES
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
echo L'application va demarrer automatiquement...
echo.

REM Attendre 2 secondes
timeout /t 2 /nobreak >nul

REM Lancer l'application
cd /d "%PROJECT_ROOT%"
call "%VENV_PATH%\Scripts\activate.bat"
python run_waitress.py

pause
