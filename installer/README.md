# Installateur BoutiqueGest

Ce dossier contient tous les scripts nécessaires pour l'installation automatisée de BoutiqueGest sur Windows.

## 📋 Contenu

| Fichier | Description |
|---------|-------------|
| `install.ps1` | Script principal d'installation automatisée |
| `start_app.bat` | Script de démarrage de l'application |
| `check_python.ps1` | Vérification de Python et des prérequis |
| `create_shortcut.ps1` | Création du raccourci bureau |
| `generate_icon.py` | Génération de l'icône de l'application |
| `config_waitress.py` | Test de configuration Waitress |
| `python-3.12.3-amd64.exe` | Installateur Python (à placer ici) |

## 🚀 Installation rapide

### Option 1: Installation complète (recommandée)

1. Télécharger Python 3.12.3 et placer `python-3.12.3-amd64.exe` dans ce dossier
2. Ouvrir PowerShell en tant qu'administrateur
3. Exécuter:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
cd C:\Users\kitima\Desktop\BoutiqueGest\installer
.\install.ps1
```

### Option 2: Installation manuelle étape par étape

1. **Vérifier les prérequis**
```powershell
.\check_python.ps1
```

2. **Installer Python** (si non installé)
- Télécharger depuis https://www.python.org/downloads/
- Installer avec l'option "Add Python to PATH"

3. **Générer l'icône** (optionnel)
```powershell
python generate_icon.py
```

4. **Lancer l'installation**
```powershell
.\install.ps1
```

5. **Créer le raccourci bureau** (si l'installation ne l'a pas fait)
```powershell
.\create_shortcut.ps1
```

## 🔧 Détails de l'installation

Le script `install.ps1` effectue automatiquement:

1. ✅ Vérification des droits administrateur
2. ✅ Installation de Python 3.12.3 (si nécessaire)
3. ✅ Création de l'environnement virtuel `.venv`
4. ✅ Installation des dépendances depuis `requirements.txt`
5. ✅ Migration de la base de données
6. ✅ Peuplement des données de référence
7. ✅ Création du script de démarrage
8. ✅ Création du raccourci bureau avec icône

## 📦 Configuration Waitress

L'application utilise Waitress comme serveur WSGI pour la production avec les optimisations suivantes:

- **Host**: 127.0.0.1 (localhost uniquement)
- **Port**: 5000
- **Threads**: 8 workers
- **Connection limit**: 1000 connexions simultanées
- **Channel timeout**: 120 secondes
- **Buffer size**: 64 KB (envoi/réception)
- **Max request body**: 10 MB

Pour tester la configuration:
```powershell
python config_waitress.py
```

## 🎯 Démarrage de l'application

### Via le raccourci bureau
- Double-cliquez sur "BoutiqueGest" sur votre bureau

### Via le script
```powershell
.\start_app.bat
```

### Via la ligne de commande
```powershell
cd C:\Users\kitima\Desktop\BoutiqueGest
.venv\Scripts\activate
python run_waitress.py
```

## 🔐 Accès par défaut

- **URL**: http://127.0.0.1:5000
- **Utilisateur**: admin
- **Mot de passe**: admin123

⚠️ **Important**: Changez le mot de passe admin après la première connexion!

## 🔍 Dépannage

### Python n'est pas reconnu
```powershell
# Vérifiez que Python est dans le PATH
python --version

# Si non, réinstallez Python avec "Add Python to PATH"
```

### Erreur lors de l'installation des dépendances
```powershell
# Mettez à jour pip
python -m pip install --upgrade pip

# Réessayez l'installation
.\install.ps1 -Force
```

### Le serveur ne démarre pas
```powershell
# Vérifiez que le port 5000 n'est pas utilisé
netstat -ano | findstr :5000

# Testez la configuration Waitress
python config_waitress.py
```

### Erreur de base de données
```powershell
# Ne supprimez pas la base : cela effacerait les données de la boutique.
# Vérifiez le fichier .env et la sauvegarde, puis appliquez les migrations.
cd C:\Users\kitima\Desktop\BoutiqueGest
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe -m flask --app run seed
```

## 📝 Paramètres avancés

### Réinstaller proprement
```powershell
.\install.ps1 -Force
```

### Installation silencieuse
```powershell
.\install.ps1 -Silent
```

### Changer le nom du raccourci
```powershell
.\create_shortcut.ps1 -ShortcutName "MaBoutique"
```

## 🚀 Performance

L'installation est optimisée pour:
- ✅ Démarrage rapide (< 3 secondes)
- ✅ Utilisation minimale des ressources
- ✅ Stabilité en production
- ✅ Gestion des connexions multiples
- ✅ Cache des fichiers statiques

## 📞 Support

En cas de problème:
1. Vérifiez les logs dans la console
2. Consultez le fichier `README.md` du projet principal
3. Vérifiez que tous les prérequis sont satisfaits avec `check_python.ps1`

---

**Version**: 1.0
**Date**: 2026-10-27
**Auteur**: Devin AI
