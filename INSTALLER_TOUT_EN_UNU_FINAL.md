# INSTALLATEUR AUTOMATIQUE - GUIDE FINAL

## 🎯 INSTALLATION EN UN SEUL CLIC - POUR LES CLIENTS

### BOUTIQUEGEST

**Fichier à utiliser**: `INSTALLER_AUTOMATIQUE.bat`

**Instructions pour le client**:
1. Double-cliquez sur `INSTALLER_AUTOMATIQUE.bat`
2. Acceptez la demande de droits administrateur (si demandée)
3. Attendez que l'installation se termine (5-10 minutes la première fois)
4. L'application démarre automatiquement
5. Un raccourci "BoutiqueGest" est créé sur le bureau

**Accès après installation**:
- Double-cliquez sur le raccourci "BoutiqueGest" sur le bureau
- URL: http://127.0.0.1:5000
- Utilisateur: admin
- Mot de passe: admin123
- ⚠️ Changez le mot de passe après la première connexion!

---

### AVPH_SYSTEM

**Fichier à utiliser**: `INSTALLER_AUTOMATIQUE.bat`

**Instructions pour le client**:
1. Double-cliquez sur `INSTALLER_AUTOMATIQUE.bat`
2. Acceptez la demande de droits administrateur (si demandée)
3. Attendez que l'installation se termine (5-10 minutes la première fois)
4. L'application démarre automatiquement
5. Un raccourci "AVPH_SYSTEM" est créé sur le bureau

**Accès après installation**:
- Double-cliquez sur le raccourci "AVPH_SYSTEM" sur le bureau
- URL: http://127.0.0.1:5000
- Au premier démarrage, créez le compte administrateur
- Le mot de passe doit contenir au moins 12 caractères

---

## ✅ CE QUE FAIT L'INSTALLATEUR AUTOMATIQUEMENT

L'installateur `INSTALLER_AUTOMATIQUE.bat` effectue **toutes** les étapes:

1. ✅ **Vérifie les droits administrateur** (les demande automatiquement)
2. ✅ **Vérifie si Python est installé**
3. ✅ **Télécharge Python 3.12.3** depuis internet (si nécessaire)
4. ✅ **Installe Python** en mode silencieux (sans intervention)
5. ✅ **Crée l'environnement virtuel** `.venv`
6. ✅ **Active l'environnement virtuel**
7. ✅ **Installe toutes les dépendances** depuis `requirements.txt`
8. ✅ **Installe Waitress** (serveur de production optimisé)
9. ✅ **Initialise la base de données** (BoutiqueGest uniquement)
10. ✅ **Crée le raccourci bureau** avec icône personnalisée
11. ✅ **Lance l'application** automatiquement

---

## 🎯 FONCTIONNE SUR MACHINE NEUVE

Cet installateur fonctionne sur **n'importe quel ordinateur Windows**:

- ✅ **Machine neuve** (sans Python)
- ✅ **Machine formatée**
- ✅ **Windows 10**
- ✅ **Windows 11**
- ✅ **Sans prérequis** (sauf connexion internet pour Python)

---

## 📋 PRÉREQUIS MINIMAUX

Pour les clients:
- **Windows 10 ou 11**
- **Connexion internet** (seulement pour la première installation, pour télécharger Python)
- **Droits administrateur** (l'installateur les demande automatiquement)

---

## ⏱️ TEMPS D'INSTALLATION

- **Première installation** (machine sans Python): 5-10 minutes
  - Téléchargement Python: ~3-5 minutes
  - Installation Python: ~1-2 minutes
  - Installation dépendances: ~1-2 minutes
  - Configuration: ~30 secondes

- **Installations suivantes** (Python déjà installé): 1-2 minutes

---

## 🎯 UTILISATION QUOTIDIENNE

Après l'installation initiale, l'utilisation est ultra-simple:

1. **Double-cliquez sur le raccourci bureau** (BoutiqueGest ou AVPH_SYSTEM)
2. L'application démarre en moins de 3 secondes
3. Utilisez l'application normalement

---

## 📝 LIVRAISON AUX CLIENTS

### Dossier à livrer pour BoutiqueGest:
```
BoutiqueGest/
├── INSTALLER_AUTOMATIQUE.bat  ← LE SEUL FICHIER NÉCESSAIRE
├── installer/                 (dossier optionnel pour scripts avancés)
├── app/
├── requirements.txt
├── run_waitress.py
└── ... (autres fichiers du projet)
```

### Dossier à livrer pour AVPH_SYSTEM:
```
AVPH_SYSTEM/
├── INSTALLER_AUTOMATIQUE.bat  ← LE SEUL FICHIER NÉCESSAIRE
├── installer/                 (dossier optionnel pour scripts avancés)
├── avph_system/
├── requirements.txt
├── run_waitress.py
└── ... (autres fichiers du projet)
```

---

## 🔧 DÉPANNAGE (POUR SUPPORT)

### Problème: "Echec du téléchargement de Python"
**Cause**: Pas de connexion internet
**Solution**:
- Vérifiez la connexion internet
- Téléchargez manuellement Python depuis https://www.python.org/downloads/
- Installez Python avec l'option "Add Python to PATH"
- Relancez `INSTALLER_AUTOMATIQUE.bat`

### Problème: "Droits administrateur requis"
**Cause**: L'utilisateur n'a pas les droits
**Solution**:
- Cliquez droit sur `INSTALLER_AUTOMATIQUE.bat`
- Sélectionnez "Exécuter en tant qu'administrateur"

### Problème: L'application ne démarre pas
**Cause**: Port 5000 déjà utilisé
**Solution**:
- Fermez les autres applications
- Redémarrez l'ordinateur
- Relancez le raccourci

### Problème: Erreur lors de l'installation des dépendances
**Cause**: Problème de connexion ou de version
**Solution**:
- Vérifiez la connexion internet
- Relancez `INSTALLER_AUTOMATIQUE.bat`
- Le script réessayera automatiquement

---

## 📞 SUPPORT TECHNIQUE

Si le client rencontre des problèmes:

1. **Première étape**: Relancez `INSTALLER_AUTOMATIQUE.bat`
2. **Vérifiez**: Les messages d'erreur dans la console noire
3. **Consultez**: Le fichier `INSTALLER_TOUT_EN_UNU.md`
4. **Contactez**: Le support technique avec les messages d'erreur

---

## 🔄 MISES À JOUR

Pour mettre à jour l'application:
1. Remplacez les fichiers du projet par les nouvelles versions
2. Relancez `INSTALLER_AUTOMATIQUE.bat`
3. L'installateur mettra à jour les dépendances automatiquement

---

## 🗑️ DÉSINSTALLATION

Pour désinstaller:
1. Utilisez `installer\uninstall.ps1` (dans le dossier installer)
2. Ou supprimez manuellement:
   - Le raccourci bureau
   - Le dossier `.venv`
   - Le dossier `instance` (données)

---

## ✅ AVANTAGES POUR LES CLIENTS

- ✅ **Ultra-simple**: Un seul double-clic
- ✅ **Automatique**: Tout est fait sans intervention
- ✅ **Rapide**: Installation en quelques minutes
- ✅ **Fiable**: Fonctionne sur machine neuve
- ✅ **Professionnel**: Icône et raccourci bureau
- ✅ **Optimisé**: Démarrage rapide (< 3 secondes)
- ✅ **Sécurisé**: Serveur localhost uniquement

---

## 📝 RÉSUMÉ POUR L'ÉQUIPE DE LIVRAISON

**Instructions aux clients**:
1. Copiez le dossier complet (BoutiqueGest ou AVPH_SYSTEM)
2. Dites au client: "Double-cliquez sur INSTALLER_AUTOMATIQUE.bat"
3. Attendez que l'installation se termine
4. L'application démarre automatiquement
5. Un raccourci est créé sur le bureau
6. Pour l'utiliser ensuite: double-cliquez sur le raccourci

**C'est tout!** Aucune autre manipulation nécessaire.

---

**Version**: 2.0 (Tout-en-un)
**Date**: 2026-10-27
**Auteur**: Devin AI
**Statut**: ✅ PRÊT POUR LIVRAISON
