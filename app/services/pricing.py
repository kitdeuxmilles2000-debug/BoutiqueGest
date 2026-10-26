"""Calculs de prix : marge, stock exprime en unites de vente, types de mesure.

Le stock est compte dans l'unite de base (ml, g, cm, piece...). Chaque unite de
vente a un facteur vers cette base (ex. verre de 200 ml = facteur 200 en ml).
"""
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.models.user import get_setting
from app.services.stock import dec

TARGET_MARGIN_SETTING = "marge_objectif_defaut"
DEFAULT_TARGET_MARGIN = Decimal("20")

# code -> (libelle, code de l'unite de stock proposee, aide)
TYPES_MESURE = {
    "liquide": (
        "Liquide en contenant (lait, eau, huile)",
        "ML",
        "Stock compte en ml : 20 L = 20 000 ml. Vendez au verre, bouteille ou bidon.",
    ),
    "poids": (
        "Au poids (farine, sucre, engrais)",
        "G",
        "Stock compte en g. Vendez au kg, au sachet ou au gramme.",
    ),
    "longueur": (
        "Au mètre (tissu, fil, câble)",
        "CM",
        "Stock compte en cm. Vendez au mètre ou à la coupe.",
    ),
    "piece": (
        "Pièce / matériel",
        "PIECE",
        "Stock compté à la pièce. Vendez à la pièce ou au lot.",
    ),
    "carton": (
        "Carton / casier",
        "PIECE",
        "Stock compté à la pièce. Vendez au carton ou casier (facteur = nombre de pièces).",
    ),
    "autre": ("Autre", None, ""),
}


def default_target_margin():
    """Objectif de marge par defaut (Parametres), en %."""
    return dec(get_setting(TARGET_MARGIN_SETTING, str(DEFAULT_TARGET_MARGIN)))


def target_margin(product):
    """Marge cible en % : celle du produit, sinon l'objectif par defaut."""
    if product.marge_cible is not None:
        return dec(product.marge_cible)
    return default_target_margin()


def default_sale_unit(product):
    """Unite de vente proposee : celle marquee par defaut, sinon la premiere hors base."""
    secondary = [
        pu for pu in product.selling_units
        if pu.unit_id != product.base_unit_id and dec(pu.factor) > 0
    ]
    for pu in secondary:
        if pu.is_sale_default:
            return pu
    return secondary[0] if secondary else None


def sale_unit_cost(product, pu):
    """Cout d'une unite de vente = cout moyen par unite de base x facteur."""
    return dec(product.cost_avg) * dec(pu.factor)


def margin_status(price, unit_cost, target):
    """Niveau de marge : none (pas de prix), loss (a perte), low (sous l'objectif), ok."""
    price = dec(price)
    cost = dec(unit_cost)
    if price <= 0:
        return {"level": "none", "percent": None, "margin": None}
    margin = price - cost
    percent = (margin * 100 / price).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if margin < 0:
        level = "loss"
    elif percent < dec(target):
        level = "low"
    else:
        level = "ok"
    return {"level": level, "percent": percent, "margin": margin}


def fmt_qty(value):
    """Quantite lisible en francais : 37 ; 0,5 ; 120."""
    value = dec(value)
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f").replace(".", ",")


def stock_in_sale_units(product, pu=None):
    """Stock exprime en unites de vente, ex. '37 Verre + 120 ml'."""
    stock = dec(product.stock_qty)
    base_code = product.base_unit.code if product.base_unit else ""
    if pu is None:
        pu = default_sale_unit(product)
    if pu is None or stock <= 0:
        return f"{fmt_qty(stock)} {base_code}".strip()
    factor = dec(pu.factor)
    count = int((stock / factor).to_integral_value(rounding=ROUND_DOWN))
    rest = stock - count * factor
    text = f"{count} {pu.unit.label}"
    if rest > 0:
        text += f" + {fmt_qty(rest)} {base_code}"
    return text
