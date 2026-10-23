"""Rapports : tableau de bord d'analyse, export CSV (Excel) et impression PDF."""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from app.security.decorators import permission_required
from app.security.permissions import P
from app.services import reports as reports_service
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
    writer.writerow(["Devise", "Nombre", "CA", "Cout marchandises", "Marge"])
    for cur, v in ctx["ventes"].items():
        writer.writerow([cur, v["count"], str(v["ca"]), str(v["cout"]), str(v["marge"])])
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
    writer.writerow(["Produit", "Quantite (base)", "CA", "Marge", "Devise"])
    for row in ctx["top"]:
        writer.writerow([
            row["product"].name if row["product"] else "?",
            str(row["qte"]), str(row["ca"]), str(row["marge"]), row["currency"],
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
