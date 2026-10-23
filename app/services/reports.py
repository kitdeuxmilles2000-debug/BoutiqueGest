"""Rapports et indicateurs de gestion.

Périmètre : une période [date_debut, date_fin) bornée par bornes de jour.
Tous les montants restent **par devise** (jamais mélangés) ; la consolidation
multi-devises n'est faite qu'à titre indicatif.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.base import utcnow
from app.models.finance import Credit, CreditStatus, Expense, ExpenseStatus
from app.models.sales import (
    CASH_IN_KINDS,
    CASH_MOVEMENT_LABELS,
    CashMovement,
    CashSession,
    PaymentMethod,
    Sale,
    SaleStatus,
)
from app.services.stock import dec

PERIODE_LABELS = {
    "jour": "Aujourd'hui",
    "semaine": "Cette semaine",
    "mois": "Ce mois",
    "trimestre": "Ce trimestre",
    "annee": "Cette annee",
    "tout": "Tout l'historique",
}


def period_bounds(periode="jour", start=None, end=None):
    """Retourne (debut, fin) en datetimes naifs UTC pour la periode demandee."""
    today = utcnow().date()

    if periode == "jour":
        debut = today
        fin = today + timedelta(days=1)
    elif periode == "semaine":
        debut = today - timedelta(days=today.weekday())
        fin = debut + timedelta(days=7)
    elif periode == "mois":
        debut = today.replace(day=1)
        fin = (debut + timedelta(days=32)).replace(day=1)
    elif periode == "trimestre":
        q = (today.month - 1) // 3
        debut = date(today.year, q * 3 + 1, 1)
        fin = date(today.year + (1 if q == 3 else 0), (3 if q == 3 else q * 3 + 4), 1)
    elif periode == "annee":
        debut = date(today.year, 1, 1)
        fin = date(today.year + 1, 1, 1)
    elif periode == "libre" and start and end:
        debut = start
        fin = end
    else:  # tout
        debut = date(2000, 1, 1)
        fin = today + timedelta(days=1)

    return datetime.combine(debut, datetime.min.time()), datetime.combine(fin, datetime.min.time())


def _sales_in(debut, fin):
    return (
        Sale.query.filter(
            Sale.created_at >= debut,
            Sale.created_at < fin,
            Sale.status == SaleStatus.VALIDEE,
        )
        .all()
    )


def ventes_summary(debut, fin):
    sales = _sales_in(debut, fin)
    totals = {}
    for sale in sales:
        bucket = totals.setdefault(
            sale.currency,
            {"ca": Decimal("0"), "cout": Decimal("0"), "marge": Decimal("0"), "count": 0},
        )
        bucket["ca"] += dec(sale.montant_total)
        bucket["cout"] += dec(sale.total_cost)
        bucket["marge"] += dec(sale.marge)
        bucket["count"] += 1
    return totals


def charges_summary(debut, fin):
    expenses = (
        Expense.query.filter(
            Expense.expense_date >= debut,
            Expense.expense_date < fin,
            Expense.status == ExpenseStatus.VALIDEE,
        )
        .all()
    )
    totals = {}
    for exp in expenses:
        totals[exp.currency] = totals.get(exp.currency, Decimal("0")) + dec(exp.amount)
    return totals, expenses


def tresorerie_summary(debut, fin):
    """Encaissements / decaissements de caisse par nature et devise."""
    movements = (
        CashMovement.query.filter(
            CashMovement.created_at >= debut,
            CashMovement.created_at < fin,
        )
        .all()
    )
    par_nature = {}
    par_devise = {}
    for m in movements:
        par_nature.setdefault(m.kind, {}).setdefault(m.currency, Decimal("0"))
        par_nature[m.kind][m.currency] += dec(m.amount)
        par_devise[m.currency] = par_devise.get(m.currency, Decimal("0")) + dec(m.amount)
    return par_nature, par_devise


def top_produits(debut, fin, limit=10):
    sales = _sales_in(debut, fin)
    produits = {}
    for sale in sales:
        for line in sale.lines:
            key = line.product_id
            bucket = produits.setdefault(
                key,
                {
                    "product": line.product,
                    "currency": line.currency,
                    "qte": Decimal("0"),
                    "ca": Decimal("0"),
                    "marge": Decimal("0"),
                },
            )
            bucket["qte"] += dec(line.qty_base)
            bucket["ca"] += dec(line.line_total)
            bucket["marge"] += dec(line.line_total) - dec(line.cout_unitaire_cmp) * dec(line.qty_base)
    return sorted(produits.values(), key=lambda x: x["ca"], reverse=True)[:limit]


def serie_journaliere(debut, fin, currency="CDF"):
    """CA journalier (ventes CDF par defaut) sur la periode."""
    sales = _sales_in(debut, fin)
    serie = {}
    for sale in sales:
        if sale.currency != currency:
            continue
        day = sale.created_at.date()
        serie[day] = serie.get(day, Decimal("0")) + dec(sale.montant_total)
    return [(d, serie[d]) for d in sorted(serie)]


def result_summary(debut, fin):
    """Resultat estime = marge brute - charges validees, par devise."""
    ventes = ventes_summary(debut, fin)
    charges, _ = charges_summary(debut, fin)
    devises = set(ventes) | set(charges)
    resultat = {}
    for cur in devises:
        marge = dec(ventes.get(cur, {}).get("marge"))
        charge = dec(charges.get(cur))
        resultat[cur] = {"marge": marge, "charges": charge, "resultat": marge - charge}
    return resultat


def creances_summary():
    credits = Credit.query.filter(Credit.status != CreditStatus.SOLDE).all()
    par_devise = {}
    for c in credits:
        par_devise.setdefault(c.currency, {"client": Decimal("0"), "fournisseur": Decimal("0")})
        if c.is_client:
            par_devise[c.currency]["client"] += dec(c.amount_remaining)
        else:
            par_devise[c.currency]["fournisseur"] += dec(c.amount_remaining)
    return par_devise


def periode_label(periode):
    return PERIODE_LABELS.get(periode, periode)
