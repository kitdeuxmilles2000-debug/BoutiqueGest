# -*- coding: utf-8 -*-
# Script de désinstallation de BoutiqueGest

param(
    [switch]$Force = $false,
    [switch]$RemoveData = $false
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
$VenvPath = "$ProjectRoot\.venv"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\BoutiqueGest.lnk"

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

Write-ColorOutput "
============================================================
           DESINSTALLATION BOUTIQUEGEST
============================================================
" "Cyan"

if (-not $Force) {
    $response = Read-Host "Etes-vous sûr de vouloir désinstaller BoutiqueGest? (O/N)"
    if ($response -ne "O" -and $response -ne "o") {
        Write-Info "Desinstallation annulee"
        exit 0
    }
}

if ($RemoveData) {
    $response = Read-Host "ATTENTION: Cela supprimera toutes les données (base de données, sauvegardes). Continuer? (O/N)"
    if ($response -ne "O" -and $response -ne "o") {
        Write-Info "Desinstallation annulee"
        exit 0
    }
}

try {
    # Supprimer le raccourci bureau
    Write-Info "Suppression du raccourci bureau..."
    if (Test-Path $ShortcutPath) {
        Remove-Item -Path $ShortcutPath -Force
        Write-Success "Raccourci supprime"
    } else {
        Write-Warning "Raccourci non trouve"
    }

    # Supprimer l'environnement virtuel
    Write-Info "Suppression de l'environnement virtuel..."
    if (Test-Path $VenvPath) {
        Remove-Item -Path $VenvPath -Recurse -Force
        Write-Success "Environnement virtuel supprime"
    } else {
        Write-Warning "Environnement virtuel non trouve"
    }

    # Supprimer les données si demandé
    if ($RemoveData) {
        Write-Info "Suppression des donnees..."
        $dataPaths = @(
            "$ProjectRoot\instance",
            "$ProjectRoot\backups",
            "$ProjectRoot\uploads"
        )

        foreach ($path in $dataPaths) {
            if (Test-Path $path) {
                Remove-Item -Path $path -Recurse -Force
                Write-Success "Dossier supprime: $path"
            }
        }
    } else {
        Write-Info "Donnees conservees (instance, backups, uploads)"
    }

    Write-ColorOutput "
============================================================
           DESINSTALLATION TERMINEE AVEC SUCCES
============================================================
" "Green"

    if (-not $RemoveData) {
        Write-Info "Les donnees ont ete conservees dans:"
        Write-Info "  - instance\boutiquegest.db"
        Write-Info "  - backups\"
        Write-Info "  - uploads\"
        Write-Info ""
        Write-Info "Pour supprimer definitivement les donnees, relancez avec -RemoveData"
    }

} catch {
    Write-Error "Erreur lors de la desinstallation: $_"
    exit 1
}
