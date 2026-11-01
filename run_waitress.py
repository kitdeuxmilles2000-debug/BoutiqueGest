# -*- coding: utf-8 -*-
"""
Lancement de BoutiqueGest en local avec Waitress
Accès : http://127.0.0.1:5000
Configuration optimisée pour performances maximales
"""

import os
import sys
import webbrowser
from threading import Timer

from dotenv import load_dotenv
from waitress import serve

load_dotenv()

from app import create_app

# Configuration Flask pour production
os.environ.setdefault("FLASK_CONFIG", "prod")

app = create_app(os.environ.get("FLASK_CONFIG", "prod"))

# Optimisations Flask
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000  # 1 an cache static


def open_browser():
    """Ouvre le navigateur automatiquement après démarrage"""
    try:
        webbrowser.open("http://127.0.0.1:5000")
    except Exception:
        pass


if __name__ == "__main__":
    print("=" * 60)
    print("BOUTIQUEGEST - DÉMARRAGE EN COURS")
    print("=" * 60)
    print("Adresse : http://127.0.0.1:5000")
    print("Pour arrêter : CTRL + C")
    print("=" * 60)

    # Ouvrir le navigateur après 1.5 secondes
    Timer(1.5, open_browser).start()

    # Configuration Waitress optimisée
    # - threads: nombre de threads workers (ajusté selon CPU)
    # - channel_timeout: timeout pour les connexions inactives
    # - connection_limit: limite de connexions simultanées
    # - send_bytes: taille du buffer d'envoi (optimisé)
    # - recv_bytes: taille du buffer de réception (optimisé)
    serve(
        app,
        host="127.0.0.1",
        port=5000,
        threads=8,                      # Threads workers
        channel_timeout=120,           # Timeout connexion inactive
        connection_limit=1000,          # Limite connexions simultanées
        max_request_body_size=10485760, # 10 MB max body
        send_bytes=65536,              # 64 KB buffer envoi
        recv_bytes=65536,              # 64 KB buffer réception
        ident="BoutiqueGest",          # Identifiant serveur
        url_prefix="",                 # Pas de préfixe URL
        clear_untrusted_proxy_headers=True  # Sécurité proxy
    )
