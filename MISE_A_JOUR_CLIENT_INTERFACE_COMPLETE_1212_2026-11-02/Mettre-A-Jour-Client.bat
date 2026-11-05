@echo off
setlocal
title BoutiqueGest - mise a jour client
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Client.ps1"
set "UPDATE_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%UPDATE_EXIT_CODE%"=="0" (
    echo [ERREUR] La mise a jour n'est pas terminee. Consultez le message ci-dessus.
) else (
    echo [OK] Operation terminee.
)
pause
exit /b %UPDATE_EXIT_CODE%
