@echo off
chcp 65001 > nul
title Installation BoutiqueGest
powershell -ExecutionPolicy Bypass -WindowStyle Normal -File "%~dp0SCRIPTS\installer.ps1"
pause
