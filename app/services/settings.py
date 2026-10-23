"""Services de parametrage : taux de change manuel et file d'e-mails.

- **Taux de change** (decision CDC #9) : saisi manuellement, historise, jamais
  applique automatiquement aux montants.
- **E-mails** (decision CDC #11) : le rapport journalier est mise en file puis
  envoye si un serveur SMTP est configure ; sinon il reste **en attente** et
  consultable depuis l'administration.
"""
import smtplib
from datetime import date
from email.mime.text import MIMEText
from decimal import Decimal

from flask import current_app

from app.extensions import db
from app.models.base import utcnow
from app.models.settings import (
    ExchangeRate,
    OutboxMessage,
    OutboxStatus,
)
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
def queue_email(*, to_address, subject, body, kind="rapport", user_id=None, commit=True):
    """Met un message en file d'attente (statut en_attente par defaut)."""
    msg = OutboxMessage(
        to_address=to_address,
        subject=subject,
        body=body,
        kind=kind,
        status=OutboxStatus.EN_ATTENTE,
        created_by_id=user_id,
    )
    db.session.add(msg)
    if commit:
        db.session.commit()
    return msg


def _send_smtp(msg):
    """Tente l'envoi via le serveur SMTP configure. Leve une exception si echec."""
    host = current_app.config.get("SMTP_HOST")
    if not host:
        raise RuntimeError("SMTP non configure")
    port = int(current_app.config.get("SMTP_PORT", 587) or 587)
    user = current_app.config.get("SMTP_USER")
    password = current_app.config.get("SMTP_PASSWORD")
    sender = current_app.config.get("SMTP_SENDER") or user or "no-reply@boutiquegest.local"
    use_tls = bool(current_app.config.get("SMTP_USE_TLS", True))

    email = MIMEText(msg.body, "plain", "utf-8")
    email["Subject"] = msg.subject
    email["From"] = sender
    email["To"] = msg.to_address

    with smtplib.SMTP(host, port, timeout=10) as server:
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(sender, [msg.to_address], email.as_string())


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


# --------------------------------------------------- Rapport journalier (mail)
def build_daily_report_text(report_date=None):
    """Construit le corps texte du rapport journalier (par devise, sans conversion)."""
    from app.services import reports as reports_service

    debut, fin = reports_service.period_bounds("jour")
    ventes = reports_service.ventes_summary(debut, fin)
    charges, _ = reports_service.charges_summary(debut, fin)
    _, tresorerie = reports_service.tresorerie_summary(debut, fin)

    lines = [f"Rapport journalier - {date.today():%d/%m/%Y}", ""]
    lines.append("Ventes (par devise) :")
    if ventes:
        for devise, data in sorted(ventes.items()):
            lines.append(
                f"  {devise}: CA={data['ca']}  marge={data['marge']}  ({data['count']} vente(s))"
            )
    else:
        lines.append("  aucune vente")
    lines.append("")
    lines.append("Charges validees (par devise) :")
    if charges:
        for devise, montant in sorted(charges.items()):
            lines.append(f"  {devise}: {montant}")
    else:
        lines.append("  aucune charge")
    lines.append("")
    lines.append("Tresorerie nette (par devise) :")
    if tresorerie:
        for devise, montant in sorted(tresorerie.items()):
            lines.append(f"  {devise}: {montant}")
    else:
        lines.append("  aucun mouvement")
    lines.append("")
    lines.append("(Montants non convertis : CDF et USD restent separes.)")
    return "\n".join(lines)


def queue_daily_report(to_address, user_id=None, commit=True):
    return queue_email(
        to_address=to_address,
        subject=f"Rapport journalier BoutiqueGest - {date.today():%d/%m/%Y}",
        body=build_daily_report_text(),
        kind="rapport",
        user_id=user_id,
        commit=commit,
    )
