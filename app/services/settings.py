"""Services de parametrage : taux de change manuel et file d'e-mails.

- **Taux de change** (decision CDC #9) : saisi manuellement, historise, jamais
  applique automatiquement aux montants.
- **E-mails** (decision CDC #11) : le rapport est mis en file puis envoye via le
  serveur SMTP configure **dans l'interface** (Administration > E-mails). Sans
  SMTP, il reste **en attente** et consultable depuis l'administration.
"""
import smtplib
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from flask import current_app, render_template

from app.extensions import db
from app.models.base import utcnow
from app.models.settings import (
    ExchangeRate,
    OutboxMessage,
    OutboxStatus,
)
from app.models.user import get_setting, set_setting
from app.security.audit import log_action


# ------------------------------------------------------------ Taux de change
def latest_rate(base="USD", quote="CDF"):
    """Dernier taux connu pour la paire (ordonne par date d'effet puis creation)."""
    return (
        ExchangeRate.query.filter_by(base_currency=base, quote_currency=quote)
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.created_at.desc())
        .first()
    )


def rate_history(base="USD", quote="CDF", limit=50):
    return (
        ExchangeRate.query.filter_by(base_currency=base, quote_currency=quote)
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.created_at.desc())
        .limit(limit)
        .all()
    )


def set_rate(*, rate, effective_date=None, source=None, notes=None, user_id=None, commit=True):
    """Enregistre un nouveau taux (jamais en ecrasement : nouvel enregistrement)."""
    rate = Decimal(str(rate))
    if rate <= 0:
        raise ValueError("Le taux doit etre strictement positif.")
    entry = ExchangeRate(
        base_currency="USD",
        quote_currency="CDF",
        rate=rate,
        effective_date=effective_date or date.today(),
        source=source,
        notes=notes,
        created_by_id=user_id,
    )
    db.session.add(entry)
    log_action(
        action="exchange_rate.set",
        entity="ExchangeRate",
        entity_uuid=entry.uuid,
        after={"rate": str(rate), "effective_date": str(entry.effective_date)},
        reason=source,
    )
    if commit:
        db.session.commit()
    return entry


def convert(amount, rate=None):
    """Conversion explicite USD -> CDF (jamais automatique). Retourne Decimal arrondi."""
    if rate is None:
        latest = latest_rate()
        if latest is None:
            raise ValueError("Aucun taux de change enregistre.")
        rate = latest.rate
    return (Decimal(str(amount)) * Decimal(str(rate))).quantize(Decimal("0.01"))


# ------------------------------------------------------------------- E-mails
SMTP_KEYS = {
    "host": "smtp_host",
    "port": "smtp_port",
    "security": "smtp_security",
    "user": "smtp_user",
    "password": "smtp_password",
    "sender": "smtp_sender",
}
REPORT_TO_SETTING = "report_email_to"
REPORT_AUTO_SEND_SETTING = "report_auto_send"
SECURITY_LABELS = {
    "starttls": "STARTTLS (port 587, recommande)",
    "ssl": "SSL / TLS direct (port 465)",
    "none": "Aucun chiffrement (reseau local uniquement)",
}


def smtp_config():
    """Configuration SMTP effective : interface (base) puis variables d'environnement."""
    def from_setting(key, config_key, default=None):
        value = get_setting(SMTP_KEYS[key])
        if value is None or value == "":
            value = current_app.config.get(config_key)
        return value if value not in (None, "") else default

    host = (from_setting("host", "SMTP_HOST", "") or "").strip()
    raw_port = from_setting("port", "SMTP_PORT", 587)
    try:
        port = int(str(raw_port).strip())
    except (TypeError, ValueError):
        port = 587
    security = get_setting(SMTP_KEYS["security"])
    if security not in SECURITY_LABELS:
        security = "starttls" if current_app.config.get("SMTP_USE_TLS", True) else "none"
    user = from_setting("user", "SMTP_USER")
    password = from_setting("password", "SMTP_PASSWORD")
    sender = from_setting("sender", "SMTP_SENDER") or user or "no-reply@boutiquegest.local"
    return {
        "host": host,
        "port": port,
        "security": security,
        "user": user,
        "password": password,
        "sender": sender,
    }


def smtp_configured():
    return bool(smtp_config()["host"])


def save_smtp_config(
    *,
    host,
    port,
    security,
    user=None,
    password=None,
    sender=None,
    report_to=None,
    auto_send=False,
):
    """Enregistre la configuration SMTP saisie dans l'interface."""
    host = (host or "").strip()
    if "://" in host or "/" in host or " " in host:
        raise ValueError(
            "Serveur SMTP invalide : indiquez seulement le nom d'hote (ex. smtp.gmail.com)."
        )
    try:
        port_value = int(str(port or "587").strip())
    except (TypeError, ValueError):
        raise ValueError("Port SMTP invalide : utilisez un nombre entre 1 et 65535.")
    if not (1 <= port_value <= 65535):
        raise ValueError("Port SMTP invalide : utilisez un nombre entre 1 et 65535.")
    if security not in SECURITY_LABELS:
        security = "starttls"
    sender = (sender or "").strip()
    if sender and "@" not in sender:
        raise ValueError("Adresse d'expediteur invalide.")

    set_setting(SMTP_KEYS["host"], host)
    set_setting(SMTP_KEYS["port"], str(port_value))
    set_setting(SMTP_KEYS["security"], security)
    set_setting(SMTP_KEYS["user"], (user or "").strip())
    set_setting(SMTP_KEYS["sender"], sender)
    set_setting(REPORT_AUTO_SEND_SETTING, "1" if auto_send else "0")
    if password:
        # Un champ laisse vide conserve le mot de passe deja enregistre.
        set_setting(SMTP_KEYS["password"], password)
    if report_to is not None:
        set_setting(REPORT_TO_SETTING, (report_to or "").strip())
    return smtp_config()


@contextmanager
def _open_smtp(config):
    """Ouvre une connexion SMTP (SSL direct ou STARTTLS) et s'authentifie si besoin."""
    host = config["host"]
    if not host:
        raise RuntimeError(
            "SMTP non configure : renseignez le serveur dans Administration > E-mails."
        )
    if config["security"] == "ssl":
        server = smtplib.SMTP_SSL(host, config["port"], timeout=20)
    else:
        server = smtplib.SMTP(host, config["port"], timeout=20)
    try:
        if config["security"] == "starttls":
            server.starttls()
        if config["user"] and config["password"]:
            server.login(config["user"], config["password"])
        yield server
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - fermeture best effort
            pass


def verify_connection():
    """Teste la connexion et l'authentification. Retourne (ok, message)."""
    config = smtp_config()
    if not config["host"]:
        return False, "Renseignez d'abord le serveur SMTP, puis testez la connexion."
    try:
        with _open_smtp(config):
            pass
    except Exception as exc:  # noqa: BLE001 - on remonte le message reel
        return False, f"Echec de connexion a {config['host']}:{config['port']} : {exc}"
    return True, f"Connexion reussie a {config['host']}:{config['port']}."


def _build_message(to_address, subject, text_body, html_body=None, config=None):
    config = config or smtp_config()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["sender"]
    message["To"] = to_address
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="boutiquegest.local")
    message.set_content(text_body or "")
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


def _send_smtp(msg):
    """Tente l'envoi reel du message (HTML + version texte). Leve une exception si echec."""
    config = smtp_config()
    message = _build_message(
        msg.to_address, msg.subject, msg.body, getattr(msg, "body_html", None), config
    )
    with _open_smtp(config) as server:
        server.send_message(message)


def queue_email(
    *, to_address, subject, body, body_html=None, kind="rapport", user_id=None, commit=True
):
    """Met un message en file d'attente (statut en_attente par defaut)."""
    msg = OutboxMessage(
        to_address=to_address,
        subject=subject,
        body=body,
        body_html=body_html,
        kind=kind,
        status=OutboxStatus.EN_ATTENTE,
        created_by_id=user_id,
    )
    db.session.add(msg)
    if commit:
        db.session.commit()
    return msg


def send_pending(limit=25):
    """Tente d'envoyer les messages en attente. Retourne (envoyes, erreurs)."""
    pending = (
        OutboxMessage.query.filter_by(status=OutboxStatus.EN_ATTENTE)
        .order_by(OutboxMessage.created_at)
        .limit(limit)
        .all()
    )
    sent = errors = 0
    for msg in pending:
        msg.attempts += 1
        try:
            _send_smtp(msg)
            msg.status = OutboxStatus.ENVOYE
            msg.sent_at = utcnow()
            msg.last_error = None
            sent += 1
        except Exception as exc:  # noqa: BLE001 - on trace l'erreur reelle
            msg.status = OutboxStatus.ERREUR
            msg.last_error = str(exc)[:255]
            errors += 1
    db.session.commit()
    return sent, errors


def resend(message_id):
    msg = db.session.get(OutboxMessage, message_id)
    if msg is None:
        raise ValueError("Message introuvable.")
    msg.status = OutboxStatus.EN_ATTENTE
    msg.last_error = None
    db.session.commit()
    return msg


# --------------------------------------------------- Rapport (e-mail)
def _report_bounds(periode="jour", report_date=None):
    from app.services import reports as reports_service

    if report_date is not None:
        debut = datetime.combine(report_date, time.min)
        return debut, debut + timedelta(days=1)
    return reports_service.period_bounds(periode)


def build_report_context(periode="jour", report_date=None):
    """Rassemble toutes les donnees du rapport (par devise, sans conversion)."""
    from app.services import reports as reports_service

    debut, fin = _report_bounds(periode, report_date)
    ventes = reports_service.ventes_summary(debut, fin)
    charges, expenses = reports_service.charges_summary(debut, fin)
    par_nature, par_devise = reports_service.tresorerie_summary(debut, fin)
    resultat = reports_service.result_summary(debut, fin)
    top = reports_service.top_produits(debut, fin, limit=8)
    creances = reports_service.creances_summary()

    devises = sorted(set(ventes) | set(charges) | set(resultat) | set(par_devise))
    highlight_currency = "CDF" if "CDF" in devises else (devises[0] if devises else "CDF")
    highlight = resultat.get(
        highlight_currency, {"marge": Decimal("0"), "charges": Decimal("0"), "resultat": Decimal("0")}
    )
    highlight_ventes = ventes.get(
        highlight_currency, {"ca": Decimal("0"), "cout": Decimal("0"), "marge": Decimal("0"), "count": 0}
    )

    from app.models.sales import CASH_MOVEMENT_LABELS

    recent_expenses = (
        sorted(expenses, key=lambda e: e.expense_date or datetime.min, reverse=True)[:8]
    )
    return {
        "periode": periode,
        "debut": debut.date(),
        "fin": (fin - timedelta(days=1)).date(),
        "periode_label": reports_service.PERIODE_LABELS.get(periode, periode),
        "generated_at": utcnow(),
        "today": date.today(),
        "ventes": ventes,
        "charges": charges,
        "expenses": recent_expenses,
        "tresorerie_nature": par_nature,
        "tresorerie_devise": par_devise,
        "resultat": resultat,
        "top": top,
        "creances": creances,
        "movement_labels": CASH_MOVEMENT_LABELS,
        "devises": devises,
        "highlight_currency": highlight_currency,
        "highlight": highlight,
        "highlight_ventes": highlight_ventes,
        "currency": highlight_currency,
    }


def _fmt_amount(value, currency=None):
    try:
        text = f"{Decimal(value or 0):,.2f}".replace(",", " ").replace(".", ",")
    except Exception:  # noqa: BLE001
        text = str(value)
    return f"{text} {currency}" if currency else text


def build_report_text(periode="jour", report_date=None):
    """Version texte (fallback des clients mail). Montants separes par devise."""
    ctx = build_report_context(periode, report_date)
    lines = [
        f"{current_app.config.get('APP_NAME', 'BoutiqueGest')} - Rapport d'activite",
        f"Periode : {ctx['periode_label']} (du {ctx['debut']:%d/%m/%Y} au {ctx['fin']:%d/%m/%Y})",
        f"Genere le : {ctx['generated_at']:%d/%m/%Y %H:%M}",
        "",
        "Synthese (par devise) :",
    ]
    if ctx["resultat"]:
        for devise, row in sorted(ctx["resultat"].items()):
            ventes = ctx["ventes"].get(devise, {})
            lines.append(
                f"  {devise}: CA={_fmt_amount(ventes.get('ca'))} | "
                f"marge={_fmt_amount(row['marge'])} | charges={_fmt_amount(row['charges'])} | "
                f"resultat={_fmt_amount(row['resultat'])}"
            )
    else:
        lines.append("  aucune activite")

    lines += ["", "Ventes (par devise) :"]
    if ctx["ventes"]:
        for devise, data in sorted(ctx["ventes"].items()):
            lines.append(
                f"  {devise}: {data['count']} vente(s), CA={_fmt_amount(data['ca'])}, "
                f"cout={_fmt_amount(data['cout'])}, marge={_fmt_amount(data['marge'])}"
            )
    else:
        lines.append("  aucune vente")

    lines += ["", "Charges validees (par devise) :"]
    if ctx["charges"]:
        for devise, montant in sorted(ctx["charges"].items()):
            lines.append(f"  {devise}: {_fmt_amount(montant)}")
    else:
        lines.append("  aucune charge")

    lines += ["", "Tresorerie nette (par devise) :"]
    if ctx["tresorerie_devise"]:
        for devise, montant in sorted(ctx["tresorerie_devise"].items()):
            lines.append(f"  {devise}: {_fmt_amount(montant)}")
    else:
        lines.append("  aucun mouvement")

    lines += ["", "Top produits :"]
    if ctx["top"]:
        for index, row in enumerate(ctx["top"], start=1):
            nom = row["product"].name if row["product"] else "?"
            lines.append(
                f"  {index}. {nom} - {row['qte']} unite(s) de base, "
                f"CA={_fmt_amount(row['ca'])}, marge={_fmt_amount(row['marge'])}"
            )
    else:
        lines.append("  aucune vente sur la periode")

    lines += ["", "Creances et dettes en cours :"]
    if ctx["creances"]:
        for devise, row in sorted(ctx["creances"].items()):
            lines.append(
                f"  {devise}: creances clients={_fmt_amount(row['client'])}, "
                f"dettes fournisseurs={_fmt_amount(row['fournisseur'])}"
            )
    else:
        lines.append("  aucun encours")

    lines += ["", "(Montants non convertis : CDF et USD restent separes.)"]
    return "\n".join(lines)


def build_report_html(periode="jour", report_date=None):
    """Version HTML professionnelle du rapport (design email)."""
    ctx = build_report_context(periode, report_date)
    ctx = {k: v for k, v in ctx.items() if not k.startswith("_")}
    ctx["app_name"] = current_app.config.get("APP_NAME", "BoutiqueGest")
    return render_template("emails/rapport.html", **ctx)


def build_daily_report_text(report_date=None):
    """Compatibilite : texte du rapport journalier."""
    return build_report_text("jour", report_date)


def queue_daily_report(to_address, user_id=None, commit=True, periode="jour"):
    label = "Rapport journalier" if periode == "jour" else "Rapport d'activite"
    periode_label = build_report_context(periode)["periode_label"]
    return queue_email(
        to_address=to_address,
        subject=f"{label} {current_app.config.get('APP_NAME', 'BoutiqueGest')} - "
        f"{periode_label} ({date.today():%d/%m/%Y})",
        body=build_report_text(periode),
        body_html=build_report_html(periode),
        kind="rapport",
        user_id=user_id,
        commit=commit,
    )


def send_test_email(to_address):
    """Envoie un e-mail de test avec le design du rapport. Retourne (ok, message)."""
    if not to_address:
        return False, "Renseignez une adresse destinataire pour le test."
    subject = f"{current_app.config.get('APP_NAME', 'BoutiqueGest')} - E-mail de test"
    text = (
        "Ceci est un e-mail de test envoye par BoutiqueGest.\n\n"
        "Si vous lisez ce message, la configuration SMTP est correcte :\n"
        "les rapports d'activite pourront etre envoyes."
    )
    html = render_template(
        "emails/test.html",
        subject=subject,
        now_date=date.today(),
        app_name=current_app.config.get("APP_NAME", "BoutiqueGest"),
    )
    message = _build_message(to_address, subject, text, html)
    try:
        with _open_smtp(smtp_config()) as server:
            server.send_message(message)
    except Exception as exc:  # noqa: BLE001 - message d'erreur reel a afficher
        return False, f"Echec de l'envoi : {exc}"
    return True, f"E-mail de test envoye a {to_address}."
