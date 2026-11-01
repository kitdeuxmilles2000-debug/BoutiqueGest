# -*- coding: utf-8 -*-
"""
Génération d'une icône professionnelle pour BoutiqueGest
Crée une icône SVG qui peut être convertie en ICO
"""

import os
import sys

# Forcer l'encodage UTF-8 pour la sortie console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def generate_svg_icon():
    """Génère une icône SVG moderne et professionnelle"""
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#4CAF50;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#2E7D32;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#FF9800;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#F57C00;stop-opacity:1" />
    </linearGradient>
  </defs>

  <!-- Fond circulaire -->
  <circle cx="256" cy="256" r="240" fill="url(#grad1)" />

  <!-- Icône de boutique (panier) -->
  <g transform="translate(128, 128)">
    <!-- Corps du panier -->
    <path d="M 20 60 L 40 200 L 200 200 L 220 60 Z" fill="#FFFFFF" stroke="#1B5E20" stroke-width="4" />

    <!-- Anse du panier -->
    <path d="M 60 60 C 60 20, 180 20, 180 60" fill="none" stroke="#FFFFFF" stroke-width="8" stroke-linecap="round" />

    <!-- Produits dans le panier -->
    <rect x="50" y="90" width="40" height="50" rx="5" fill="url(#grad2)" />
    <rect x="100" y="80" width="40" height="60" rx="5" fill="#FFC107" />
    <rect x="150" y="95" width="40" height="45" rx="5" fill="#FF6F00" />

    <!-- Symbole dollar -->
    <circle cx="70" cy="115" r="15" fill="#FFFFFF" />
    <text x="70" y="122" font-family="Arial" font-size="20" font-weight="bold" fill="#2E7D32" text-anchor="middle">$</text>
  </g>

  <!-- Étiquette BG -->
  <rect x="156" y="350" width="200" height="60" rx="10" fill="#FFFFFF" opacity="0.95" />
  <text x="256" y="390" font-family="Arial" font-size="32" font-weight="bold" fill="#2E7D32" text-anchor="middle">BG</text>
</svg>"""

    script_dir = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(script_dir, "icon.svg")

    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)

    print(f"[OK] Icône SVG générée: {svg_path}")
    return svg_path

def generate_ico_from_svg():
    """Tente de convertir SVG en ICO si PIL est disponible"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        # Créer une image PNG directement avec PIL
        size = 256
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fond circulaire vert
        center = size // 2
        radius = size // 2 - 20
        draw.ellipse([center - radius, center - radius, center + radius, center + radius],
                     fill=(76, 175, 80, 255))

        # Corps du panier (blanc)
        basket_left = center - 100
        basket_top = center - 20
        basket_right = center + 100
        basket_bottom = center + 80
        draw.rectangle([basket_left, basket_top, basket_right, basket_bottom],
                      fill=(255, 255, 255, 255), outline=(27, 94, 32, 255), width=4)

        # Anse du panier
        draw.arc([basket_left + 20, basket_top - 40, basket_right - 20, basket_top + 20],
                start=180, end=0, fill=(255, 255, 255, 255), width=10)

        # Produits
        draw.rectangle([basket_left + 30, basket_top + 20, basket_left + 70, basket_top + 70],
                      fill=(255, 152, 0, 255))
        draw.rectangle([basket_left + 80, basket_top + 10, basket_left + 120, basket_top + 70],
                      fill=(255, 193, 7, 255))
        draw.rectangle([basket_left + 130, basket_top + 25, basket_left + 170, basket_top + 70],
                      fill=(255, 111, 0, 255))

        # Étiquette BG
        label_x = center - 80
        label_y = basket_bottom + 30
        draw.rectangle([label_x, label_y, label_x + 160, label_y + 50],
                      fill=(255, 255, 255, 255))

        # Texte BG
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except:
            font = ImageFont.load_default()

        text = "BG"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = label_x + (160 - text_width) // 2
        text_y = label_y + (50 - text_height) // 2
        draw.text((text_x, text_y), text, fill=(46, 125, 50, 255), font=font)

        # Sauvegarder en ICO avec plusieurs tailles
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(os.path.join(os.path.dirname(__file__), "icon.ico"), format='ICO', sizes=sizes)

        print("[OK] Icône ICO générée avec succès")
        return True

    except ImportError:
        print("[WARN] PIL non disponible, icône ICO non générée")
        print("       Installation optionnelle: pip install pillow")
        return False
    except Exception as e:
        print(f"[WARN] Erreur lors de la génération ICO: {e}")
        return False

if __name__ == "__main__":
    print("=== Génération de l'icône BoutiqueGest ===")
    generate_svg_icon()
    generate_ico_from_svg()
    print("\nTerminé")
