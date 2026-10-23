"""Routes principales : accueil et tableau de bord."""
from decimal import Decimal

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.models.base import utcnow
from app.models.sales import CashSession, CashSessionStatus, Sale, SaleStatus
from app.security.permissions import P
from app.services import cash as cash_service
from app.services import finance as finance_service
from app.services import stock as stock_service
from app.services.stock import dec

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    sales_query = Sale.query.filter(Sale.created_at >= start, Sale.status == SaleStatus.VALIDEE)
    if not current_user.has_permission(P.SALES_VIEW_ALL):
        sales_query = sales_query.filter_by(vendeur_id=current_user.id)
    today_sales = sales_query.all()

    ventes_total = sum((s.montant_total for s in today_sales), start=Decimal("0"))
    ventes_marge = sum((s.marge for s in today_sales), start=Decimal("0"))

    ventes_par_devise = {}
    for s in today_sales:
        dev = s.currency or "CDF"
        ventes_par_devise.setdefault(dev, {"montant": Decimal("0"), "marge": Decimal("0"), "count": 0})
        ventes_par_devise[dev]["montant"] += dec(s.montant_total)
        ventes_par_devise[dev]["marge"] += dec(s.marge)
        ventes_par_devise[dev]["count"] += 1

    caisse_open = cash_service.find_open_session(vendeur_id=current_user.id)
    caisse_label = None
    if caisse_open is not None:
        caisse_label = f"{caisse_open.register.name} — {caisse_open.currency}"
    elif current_user.has_permission(P.CASH_VIEW_ALL):
        count = CashSession.query.filter_by(status=CashSessionStatus.OUVERTE).count()
        if count:
            caisse_label = f"{count} caisse(s) ouverte(s)"

    alerts = stock_service.stock_alerts()

    en_retard, proches, echeances_echues = [], [], []
    if current_user.has_permission(P.CREDITS_VIEW):
        en_retard, proches, echeances_echues = finance_service.credit_alerts()

    return render_template(
        "dashboard.html",
        ventes_total=ventes_total,
        ventes_count=len(today_sales),
        ventes_marge=ventes_marge,
        ventes_par_devise=ventes_par_devise,
        caisse_ouverte=caisse_label is not None,
        caisse_label=caisse_label,
        ruptures=len(alerts["out_of_stock"]),
        stock_bas=len(alerts["low_stock"]),
        credits_en_retard=en_retard,
        credits_proches=proches,
        echeances_echues=echeances_echues,
    )
