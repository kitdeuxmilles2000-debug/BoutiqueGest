"""Rapports : tableau de bord d'analyse, export CSV (Excel) et impression PDF."""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import reports as reports_service
from app.services import settings as settings_service
from app.services.reports import PERIODE_LABELS

reports_bp = Blueprint("reports", __name__, url_prefix="/rapports")


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _build_context():
    periode = request.args.get("periode", "jour")
    debut, fin = reports_service.period_bounds(periode)

    ventes = reports_service.ventes_summary(debut, fin)
    rate = settings_service.latest_rate()
    sales_currency_summary = reports_service.sales_currency_summary(
        debut, fin, rate.rate if rate else None
    )
    achats = reports_service.achats_summary(debut, fin)
    charges, expenses = reports_service.charges_summary(debut, fin)
    par_nature, par_devise = reports_service.tresorerie_summary(debut, fin)
    resultat = reports_service.result_summary(debut, fin)
    top = reports_service.top_produits(debut, fin)
    serie = reports_service.serie_journaliere(debut, fin, "CDF")
    creances = reports_service.creances_summary()

    return {
        "periode": periode,
        "periode_labels": PERIODE_LABELS,
        "debut": debut,
        "fin": fin,
        "ventes": ventes,
        "sales_currency_summary": sales_currency_summary,
        "rate": rate,
        "achats": achats,
        "charges": charges,
        "expenses": expenses,
        "tresorerie_nature": par_nature,
        "tresorerie_devise": par_devise,
        "resultat": resultat,
        "top": top,
        "serie": serie,
        "creances": creances,
    }


@reports_bp.route("/")
@login_required
@permission_required(P.REPORTS_VIEW)
def index():
    return render_template("reports/index.html", **ctx_keys(_build_context()))


def ctx_keys(ctx):
    from app.models.sales import CASH_MOVEMENT_LABELS, PaymentMethod

    ctx["movement_labels"] = CASH_MOVEMENT_LABELS
    ctx["methods"] = PaymentMethod
    return ctx


@reports_bp.route("/export.csv")
@login_required
@permission_required(P.REPORTS_EXPORT)
def export_csv():
    ctx = _build_context()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["BoutiqueGest - Rapport"])
    writer.writerow(["Periode", ctx["periode_labels"].get(ctx["periode"], ctx["periode"])])
    writer.writerow(["Du", ctx["debut"].strftime("%d/%m/%Y"), "Au", ctx["fin"].strftime("%d/%m/%Y")])
    writer.writerow([])

    writer.writerow(["VENTES PAR DEVISE"])
    writer.writerow(["Devise", "Nombre", "CA", "Cout marchandises", "Marge brute", "Marge brute %"])
    for cur, v in ctx["ventes"].items():
        writer.writerow([
            cur, v["count"], str(v["ca"]), str(v["cout"]), str(v["marge"]),
            str(v["taux_marge"]) if v["taux_marge"] is not None else "",
        ])
    writer.writerow([])

    writer.writerow(["CHIFFRE D'AFFAIRES CONVERTI AU TAUX COURANT"])
    writer.writerow([
        "Taux courant",
        f"1 USD = {ctx['rate'].rate} CDF" if ctx["rate"] else "Non renseigne",
    ])
    writer.writerow(["Devise cible", "CA"])
    for cur, amount in ctx["sales_currency_summary"]["totals"].items():
        writer.writerow([cur, str(amount)])
    if not ctx["sales_currency_summary"]["totals"]:
        reason = (
            "Aucune vente CDF/USD a convertir"
            if ctx["rate"]
            else "Aucun taux de change renseigne"
        )
        writer.writerow(["Conversion indisponible", reason])
    writer.writerow([])

    writer.writerow(["CHIFFRE D'AFFAIRES JOURNALIER CDF/USD"])
    writer.writerow([
        "Mode",
        "Conversion au taux courant" if ctx["rate"] else "Montants natifs; aucune conversion",
    ])
    writer.writerow(["Date", "CDF", "USD"])
    for row in ctx["sales_currency_summary"]["daily"]:
        writer.writerow([row["date"].strftime("%d/%m/%Y"), str(row["CDF"]), str(row["USD"])])
    writer.writerow([])

    writer.writerow(["ACHATS RECUS"])
    writer.writerow(["Devise", "Nombre", "Total des achats"])
    for cur, achat in ctx["achats"].items():
        writer.writerow([cur, achat["count"], str(achat["total"])])
    writer.writerow([])

    writer.writerow(["CHARGES (depenses validees)"])
    writer.writerow(["Devise", "Total charges"])
    for cur, total in ctx["charges"].items():
        writer.writerow([cur, str(total)])
    writer.writerow([])

    writer.writerow(["RESULTAT ESTIME"])
    writer.writerow(["Devise", "Marge brute", "Charges", "Resultat"])
    for cur, r in ctx["resultat"].items():
        writer.writerow([cur, str(r["marge"]), str(r["charges"]), str(r["resultat"])])
    writer.writerow([])

    writer.writerow(["TRESORERIE (mouvements de caisse)"])
    writer.writerow(["Nature", "Devise", "Montant"])
    for kind, par_dev in ctx["tresorerie_nature"].items():
        for cur, amount in par_dev.items():
            writer.writerow([kind, cur, str(amount)])
    writer.writerow([])

    writer.writerow(["TOP PRODUITS"])
    writer.writerow(["Produit", "Quantite (base)", "CA net", "Marge brute", "Marge brute %", "Devise"])
    for row in ctx["top"]:
        writer.writerow([
            row["product"].name if row["product"] else "?",
            str(row["qte"]), str(row["ca"]), str(row["marge"]),
            str(row["taux_marge"]) if row["taux_marge"] is not None else "",
            row["currency"],
        ])
    writer.writerow([])

    writer.writerow(["CREANCES ET DETTES EN COURS"])
    writer.writerow(["Devise", "Creances clients", "Dettes fournisseurs"])
    for cur, v in ctx["creances"].items():
        writer.writerow([cur, str(v["client"]), str(v["fournisseur"])])

    data = output.getvalue()
    filename = f"rapport_{ctx['periode']}_{ctx['debut']:%Y%m%d}.csv"
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
