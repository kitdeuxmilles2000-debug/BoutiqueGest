@echo off
setlocal EnableExtensions
title BoutiqueGest - mise a jour client

set "PROJECT_ROOT=%~dp0"
set "VENV_PATH=%PROJECT_ROOT%.venv"
set "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"

cd /d "%PROJECT_ROOT%"
if errorlevel 1 goto project_error

if not exist "%PROJECT_ROOT%run.py" goto project_error
if not exist "%PROJECT_ROOT%requirements.txt" goto project_error
if not exist "%PROJECT_ROOT%migrations\env.py" goto project_error

echo ============================================================
echo          BOUTIQUEGEST - MISE A JOUR CLIENT
echo ============================================================
echo.
echo Fermez BoutiqueGest sur cet ordinateur avant de continuer.
echo Ce script met a jour l'environnement Python, migre la base
echo et ajoute les donnees de reference manquantes.
echo Il ne telecharge pas le code de l'application.
echo.
choice /C ON /N /M "BoutiqueGest est ferme ? [O/N] "
if errorlevel 2 goto cancelled

if not exist "%PYTHON_EXE%" goto create_venv
goto check_venv

:create_venv
echo.
echo [INFO] Creation de l'environnement virtuel...
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 --version >nul 2>&1
    if not errorlevel 1 goto create_venv_with_launcher
)
where python >nul 2>&1
if errorlevel 1 goto python_not_found
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto python_version_error
python -m venv "%VENV_PATH%"
if errorlevel 1 goto venv_create_error
goto check_venv

:create_venv_with_launcher
py -3.12 -m venv "%VENV_PATH%"
if errorlevel 1 goto venv_create_error
goto check_venv

:check_venv
if not exist "%PYTHON_EXE%" goto venv_create_error
"%PYTHON_EXE%" -c "import sys; print('Python %d.%d.%d' % sys.version_info[:3]); raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
if errorlevel 1 goto python_version_error

echo.
echo [INFO] Actualisation de pip...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto pip_error

echo.
echo [INFO] Installation des dependances du projet...
"%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%requirements.txt"
if errorlevel 1 goto dependencies_error

set "FLASK_CONFIG=production"

echo.
echo [INFO] Sauvegarde et verification de la base de donnees...
"%PYTHON_EXE%" -c "from run import app; from app.services.backup import create_backup; ctx=app.app_context(); ctx.push(); backup=create_backup('avant-migration'); print('Sauvegarde verifiee : %s' % backup['path']); raise SystemExit(0 if backup['valid'] else 1)"
if errorlevel 1 goto backup_error

echo.
echo [INFO] Application des migrations Alembic...
"%PYTHON_EXE%" -m flask --app run db upgrade
if errorlevel 1 goto migration_error

echo.
echo [INFO] Mise a jour des donnees de reference...
"%PYTHON_EXE%" -m flask --app run seed
if errorlevel 1 goto seed_error

echo.
echo [INFO] Revision de base appliquee :
"%PYTHON_EXE%" -m flask --app run db current
if errorlevel 1 goto verification_error

echo.
echo ============================================================
echo [OK] MISE A JOUR TERMINEE
echo ============================================================
echo Vos donnees et fichiers uploads ont ete conserves.
echo Vous pouvez relancer BoutiqueGest avec votre raccourci habituel.
echo.
pause
exit /b 0

:project_error
echo [ERREUR] Fichiers du projet introuvables. Placez ce fichier dans
echo le dossier principal BoutiqueGest et relancez-le.
goto failed

:python_not_found
echo [ERREUR] Python 3.12 ou plus recent est requis.
echo Installez Python, puis relancez ce fichier.
goto failed

:python_version_error
echo [ERREUR] Python 3.12 ou plus recent est requis pour cet environnement.
echo Verifiez l'installation de Python et relancez ce fichier.
goto failed

:venv_create_error
echo [ERREUR] Impossible de creer ou d'utiliser .venv.
echo Verifiez Python 3.12+ et les droits d'ecriture dans le dossier du projet.
goto failed

:pip_error
echo [ERREUR] La mise a jour de pip a echoue. Verifiez la connexion internet.
goto failed

:dependencies_error
echo [ERREUR] Installation des dependances echouee. La base n'a pas ete migree.
goto failed

:backup_error
echo [ERREUR] Sauvegarde impossible ou invalide. La migration a ete arretee.
echo Verifiez le message ci-dessus et l'acces a la base SQLite locale.
goto failed

:migration_error
echo [ERREUR] Migration echouee. La sauvegarde prealable est conservee.
echo Contactez le support avec le message d'erreur affiche ci-dessus.
goto failed

:seed_error
echo [ERREUR] Mise a jour des donnees de reference echouee.
echo La sauvegarde prealable est conservee.
goto failed

:verification_error
echo [ERREUR] Impossible de verifier la revision de la base.
goto failed

:cancelled
echo Mise a jour annulee. Fermez BoutiqueGest puis relancez le fichier.
pause
exit /b 1

:failed
echo.
pause
exit /b 1
