"""Services notifications / alertes."""
from datetime import date

from app.extensions import db
from app.models.catalog import Product
from app.models.finance import Credit, CreditStatus, Installment, InstallmentStatus
from app.models.notifications import Notification, NotificationType
from app.services.stock import dec


def create_notification(
    type,
    title,
    message,
    link=None,
    priority=0,
    entity_type=None,
    entity_id=None,
    entity_uuid=None,
    commit=True,
):
    """Crée une notification (alerte / événement). `type` : code NotificationType."""
    n = Notification(
        type=type,
        title=title,
        message=message,
        link=link,
        priority=priority,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_uuid=entity_uuid,
    )
    db.session.add(n)
    if commit:
        db.session.commit()
    return n


def notify_stock_replenished(product, source=None, commit=True):
    """Notification : un produit a été remis à niveau (réception / entrée validée)."""
    qty = dec(product.stock_qty)
    n = create_notification(
        type=NotificationType.STOCK_REPLENISHED,
        title=f"Stock remis à niveau - {product.name}",
        message=(
            f"{product.name} ({product.code}) : {qty} {product.base_unit.code if product.base_unit else ''} "
            f"disponibles. Source : {source or 'réception stock'}."
        ),
        link=f"/produits/{product.id}",
        priority=5,
        entity_type="product",
        entity_id=product.id,
        entity_uuid=product.uuid,
        commit=commit,
    )
    return n


def notify_debt_paid(credit, amount=None, commit=True):
    """Notification : une dette (client / fournisseur) vient d'être soldée."""
    montant = dec(amount) if amount is not None else dec(credit.amount_remaining)
    create_notification(
        type=NotificationType.DEBT_PAID,
        title=f"Dette soldée - {credit.partner_name}",
        message=f"Montant réglé : {montant} {credit.currency}. Solde restant : {dec(credit.amount_remaining)} {credit.currency}.",
        link=f"/credits/{credit.id}",
        priority=3,
        entity_type="credit",
        entity_id=credit.id,
        entity_uuid=credit.uuid,
        commit=commit,
    )


def notify_password_changed(user, commit=True):
    """Notification sécurité : le mot de passe de l'utilisateur a été renforcé / changé."""
    create_notification(
        type=NotificationType.PASSWORD_CHANGED,
        title=f"Sécurité : mot de passe modifié - {user.full_name}",
        message=f"Le mot de passe de {user.full_name} ({user.username}) a été renforcé.",
        link="/admin/users",
        priority=8,
        entity_type="user",
        entity_id=user.id,
        entity_uuid=user.uuid,
        commit=commit,
    )


def sync_alerts(commit=True):
    """Crée / met à jour les alertes (crédits, stocks). Supprime les alertes résolues."""
    today = date.today()
    # Crédits échus / à échéance aujourd'hui
    credits = Credit.query.filter(Credit.amount_remaining > 0).all()
    for c in credits:
        partner = c.partner_name
        cur = c.currency
        # Échéances
        for inst in c.installments:
            if inst.status == InstallmentStatus.PAYEE:
                continue
            if inst.due_date and inst.due_date < today:
                exists = (
                    Notification.query.filter_by(
                        entity_type="installment",
                        entity_id=inst.id,
                        type=NotificationType.CREDIT_ECHU,
                        dismissed=False,
                    ).first()
                )
                if not exists:
                    db.session.add(
                        Notification(
                            type=NotificationType.CREDIT_ECHU,
                            title=f"Échéance échue - {partner}",
                            message=f"Échéance du {inst.due_date} : {inst.amount_due} {cur}. Solde restant crédit {c.amount_remaining} {cur}.",
                            link=f"/credits/{c.id}",
                            priority=10,
                            entity_type="installment",
                            entity_id=inst.id,
                        )
                    )
            elif inst.due_date and inst.due_date == today:
                exists = (
                    Notification.query.filter_by(
                        entity_type="installment",
                        entity_id=inst.id,
                        type=NotificationType.CREDIT_JOUR,
                        dismissed=False,
                    ).first()
                )
                if not exists:
                    db.session.add(
                        Notification(
                            type=NotificationType.CREDIT_JOUR,
                            title=f"Échéance aujourd'hui - {partner}",
                            message=f"Échéance du {inst.due_date} : {inst.amount_due} {cur}. À régler.",
                            link=f"/credits/{c.id}",
                            priority=5,
                            entity_type="installment",
                            entity_id=inst.id,
                        )
                    )
        if c.due_date and c.due_date < today and c.status != CreditStatus.SOLDE:
            exists = (
                Notification.query.filter_by(
                    entity_type="credit",
                    entity_id=c.id,
                    type=NotificationType.CREDIT_ECHU,
                    dismissed=False,
                ).first()
            )
            if not exists:
                db.session.add(
                    Notification(
                        type=NotificationType.CREDIT_ECHU,
                        title=f"Crédit échue - {partner}",
                        message=f"Date d'échéance {c.due_date} dépassée. Restant : {c.amount_remaining} {cur}.",
                        link=f"/credits/{c.id}",
                        priority=10,
                        entity_type="credit",
                        entity_id=c.id,
                    )
                )

    # Stocks bas / rupture
    for p in Product.query.filter_by(active=True).all():
        qty = dec(p.stock_qty)
        seuil = dec(p.seuil_alerte)
        if qty <= 0:
            exists = (
                Notification.query.filter_by(
                    entity_type="product",
                    entity_id=p.id,
                    type=NotificationType.STOCK_RUPTURE,
                    dismissed=False,
                ).first()
            )
            if not exists:
                db.session.add(
                    Notification(
                        type=NotificationType.STOCK_RUPTURE,
                        title=f"Rupture de stock - {p.name}",
                        message=f"{p.name} ({p.code}) en rupture. À approvisionner.",
                        link=f"/produits/{p.id}",
                        priority=8,
                        entity_type="product",
                        entity_id=p.id,
                    )
                )
        elif seuil > 0 and qty <= seuil:
            exists = (
                Notification.query.filter_by(
                    entity_type="product",
                    entity_id=p.id,
                    type=NotificationType.STOCK_BAS,
                    dismissed=False,
                ).first()
            )
            if not exists:
                db.session.add(
                    Notification(
                        type=NotificationType.STOCK_BAS,
                        title=f"Stock bas - {p.name}",
                        message=f"{p.name} ({p.code}) : {qty} {p.base_unit.code if p.base_unit else ''} (seuil {seuil}).",
                        link=f"/produits/{p.id}",
                        priority=6,
                        entity_type="product",
                        entity_id=p.id,
                    )
                )
        else:
            # Supprimer notifications si approvisionné / plus en alerte
            Notification.query.filter_by(
                entity_type="product",
                entity_id=p.id,
                type=NotificationType.STOCK_RUPTURE,
                dismissed=False,
            ).delete()
            if not (seuil > 0 and qty <= seuil):
                Notification.query.filter_by(
                    entity_type="product",
                    entity_id=p.id,
                    type=NotificationType.STOCK_BAS,
                    dismissed=False,
                ).delete()

    # Supprimer notifications crédits si soldés
    for c in Credit.query.filter(Credit.amount_remaining <= 0).all():
        Notification.query.filter_by(entity_type="credit", entity_id=c.id, dismissed=False).delete()
        for inst in c.installments:
            Notification.query.filter_by(entity_type="installment", entity_id=inst.id, dismissed=False).delete()

    if commit:
        db.session.commit()
