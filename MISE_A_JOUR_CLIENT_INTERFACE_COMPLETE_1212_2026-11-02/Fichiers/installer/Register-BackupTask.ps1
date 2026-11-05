param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python BoutiqueGest introuvable : $Python"
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "run.py"))) {
    throw "Fichier run.py introuvable dans $ProjectRoot"
}

$taskName = "BoutiqueGest - Sauvegarde quotidienne"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument '-m flask --app run backup-db --label automatique' `
    -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "2:00AM"
$principal = New-ScheduledTaskPrincipal `
    -UserId $identity `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Sauvegarde quotidienne verifiee de la base BoutiqueGest." `
    -Force | Out-Null

Write-Host "Sauvegarde automatique programmee chaque jour a 02:00." -ForegroundColor Green
Write-Host "La tache s'executera au prochain demarrage si l'heure prevue a ete manque." -ForegroundColor Cyan
Write-Host "La retention est geree par BACKUP_RETENTION (30 versions par defaut)." -ForegroundColor Cyan
