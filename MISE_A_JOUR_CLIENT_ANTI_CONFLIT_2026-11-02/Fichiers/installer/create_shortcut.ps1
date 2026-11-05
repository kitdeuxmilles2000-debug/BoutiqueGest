# -*- coding: utf-8 -*-
# Script de création du raccourci bureau pour BoutiqueGest

param(
    [string]$ShortcutName = "BoutiqueGest",
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\$ShortcutName.lnk"
$IconPath = "$ScriptPath\icon.ico"
$TargetPath = "$ScriptPath\start_app.bat"

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

Write-ColorOutput "
============================================================
           CREATION RACCOURCI BUREAU
============================================================
" "Cyan"

# Vérifier que le script de démarrage existe
if (-not (Test-Path $TargetPath)) {
    Write-Error "Script de démarrage non trouvé: $TargetPath"
    exit 1
}

# Supprimer le raccourci existant si demandé
if (Test-Path $ShortcutPath) {
    if ($Force) {
        Write-Warning "Suppression du raccourci existant..."
        Remove-Item -Path $ShortcutPath -Force
    } else {
        Write-Warning "Raccourci déjà existant: $ShortcutPath"
        Write-ColorOutput "Utilisez -Force pour le remplacer" "Cyan"
        exit 0
    }
}

# Créer le raccourci
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetPath
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "BoutiqueGest - Système de gestion commerciale"

    # Définir l'icône si disponible
    if (Test-Path $IconPath) {
        $Shortcut.IconLocation = $IconPath
        Write-Success "Icône personnalisée appliquée"
    } else {
        Write-Warning "Icône personnalisée non trouvée"
        Write-ColorOutput "Utilisation de l'icône par défaut" "Cyan"
    }

    $Shortcut.Save()

    Write-Success "Raccourci créé avec succès"
    Write-ColorOutput "Emplacement: $ShortcutPath" "Cyan"
    Write-ColorOutput "Double-cliquez pour lancer BoutiqueGest" "Cyan"

} catch {
    Write-Error "Erreur lors de la création du raccourci: $_"
    exit 1
}
