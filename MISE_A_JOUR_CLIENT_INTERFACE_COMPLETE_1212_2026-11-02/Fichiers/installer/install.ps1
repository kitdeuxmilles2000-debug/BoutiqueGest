# -*- coding: utf-8 -*-
# Script d'installation automatisé pour BoutiqueGest
# Auteur: Devin AI
# Version: 1.0

param(
    [switch]$Force = $false,
    [switch]$Silent = $false
)

# Configuration globale
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Variables
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
$PythonVersion = "3.12.3"
$PythonInstaller = "$ScriptPath\python-$PythonVersion-amd64.exe"
$VenvPath = "$ProjectRoot\.venv"
$PythonExe = "$VenvPath\Scripts\python.exe"
$PipExe = "$VenvPath\Scripts\pip.exe"
$script:SystemPython = $null
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutName = "BoutiqueGest"
$ShortcutPath = "$DesktopPath\$ShortcutName.lnk"
$IconPath = "$ScriptPath\icon.ico"

# Fonction d'affichage
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Success {
    param([string]$Message)
    Write-ColorOutput "[OK] $Message" "Green"
}

function Write-Error {
    param([string]$Message)
    Write-ColorOutput "[ERROR] $Message" "Red"
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "[WARN] $Message" "Yellow"
}

function Write-Info {
    param([string]$Message)
    Write-ColorOutput "[INFO] $Message" "Cyan"
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-ColorOutput "=== $Message ===" "Magenta"
}

# Vérifier les droits administrateur
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-SystemPython {
    $pythonCommand = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pythonCommand) {
        $version = & $pythonCommand.Source --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return @{ Path = $pythonCommand.Source; Prefix = @(); Version = $version }
        }
    }

    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        $version = & $launcher.Source -3 --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return @{ Path = $launcher.Source; Prefix = @("-3"); Version = $version }
        }
    }
    return $null
}

# Vérifier si Python est installé
function Test-PythonInstalled {
    $script:SystemPython = Find-SystemPython
    if ($script:SystemPython) {
        Write-Info "Python détecté: $($script:SystemPython.Version)"
        return $true
    }
    return $false
}

# Installer Python
function Install-Python {
    Write-Step "Installation de Python $PythonVersion"

    if (Test-PythonInstalled) {
        Write-Success "Python est deja installe"
        return
    }

    if (-not (Test-Path $PythonInstaller)) {
        Write-Error "Fichier d'installation Python non trouve: $PythonInstaller"
        Write-Info "Veuillez placer python-$PythonVersion-amd64.exe dans le dossier installer/"
        exit 1
    }

    Write-Info "Installation de Python en cours..."
    $args = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_test=0"
    )

    $process = Start-Process -FilePath $PythonInstaller -ArgumentList $args -Wait -PassThru

    if ($process.ExitCode -eq 0) {
        Write-Success "Python installe avec succes"
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $script:SystemPython = Find-SystemPython
        if (-not $script:SystemPython) {
            throw "Python a ete installe mais reste introuvable. Fermez puis relancez l'installation."
        }
    } else {
        Write-Error "Echec de l'installation de Python (code: $($process.ExitCode))"
        exit 1
    }
}

# Créer l'environnement virtuel
function New-VirtualEnvironment {
    Write-Step "Creation de l'environnement virtuel"

    if (Test-Path $VenvPath) {
        if ($Force) {
            Write-Warning "Suppression de l'environnement virtuel existant..."
            Remove-Item -Path $VenvPath -Recurse -Force
        } else {
            Write-Success "Environnement virtuel deja existant"
            return
        }
    }

    Write-Info "Creation de l'environnement virtuel..."
    if (-not $script:SystemPython) {
        $script:SystemPython = Find-SystemPython
    }
    if (-not $script:SystemPython) {
        throw "Python est introuvable. Verifiez la commande python ou le lanceur py -3."
    }
    $pythonArgs = @($script:SystemPython.Prefix) + @("-m", "venv", $VenvPath)
    & $script:SystemPython.Path @pythonArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Environnement virtuel cree avec succes"
    } else {
        Write-Error "Echec de la creation de l'environnement virtuel"
        exit 1
    }
}

# Installer les dépendances
function Install-Dependencies {
    Write-Step "Installation des dependances"

    Write-Info "Mise a jour de pip..."
    & $PipExe install --upgrade pip --quiet

    Write-Info "Installation des packages depuis requirements.txt..."
    & $PipExe install -r "$ProjectRoot\requirements.txt" --quiet

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Dependances installees avec succes"
    } else {
        Write-Error "Echec de l'installation des dependances"
        exit 1
    }
}

# Initialiser la base de données
function Initialize-Database {
    Write-Step "Initialisation de la base de donnees"

    Write-Info "Migration de la base de donnees..."
    Push-Location $ProjectRoot
    & $PythonExe -m flask --app run.py db upgrade
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Base de donnees migree avec succes"
    } else {
        Write-Warning "Erreur lors de la migration (peut etre normal si deja migre)"
    }

    Write-Info "Peuplement des donnees de reference..."
    Push-Location $ProjectRoot
    & $PythonExe -m flask --app run.py seed
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Donnees de reference creees avec succes"
    } else {
        Write-Warning "Erreur lors du peuplement (peut etre normal si deja fait)"
    }
}

# Créer le raccourci bureau
function New-DesktopShortcut {
    Write-Step "Creation du raccourci bureau"

    if (-not (Test-Path $IconPath)) {
        Write-Warning "Icône non trouvee: $IconPath"
        Write-Info "Le raccourci sera cree sans icône personnalisee"
        $IconPath = ""
    }

    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "$ScriptPath\start_app.bat"
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "BoutiqueGest - Systeme de gestion commerciale"
    if ($IconPath) {
        $Shortcut.IconLocation = $IconPath
    }
    $Shortcut.Save()

    Write-Success "Raccourci cree: $ShortcutPath"
}

# Créer le script de démarrage
function New-StartupScript {
    Write-Step "Creation du script de demarrage"

    $startScript = @'
@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo [ERREUR] Dossier BoutiqueGest introuvable.
    pause
    exit /b 1
)
if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    echo [ERREUR] Environnement Python manquant.
    pause
    exit /b 1
)
"%PROJECT_ROOT%\.venv\Scripts\python.exe" "%PROJECT_ROOT%\run_waitress.py"
set "APP_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %APP_EXIT_CODE%
'@

    $startScript | Out-File -FilePath "$ScriptPath\start_app.bat" -Encoding ASCII -Force
    Write-Success "Script de demarrage cree"
}

# Vérifier la configuration
function Test-Configuration {
    Write-Step "Verification de la configuration"

    $checks = @(
        @{ Name = "Python"; Test = { Test-Path $PythonExe } },
        @{ Name = "Pip"; Test = { Test-Path $PipExe } },
        @{ Name = "Environnement virtuel"; Test = { Test-Path $VenvPath } },
        @{ Name = "Raccourci bureau"; Test = { Test-Path $ShortcutPath } },
        @{ Name = "Script de demarrage"; Test = { Test-Path "$ScriptPath\start_app.bat" } }
    )

    $allPassed = $true
    foreach ($check in $checks) {
        if (& $check.Test) {
            Write-Success "$($check.Name): OK"
        } else {
            Write-Error "$($check.Name): ECHEC"
            $allPassed = $false
        }
    }

    return $allPassed
}

# Point d'entrée principal
function Main {
    Write-ColorOutput "
============================================================
           INSTALLATEUR BOUTIQUEGEST
           Systeme de gestion commerciale
============================================================
" "Cyan"

    if (-not (Test-Administrator) -and -not $Silent) {
        Write-Warning "Ce script necessite des droits administrateur pour installer Python"
        Write-Info "Execution en mode utilisateur (Python doit deja etre installe)"
    }

    try {
        # Etape 1: Installer Python
        Install-Python

        # Etape 2: Creer l'environnement virtuel
        New-VirtualEnvironment

        # Etape 3: Installer les dependances
        Install-Dependencies

        # Etape 4: Initialiser la base de donnees
        Initialize-Database

        # Etape 5: Creer le script de demarrage
        New-StartupScript

        # Etape 6: Creer le raccourci bureau
        New-DesktopShortcut

        # Etape 7: Programmer la sauvegarde quotidienne
        Write-Step "Programmation des sauvegardes quotidiennes"
        $backupTaskScript = Join-Path $ScriptPath "Register-BackupTask.ps1"
        if (Test-Path $backupTaskScript) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $backupTaskScript -ProjectRoot $ProjectRoot
            if ($LASTEXITCODE -ne 0) {
                throw "La programmation de la sauvegarde quotidienne a echoue."
            }
        } else {
            throw "Script de programmation des sauvegardes introuvable : $backupTaskScript"
        }

        # Etape 8: Verification
        Write-Step "Verification finale"
        if (Test-Configuration) {
            Write-ColorOutput "
============================================================
           INSTALLATION TERMINEE AVEC SUCCES
============================================================
" "Green"
            Write-Info "L'application peut etre lancee via le raccourci sur le bureau"
            Write-Info "Ou manuellement: installer\start_app.bat"
            Write-Info "URL: http://127.0.0.1:5000"
            Write-Info "Compte par defaut: admin / admin123 (a changer apres premiere connexion)"
        } else {
            Write-Error "La verification a echoue"
            exit 1
        }

    } catch {
        Write-Error "Erreur lors de l'installation: $_"
        exit 1
    }
}

# Exécution
Main
