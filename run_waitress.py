# -*- coding: utf-8 -*-
"""
Lancement de BoutiqueGest en local avec Waitress.

Accès local : http://127.0.0.1:PORT
Accès réseau local (Wi-Fi/LAN) : http://<IP_DE_CET_ORDINATEUR>:PORT
  (les autres appareils doivent être sur le même réseau)

Variables d'environnement optionnelles :
  HOST  (défaut 0.0.0.0 = accessible sur le réseau local)
  PORT  (défaut 5000)
"""

import os
import socket
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


def _lan_ip():
    """Best-effort LAN IP for display (no external network traffic required)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
        finally:
            sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


def open_browser(url):
    """Ouvre le navigateur automatiquement après démarrage."""
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    try:
        port = int(os.environ.get("PORT", "5000"))
    except (TypeError, ValueError):
        port = 5000

    local_url = f"http://127.0.0.1:{port}"
    lan_ip = _lan_ip()
    lan_url = f"http://{lan_ip}:{port}" if lan_ip else None

    print("=" * 60)
    print("BOUTIQUEGEST - DÉMARRAGE EN COURS")
    print("=" * 60)
    print(f"Accès local      : {local_url}")
    if lan_url and host in ("0.0.0.0", "::"):
        print(f"Accès réseau LAN : {lan_url}")
        print("  (même Wi-Fi/réseau : ouvrez cette adresse sur un autre appareil)")
        print("  Si bloqué, autorisez Python/port dans le pare-feu Windows.")
    elif host not in ("0.0.0.0", "::"):
        print(f"Accès configuré  : http://{host}:{port}")
    print("Pour arrêter : CTRL + C")
    print("=" * 60)

    # Ouvrir le navigateur local après 1.5 secondes
    Timer(1.5, open_browser, args=(local_url,)).start()

    # Configuration Waitress optimisée
    serve(
        app,
        host=host,
        port=port,
        threads=8,                       # Threads workers
        channel_timeout=120,             # Timeout connexion inactive
        connection_limit=1000,           # Limite connexions simultanées
        max_request_body_size=10485760,  # 10 MB max body
        send_bytes=65536,                # 64 KB buffer envoi
        recv_bytes=65536,                # 64 KB buffer réception
        ident="BoutiqueGest",            # Identifiant serveur
        url_prefix="",                   # Pas de préfixe URL
        clear_untrusted_proxy_headers=True,  # Sécurité proxy
    )
