# -*- coding: utf-8 -*-
# Script de vérification de Python pour BoutiqueGest
# Ce script vérifie si Python est installé et sa version

$ErrorActionPreference = "Stop"
$script:PythonCommand = $null

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

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-PythonVersion {
    param(
        [string]$Major = "3",
        [string]$Minor = "12"
    )

    try {
        $script:PythonCommand = Find-SystemPython
        if ($script:PythonCommand) {
            $versionString = [string]$script:PythonCommand.Version -replace "Python ", ""
            $version = [version]$versionString

            Write-ColorOutput "[OK] Python détecté: $versionString" "Green"

            if ($version.Major -eq [int]$Major -and $version.Minor -ge [int]$Minor) {
                Write-ColorOutput "[OK] Version compatible (>= $Major.$Minor)" "Green"
                return $true
            } else {
                Write-ColorOutput "[WARN] Version recommandée: $Major.$Minor" "Yellow"
                Write-ColorOutput "       Version actuelle: $versionString" "Yellow"
                return $true
            }
        }
    } catch {
        Write-ColorOutput "[ERROR] Python n'est pas installé" "Red"
        return $false
    }

    return $false
}

function Test-Pip {
    try {
        if (-not $script:PythonCommand) { return $false }
        $pythonArgs = @($script:PythonCommand.Prefix) + @("-m", "pip", "--version")
        $output = & $script:PythonCommand.Path @pythonArgs 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "[OK] Pip détecté: $output" "Green"
            return $true
        }
    } catch {
        Write-ColorOutput "[ERROR] Pip n'est pas installé" "Red"
        return $false
    }
    return $false
}

function Test-Venv {
    try {
        if (-not $script:PythonCommand) { return $false }
        $pythonArgs = @($script:PythonCommand.Prefix) + @("-m", "venv", "--help")
        $output = & $script:PythonCommand.Path @pythonArgs 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "[OK] Module venv disponible" "Green"
            return $true
        }
    } catch {
        Write-ColorOutput "[ERROR] Module venv non disponible" "Red"
        return $false
    }
    return $false
}

Write-ColorOutput "
============================================================
           VERIFICATION PYTHON - BOUTIQUEGEST
============================================================
" "Cyan"

Write-Host ""
Write-ColorOutput "=== Verification de Python ===" "Magenta"
$pythonOk = Test-PythonVersion

Write-Host ""
Write-ColorOutput "=== Verification de Pip ===" "Magenta"
$pipOk = Test-Pip

Write-Host ""
Write-ColorOutput "=== Verification du module venv ===" "Magenta"
$venvOk = Test-Venv

Write-Host ""
Write-ColorOutput "=== Resultat ===" "Magenta"

if ($pythonOk -and $pipOk -and $venvOk) {
    Write-ColorOutput "[OK] Tous les prerequis sont satisfaits" "Green"
    Write-ColorOutput "     Vous pouvez proceder a l'installation" "Green"
    exit 0
} else {
    Write-ColorOutput "[ERROR] Certains prerequis manquent" "Red"
    Write-ColorOutput "        Veuillez installer Python 3.12 ou superieur" "Red"
    Write-ColorOutput "        Telechargement: https://www.python.org/downloads/" "Cyan"
    exit 1
}
