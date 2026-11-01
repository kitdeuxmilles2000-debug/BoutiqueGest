$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\BoutiqueGest.lnk"
$ScriptsPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptsPath)
$TargetPath = Join-Path $ScriptsPath "lancer.bat"
$IconPath = Join-Path (Split-Path -Parent $ScriptsPath) "ASSETS\BoutiqueGest.ico"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation = $IconPath
$Shortcut.Description = "BoutiqueGest - Gestion de boutique"
$Shortcut.Save()
