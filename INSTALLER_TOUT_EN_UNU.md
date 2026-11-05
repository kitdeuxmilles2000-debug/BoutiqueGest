# INSTALLATEUR AUTOMATIQUE - UN SEUL CLIC

## 🚀 Installation ultra-simple

### Pour BoutiqueGest

1. **Double-cliquez sur** `INSTALLER_AUTOMATIQUE.bat`
2. **Attendez** que l'installation se termine (quelques minutes)
3. **L'application démarre automatiquement**

### Pour AVPH_SYSTEM

1. **Double-cliquez sur** `INSTALLER_AUTOMATIQUE.bat`
2. **Attendez** que l'installation se termine (quelques minutes)
3. **L'application démarme automatiquement**

## ✅ Ce que fait l'installateur automatiquement

L'installateur `INSTALLER_AUTOMATIQUE.bat` fait **tout** pour vous:

1. ✅ **Vérifie les droits administrateur** (les demande si nécessaire)
2. ✅ **Télécharge Python 3.12.3** depuis internet (si non installé)
3. ✅ **Installe Python** automatiquement en mode silencieux
4. ✅ **Crée l'environnement virtuel** `.venv`
5. ✅ **Installe toutes les dépendances** depuis `requirements.txt`
6. ✅ **Installe Waitress** (serveur de production)
7. ✅ **Initialise la base de données** (BoutiqueGest uniquement)
8. ✅ **Crée le raccourci bureau** avec icône
9. ✅ **Lance l'application** automatiquement

## 🎯 Fonctionne même sur machine neuve

Cet installateur fonctionne sur **n'importe quel ordinateur Windows**, même:
- ✅ Sans Python préinstallé
- ✅ Sans environnement virtuel
- ✅ Sans dépendances
- ✅ Machine neuve ou formatée

## 📋 Prérequis

- **Windows 10 ou 11**
- **Connexion internet** (pour télécharger Python si nécessaire)
- **Droits administrateur** (demandés automatiquement)

## 🔐 Après l'installation

### BoutiqueGest
- **URL**: http://127.0.0.1:5000
- **Utilisateur**: admin
- **Mot de passe**: admin123
- ⚠️ **Changez le mot de passe après la première connexion!**

### AVPH_SYSTEM
- **URL**: http://127.0.0.1:5000
- Au premier démarrage, créez le compte administrateur
- Le mot de passe doit contenir au moins 12 caractères

## 🎯 Utilisation quotidienne

Après l'installation initiale, utilisez simplement:
- **Double-cliquez sur le raccourci bureau** (BoutiqueGest ou AVPH_SYSTEM)

## 📝 Notes importantes

1. **Première installation**: Prend 5-10 minutes (téléchargement Python)
2. **Installations suivantes**: Prend 1-2 minutes (Python déjà installé)
3. **Mise à jour**: Relancez `INSTALLER_AUTOMATIQUE.bat` pour mettre à jour
4. **Désinstallation**: Utilisez `installer\uninstall.ps1`

## 🔧 Dépannage

### Problème: "Echec du téléchargement de Python"
- **Solution**: Vérifiez votre connexion internet
- **Alternative**: Téléchargez manuellement Python depuis python.org et installez

### Problème: "Droits administrateur requis"
- **Solution**: Cliquez droit sur le fichier et "Exécuter en tant qu'administrateur"

### Problème: L'application ne démarre pas
- **Solution**: Vérifiez que le port 5000 n'est pas utilisé par une autre application

## 📞 Support

En cas de problème:
1. Consultez le dossier `installer\` pour les scripts détaillés
2. Consultez `README.md` du projet principal
3. Vérifiez les messages d'erreur dans la console

---

**Version**: 2.0 (Tout-en-un)
**Date**: 2026-10-27
**Auteur**: Devin AI
