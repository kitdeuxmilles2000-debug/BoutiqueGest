param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputPath) {
    $OutputPath = Join-Path $ProjectRoot "PAQUET_MAJ_CLIENT"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (Test-Path $OutputPath) {
    throw "Le dossier existe deja : $OutputPath. Choisissez un autre chemin pour ne pas melanger les versions."
}

$FilesPath = Join-Path $OutputPath "Fichiers"
New-Item -ItemType Directory -Force -Path $FilesPath | Out-Null

foreach ($directory in @("app", "migrations")) {
    $source = Join-Path $ProjectRoot $directory
    $destination = Join-Path $FilesPath $directory
    if (-not (Test-Path $source)) {
        throw "Dossier source introuvable : $source"
    }
    & robocopy $source $destination /E /COPY:DAT /R:2 /W:1 /XD "__pycache__" /XF "*.pyc" | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "La copie de $directory a echoue (code robocopy $LASTEXITCODE)."
    }
}

$installerFiles = Join-Path $FilesPath "installer"
New-Item -ItemType Directory -Force -Path $installerFiles | Out-Null
foreach ($file in @("start_app.bat", "create_shortcut.ps1", "Register-BackupTask.ps1", "install.ps1", "INSTALL.bat", "check_python.ps1", "icon.ico")) {
    $source = Join-Path $ProjectRoot "installer\$file"
    if (-not (Test-Path $source)) {
        throw "Fichier source introuvable : $source"
    }
    Copy-Item -LiteralPath $source -Destination $installerFiles
}

foreach ($file in @("requirements.txt", "run.py", "run_waitress.py", "wsgi.py", "MISE_A_JOUR_CLIENT.bat")) {
    $source = Join-Path $ProjectRoot $file
    if (-not (Test-Path $source)) {
        throw "Fichier source introuvable : $source"
    }
    Copy-Item -LiteralPath $source -Destination $FilesPath
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Mettre-A-Jour-Client.bat") -Destination $OutputPath
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Update-Client.ps1") -Destination $OutputPath
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "MISE_A_JOUR_CLIENT.txt") -Destination $OutputPath

Write-Host "Paquet client cree : $OutputPath" -ForegroundColor Green
Write-Host "Il ne contient ni base de donnees, ni .env, ni sauvegardes, ni environnement Python." -ForegroundColor Cyan
$global:LASTEXITCODE = 0
