# -*- coding: utf-8 -*-
"""
Lancement de BoutiqueGest en local avec Waitress
Accès : http://127.0.0.1:5000
"""

import os
import webbrowser
from threading import Timer

from waitress import serve

from app import create_app

app = create_app(os.environ.get("FLASK_CONFIG", "dev"))


def open_browser():
    try:
        webbrowser.open("http://127.0.0.1:5000")
    except Exception:
        pass


if __name__ == "__main__":
    print("=" * 50)
    print("BOUTIQUEGEST - DEMARRAGE EN COURS")
    print("=" * 50)
    print("Adresse : http://127.0.0.1:5000")
    print("Pour arreter : CTRL + C")
    print("=" * 50)
    Timer(1.5, open_browser).start()
    serve(app, host="127.0.0.1", port=5000, threads=6, channel_timeout=120)
