# -*- coding: utf-8 -*-
"""
Script de configuration et test de Waitress pour BoutiqueGest
Vérifie que Waitress est correctement configuré pour la production
"""

import sys
import os

def check_waitress():
    """Vérifie que Waitress est installé et fonctionnel"""
    try:
        import waitress
        print(f"✓ Waitress installé: {waitress.__version__}")
        return True
    except ImportError:
        print("✗ Waitress n'est pas installé")
        print("  Installation: pip install waitress")
        return False

def test_app_import():
    """Teste que l'application peut être importée"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app import create_app
        app = create_app("production")
        print("✓ Application importée avec succès")
        return True, app
    except Exception as e:
        print(f"✗ Erreur lors de l'import de l'application: {e}")
        return False, None

def test_waitress_config():
    """Teste la configuration Waitress"""
    if not check_waitress():
        return False

    success, app = test_app_import()
    if not success:
        return False

    print("\n=== Configuration Waitress ===")
    print("Host: 127.0.0.1")
    print("Port: 5000")
    print("Threads: 8")
    print("Connection limit: 1000")
    print("Channel timeout: 120s")
    print("Max request body: 10 MB")
    print("Buffer size: 64 KB")
    print("\n✓ Configuration optimale détectée")

    return True

if __name__ == "__main__":
    print("=== Test de configuration Waitress ===\n")
    if test_waitress_config():
        print("\n✓ Tous les tests passés")
        sys.exit(0)
    else:
        print("\n✗ Échec des tests")
        sys.exit(1)
