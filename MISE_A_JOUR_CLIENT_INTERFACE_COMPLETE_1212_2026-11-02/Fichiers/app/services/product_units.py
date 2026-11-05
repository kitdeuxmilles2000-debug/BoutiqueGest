"""Creation et synchronisation des formats de vente propres a un produit."""
from decimal import Decimal, InvalidOperation
import uuid

from app.extensions import db
from app.models.catalog import PriceHistory, PriceKind, ProductUnit, Unit

SALE_FORMAT_TYPES = {
    "liquide": {"ml", "l", "verre", "bidon", "bouteille", "custom"},
    "carton": {"piece", "carton", "paquet", "custom"},
    "couture": {"piece", "custom"},
    "poids": {"g", "kg", "portion", "sac", "custom"},
    "tissu": {"cm", "m", "rouleau", "custom"},
}


def _sale_unit_factor(format_type, amount, measure, preset, base_unit, custom_name):
    amount_label = format(amount, "f")
    if "." in amount_label:
        amount_label = amount_label.rstrip("0").rstrip(".")
    fixed_units = {
        "ml": ("Millilitre", "ml", Decimal("1")),
        "l": ("Litre", "l", Decimal("1")),
        "g": ("Gramme", "g", Decimal("1")),
        "kg": ("Kilogramme", "kg", Decimal("1")),
        "cm": ("Centimètre", "cm", Decimal("1")),
        "m": ("Mètre", "m", Decimal("1")),
        "piece": ("Pièce", "piece", Decimal("1")),
    }
    if format_type in fixed_units:
        label, expected_measure, fixed_amount = fixed_units[format_type]
        if amount != fixed_amount:
            raise ValueError(f"Le format {label} doit avoir un contenu de 1 {expected_measure}.")
        measure = expected_measure

    measures = {
        "liquide": {
            "ML": {"ml": Decimal("1"), "l": Decimal("1000")},
            "L": {"ml": Decimal("0.001"), "l": Decimal("1")},
        },
        "poids": {
            "G": {"g": Decimal("1"), "kg": Decimal("1000")},
            "KG": {"g": Decimal("0.001"), "kg": Decimal("1")},
        },
        "tissu": {
            "CM": {"cm": Decimal("1"), "m": Decimal("100")},
            "M": {"cm": Decimal("0.01"), "m": Decimal("1")},
        },
    }
    labels = {
        "ml": "Millilitre",
        "l": "Litre",
        "g": "Gramme",
        "kg": "Kilogramme",
        "cm": "Centimètre",
        "m": "Mètre",
        "piece": "Pièce",
        "verre": "Verre",
        "bidon": "Bidon",
        "bouteille": "Bouteille",
        "carton": "Carton",
        "paquet": "Paquet",
        "portion": "Portion",
        "sac": "Sac",
        "rouleau": "Rouleau",
    }

    if format_type == "verre":
        if (
            measure != "ml"
            or amount > Decimal("1000")
            or amount != amount.to_integral_value()
        ):
            raise ValueError("Un verre doit contenir entre 1 et 1000 ml.")
    if format_type in {"carton", "paquet"}:
        measure = "piece"
    if (
        base_unit.code == "PIECE"
        and preset in {"carton", "couture"}
        and amount != amount.to_integral_value()
    ):
        raise ValueError("Le nombre de pièces doit être un nombre entier.")
    if format_type == "custom" and measure == "base":
        factor = amount
        return factor, custom_name
    elif measure == "piece":
        if base_unit.code != "PIECE":
            raise ValueError("Les formats carton/pièce nécessitent un stock compté en pièces.")
        factor = amount
        suffix = "pièces"
    else:
        conversion = measures.get(preset, {}).get(base_unit.code, {}).get(measure)
        if conversion is None:
            raise ValueError("L'unité choisie ne correspond pas à l'unité de stock du produit.")
        factor = amount * conversion
        suffix = measure

    if format_type in fixed_units:
        return factor, fixed_units[format_type][0]
    suffix_label = {
        "ml": "ml",
        "l": "L",
        "g": "g",
        "kg": "kg",
        "cm": "cm",
        "m": "m",
        "piece": "pièces",
    }.get(suffix, suffix)
    if format_type == "custom":
        return factor, f"{custom_name} {amount_label} {suffix_label}"
    return factor, f"{labels[format_type]} {amount_label} {suffix_label}"


def _unit_has_history(unit_id):
    from app.models.purchases import PurchaseLine
    from app.models.sales import SaleLine
    from app.models.stock import StockEntryRequest, StockMovement

    return any(
        model.query.filter_by(unit_id=unit_id).first() is not None
        for model in (SaleLine, PurchaseLine, StockMovement, StockEntryRequest)
    )


def parse_sale_unit_rows(form, prefix, preset=None, base_unit=None):
    """Lit les lignes de format repetables et rejette toute ligne incomplete."""
    names = form.getlist(f"{prefix}_label")
    factors = form.getlist(f"{prefix}_factor")
    prices = form.getlist(f"{prefix}_price")
    ids = form.getlist(f"{prefix}_id")
    format_types = form.getlist(f"{prefix}_type")
    amounts = form.getlist(f"{prefix}_amount")
    measures = form.getlist(f"{prefix}_measure")
    custom_names = form.getlist(f"{prefix}_custom_label")
    default_index = form.get(f"{prefix}_default", type=int)
    row_count = max(
        len(names), len(factors), len(prices), len(ids), len(format_types),
        len(amounts), len(measures), len(custom_names),
    )
    rows = []
    seen_ids = set()
    seen_names = set()

    def decimal_value(value, label):
        try:
            result = Decimal((value or "").strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{label} doit etre un nombre valide.") from None
        if not result.is_finite():
            raise ValueError(f"{label} doit etre un nombre valide.")
        return result

    for index in range(row_count):
        name = names[index].strip() if index < len(names) else ""
        factor_raw = factors[index].strip() if index < len(factors) else ""
        price_raw = prices[index].strip() if index < len(prices) else ""
        unit_id_raw = ids[index].strip() if index < len(ids) else ""
        format_type = format_types[index].strip() if index < len(format_types) else ""
        amount_raw = amounts[index].strip() if index < len(amounts) else ""
        measure = measures[index].strip() if index < len(measures) else ""
        custom_name = custom_names[index].strip() if index < len(custom_names) else ""
        if not name and not factor_raw and not price_raw and not unit_id_raw:
            if not format_type and not amount_raw and not custom_name:
                continue
        if format_type:
            if preset not in SALE_FORMAT_TYPES or format_type not in SALE_FORMAT_TYPES[preset]:
                raise ValueError("Le format de vente ne correspond pas au type de produit.")
            if base_unit is None:
                raise ValueError("L'unité de stock est nécessaire pour convertir ce format.")
            amount = decimal_value(amount_raw, "Le contenu du format")
            if amount <= 0:
                raise ValueError("Le contenu de chaque format de vente doit être positif.")
            if format_type == "custom":
                if not custom_name:
                    raise ValueError("Donnez un nom au format de vente personnalisé.")
                name = custom_name
            factor, name = _sale_unit_factor(
                format_type, amount, measure, preset, base_unit, custom_name
            )
            factor_raw = str(factor)
        if not name or not factor_raw or not price_raw:
            raise ValueError("Chaque format de vente doit avoir un nom, un contenu et un prix.")
        if len(name) > 60:
            raise ValueError("Le nom d'un format de vente ne peut pas depasser 60 caracteres.")
        factor = decimal_value(factor_raw, "Le contenu du format")
        price = decimal_value(price_raw, "Le prix de vente")
        if factor <= 0:
            raise ValueError("Le contenu de chaque format de vente doit etre positif.")
        if price <= 0:
            raise ValueError("Le prix de chaque format de vente doit etre positif.")
        if factor.as_tuple().exponent < -4 or factor > Decimal("99999999999999.9999"):
            raise ValueError("Le contenu doit tenir sur 14 chiffres avant la virgule et 4 apres.")
        if price.as_tuple().exponent < -2 or price > Decimal("9999999999999999.99"):
            raise ValueError("Le prix doit tenir sur 16 chiffres avant la virgule et 2 apres.")
        normalized_name = name.casefold()
        if normalized_name in seen_names:
            raise ValueError("Chaque format de vente doit avoir un nom different.")
        seen_names.add(normalized_name)
        try:
            unit_id = int(unit_id_raw) if unit_id_raw else None
        except ValueError:
            raise ValueError("Identifiant de format de vente invalide.") from None
        if unit_id is not None:
            if unit_id in seen_ids:
                raise ValueError("Un format de vente ne peut pas etre ajoute deux fois.")
            seen_ids.add(unit_id)
        rows.append(
            {
                "unit_id": unit_id,
                "form_index": index,
                "label": name,
                "factor": factor,
                "price": price,
                "is_default": index == default_index,
            }
        )
    return rows


def save_product_sale_units(product, rows, currency):
    """Enregistre les formats libres, avec une unite distincte par conversion."""
    existing = {
        pu.unit_id: pu
        for pu in product.selling_units
        if pu.unit and pu.unit.product_id == product.id
    }
    submitted_ids = {row["unit_id"] for row in rows if row["unit_id"] is not None}
    if not submitted_ids.issubset(existing):
        raise ValueError("Un format de vente ne correspond pas a ce produit.")

    for unit_id, pu in existing.items():
        if unit_id not in submitted_ids:
            pu.active = False
            pu.is_sale_default = False

    default_selected = any(row["is_default"] for row in rows)
    if default_selected:
        ProductUnit.query.filter_by(product_id=product.id).update(
            {"is_sale_default": False}, synchronize_session=False
        )

    base_unit = db.session.get(Unit, product.base_unit_id)
    for row in rows:
        pu = existing.get(row["unit_id"]) if row["unit_id"] is not None else None
        if pu is None:
            code = f"P{uuid.uuid4().hex[:19].upper()}"
            unit = Unit(
                code=code,
                label=row["label"],
                kind=base_unit.kind,
                is_system=False,
                product_id=product.id,
            )
            db.session.add(unit)
            db.session.flush()
            pu = ProductUnit(product_id=product.id, unit_id=unit.id)
            db.session.add(pu)
            product.selling_units.append(pu)
        else:
            if (
                (pu.unit.label != row["label"] or pu.factor != row["factor"])
                and _unit_has_history(pu.unit_id)
            ):
                raise ValueError(
                    f"Le format « {pu.unit.label} » a deja ete utilise. "
                    "Retirez-le et creez un nouveau format pour conserver l'historique."
                )
            pu.unit.label = row["label"]
            if pu.prix_vente != row["price"] or pu.currency != currency:
                db.session.add(
                    PriceHistory(
                        product_id=product.id,
                        kind=PriceKind.VENTE,
                        prix=row["price"],
                        currency=currency,
                    )
                )
        pu.factor = row["factor"]
        pu.prix_vente = row["price"]
        pu.currency = currency
        pu.active = True
        if row["is_default"]:
            pu.is_sale_default = True
        row["unit_id"] = pu.unit_id
    db.session.flush()
