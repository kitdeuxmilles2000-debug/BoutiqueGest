$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopPath\BoutiqueGest.lnk"
$TargetPath = "C:\BoutiqueGest\INSTALL_BOUTIQUEGEST\SCRIPTS\lancer.bat"
$IconPath = "C:\BoutiqueGest\INSTALL_BOUTIQUEGEST\ASSETS\BoutiqueGest.ico"
$WorkingDir = "C:\BoutiqueGest"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $WorkingDir
$Shortcut.IconLocation = $IconPath
$Shortcut.Description = "BoutiqueGest - Gestion de boutique"
$Shortcut.Save()
