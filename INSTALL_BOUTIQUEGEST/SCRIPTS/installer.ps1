# -*- coding: utf-8 -*-
# Installation automatique BoutiqueGest

$ErrorActionPreference = "SilentlyContinue"
$Host.UI.RawUI.WindowTitle = "Installation BoutiqueGest"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   INSTALLATION AUTOMATIQUE - BOUTIQUEGEST" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$source = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$target = "C:\BoutiqueGest"

Write-Host "[INFO] Copie vers : $target" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $target)) {
    Write-Host "[1/5] Copie des fichiers en cours..." -ForegroundColor Green
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    robocopy $source $target /E /XD ".git" ".venv" "__pycache__" "instance" "backups" 2>&1 | Out-Null
    Write-Host "[OK] Fichiers copies" -ForegroundColor Green
} else {
    Write-Host "[1/5] Mise a jour des fichiers..." -ForegroundColor Yellow
    robocopy "$source\app" "$target\app" /E 2>&1 | Out-Null
    robocopy "$source\migrations" "$target\migrations" /E 2>&1 | Out-Null
    Copy-Item "$source\run_waitress.py", "$source\wsgi.py", "$source\requirements.txt", "$source\Procfile" -Destination $target -Force 2>&1 | Out-Null
    Copy-Item "$source\INSTALL_BOUTIQUEGEST" "$target\INSTALL_BOUTIQUEGEST" -Recurse -Force 2>&1 | Out-Null
    Write-Host "[OK] Mise a jour effectuee" -ForegroundColor Green
}

Set-Location $target
Write-Host ""

Write-Host "[2/5] Verification de Python..." -ForegroundColor Green
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Host "[ERREUR] Python n'est pas installe. Installez Python 3.11/3.12 en cochant 'Add Python to PATH'." -ForegroundColor Red
    Read-Host "Appuyez sur Entree pour quitter"
    exit 1
}
Write-Host "[OK] Python detecte" -ForegroundColor Green
Write-Host ""

Write-Host "[3/5] Creation de l'environnement virtuel..." -ForegroundColor Green
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & python -m venv .venv
}
Write-Host "[OK] Environnement virtuel pret" -ForegroundColor Green
Write-Host ""

Write-Host "[4/5] Installation des dependances (5-10 minutes)..." -ForegroundColor Green
& "$target\.venv\Scripts\pip.exe" install --upgrade pip | Out-Null
& "$target\.venv\Scripts\pip.exe" install -r requirements.txt | Out-Null
Write-Host "[OK] Dependances installees" -ForegroundColor Green
Write-Host ""

Write-Host "[5/5] Creation du raccourci Bureau..." -ForegroundColor Green
& powershell -ExecutionPolicy Bypass -File "$target\INSTALL_BOUTIQUEGEST\SCRIPTS\create_shortcut.ps1"
Write-Host "[OK] Raccourci cree" -ForegroundColor Green
Write-Host ""

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   INSTALLATION TERMINEE AVEC SUCCES" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Lancez BoutiqueGest depuis le raccourci sur votre Bureau." -ForegroundColor Yellow
Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
