$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$FilesRoot = Join-Path $PackageRoot "Fichiers"

function Copy-UpdateDirectory {
    param([string]$Name)

    $source = Join-Path $FilesRoot $Name
    if (-not (Test-Path $source)) {
        throw "Dossier de mise a jour absent : $source"
    }
    & robocopy $source (Join-Path $ProjectRoot $Name) /E /COPY:DAT /R:2 /W:1 /XD "__pycache__" /XF "*.pyc" | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "La copie de $Name a echoue (code robocopy $LASTEXITCODE)."
    }
}

function Copy-UpdateFile {
    param([string]$Name)

    $source = Join-Path $FilesRoot $Name
    if (-not (Test-Path $source)) {
        throw "Fichier de mise a jour absent : $source"
    }
    Copy-Item -LiteralPath $source -Destination $ProjectRoot -Force
}

try {
    if (-not (Test-Path (Join-Path $FilesRoot "app")) -or -not (Test-Path (Join-Path $FilesRoot "migrations"))) {
        throw "Le dossier Fichiers est incomplet. Recree le paquet depuis le projet."
    }

    $defaultPath = "C:\BoutiqueGest"
    if (-not (Test-Path $defaultPath)) {
        $defaultPath = ""
    }
    $answer = Read-Host "Chemin de l'installation BoutiqueGest (Entrée pour '$defaultPath')"
    $ProjectRoot = if ($answer.Trim()) { [System.IO.Path]::GetFullPath($answer.Trim('" ')) } else { $defaultPath }
    if (-not $ProjectRoot -or -not (Test-Path (Join-Path $ProjectRoot "run_waitress.py"))) {
        throw "Installation introuvable. Indiquez le dossier qui contient run_waitress.py."
    }
    if (-not (Test-Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe"))) {
        throw "Environnement Python introuvable. Cette mise a jour exige une installation BoutiqueGest deja fonctionnelle."
    }

    Write-Host ""
    Write-Host "Fermez BoutiqueGest sur cet ordinateur avant de continuer." -ForegroundColor Yellow
    $closed = Read-Host "L'application est-elle fermee ? (O/N)"
    if ($closed -notmatch "^(o|oui)$") {
        Write-Host "Operation annulee. Aucune modification effectuee." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Copie des fichiers de l'application..." -ForegroundColor Cyan
    Copy-UpdateDirectory "app"
    Copy-UpdateDirectory "migrations"
    Copy-UpdateDirectory "installer"
    foreach ($file in @("requirements.txt", "run.py", "run_waitress.py", "wsgi.py", "MISE_A_JOUR_CLIENT.bat")) {
        Copy-UpdateFile $file
    }

    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    Write-Host "Mise a jour des dependances Python..." -ForegroundColor Cyan
    & $python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Installation des dependances echouee. La base de donnees n'a pas ete modifiee."
    }

    $shortcutScript = Join-Path $ProjectRoot "installer\create_shortcut.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $shortcutScript -Force
    if ($LASTEXITCODE -ne 0) {
        throw "Les fichiers sont copies mais la reparation du raccourci a echoue."
    }

    Write-Host ""
    Write-Host "Les fichiers de l'application sont mis a jour. La base SQLite, .env, .venv, backups et uploads n'ont pas ete copies ni supprimes." -ForegroundColor Green
    $migrate = Read-Host "Faut-il appliquer les migrations de base ? Une sauvegarde verifiee sera creee avant (O/N)"
    if ($migrate -match "^(o|oui)$") {
        $migrationScript = Join-Path $ProjectRoot "MISE_A_JOUR_CLIENT.bat"
        $process = Start-Process -FilePath $env:ComSpec -ArgumentList @("/c", "`"$migrationScript`"") -Wait -NoNewWindow -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Migration non terminee. La sauvegarde prealable, si elle a ete creee, est conservee."
        }
    } else {
        Write-Host "Aucune migration executee. Si l'application signale une mise a jour de base requise, relancez ce paquet et acceptez la migration apres verification de la sauvegarde." -ForegroundColor Yellow
    }

    $backupTaskScript = Join-Path $ProjectRoot "installer\Register-BackupTask.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $backupTaskScript -ProjectRoot $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "La mise a jour est appliquee, mais la sauvegarde automatique n'a pas ete programmee."
    }

    Write-Host ""
    Write-Host "Mise a jour terminee. Waitress et la sauvegarde quotidienne sont configures." -ForegroundColor Green
} catch {
    Write-Host "[ERREUR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
