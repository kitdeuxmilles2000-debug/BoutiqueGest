"""Reinitialisation de la base : effacement de toutes les operations.

Les referentiels sont conserves par defaut : utilisateurs, roles, permissions,
unites, categories, caisses, taux de change, parametres. Le catalogue (produits)
et les partenaires (clients / fournisseurs) peuvent etre effaces en option.

Une sauvegarde est creee avant tout effacement par l'appelant (route admin).
"""
from app.extensions import db
from app.models.audit import AuditLog
from app.models.catalog import PriceHistory, Product, ProductUnit
from app.models.finance import Credit, Expense, Installment, Settlement
from app.models.notifications import Notification
from app.models.partners import Customer, Supplier
from app.models.purchases import Purchase, PurchaseLine
from app.models.sales import (
    CashMovement,
    CashSession,
    Payment,
    Refund,
    Sale,
    SaleLine,
)
from app.models.settings import OutboxMessage
from app.models.stock import (
    Batch,
    InventoryLine,
    InventorySession,
    StockEntryRequest,
    StockMovement,
)
from app.models.sync import SyncEvent

MAGIC_WORD = "clovis est une fleur"


def normalize_magic_word(raw):
    """Normalise la phrase magique : espaces multiples, casse et ponctuation finale."""
    text = " ".join((raw or "").split()).casefold()
    return text.strip(" .!")


def magic_word_ok(raw):
    return normalize_magic_word(raw) == MAGIC_WORD


def collect_counts(*, include_catalog=False, include_partners=False):
    """Compte ce qui sera supprime, pour l'affichage avant confirmation."""
    counts = {
        "Ventes": Sale.query.count(),
        "Lignes de vente": SaleLine.query.count(),
        "Paiements": Payment.query.count(),
        "Remboursements": Refund.query.count(),
        "Credits (clients et fournisseurs)": Credit.query.count(),
        "Echeances de credit": Installment.query.count(),
        "Reglements de credit": Settlement.query.count(),
        "Achats": Purchase.query.count(),
        "Lignes d'achat": PurchaseLine.query.count(),
        "Mouvements de stock": StockMovement.query.count(),
        "Demandes d'entree en stock": StockEntryRequest.query.count(),
        "Lots": Batch.query.count(),
        "Sessions d'inventaire": InventorySession.query.count(),
        "Lignes d'inventaire": InventoryLine.query.count(),
        "Sessions de caisse": CashSession.query.count(),
        "Mouvements de caisse": CashMovement.query.count(),
        "Depenses": Expense.query.count(),
        "Notifications": Notification.query.count(),
        "E-mails en file": OutboxMessage.query.count(),
        "Evenements de synchronisation": SyncEvent.query.count(),
        "Journal d'audit": AuditLog.query.count(),
    }
    if include_partners:
        counts["Clients"] = Customer.query.count()
        counts["Fournisseurs"] = Supplier.query.count()
    if include_catalog:
        counts["Produits"] = Product.query.count()
        counts["Unites de vente des produits"] = ProductUnit.query.count()
        counts["Historique des prix"] = PriceHistory.query.count()
    return counts


def reset_operations(*, include_catalog=False, include_partners=False):
    """Efface toutes les operations. Retourne les compteurs reellement supprimes."""
    counts = collect_counts(
        include_catalog=include_catalog, include_partners=include_partners
    )

    # 1. Credits et leurs enfants (avant les ventes et les partenaires)
    Settlement.query.delete(synchronize_session=False)
    Installment.query.delete(synchronize_session=False)
    Credit.query.delete(synchronize_session=False)

    # 2. Ventes et leurs enfants
    Sale.query.update({"sale_origine_id": None}, synchronize_session=False)
    Payment.query.delete(synchronize_session=False)
    Refund.query.delete(synchronize_session=False)
    SaleLine.query.delete(synchronize_session=False)
    Sale.query.delete(synchronize_session=False)

    # 3. Achats et leurs enfants
    PurchaseLine.query.delete(synchronize_session=False)
    Purchase.query.delete(synchronize_session=False)

    # 4. Stock : les mouvements d'abord (ils referencent les demandes d'entree
    # et les lots), puis les demandes, puis les lots et l'inventaire.
    StockMovement.query.delete(synchronize_session=False)
    StockEntryRequest.query.delete(synchronize_session=False)
    Batch.query.delete(synchronize_session=False)
    InventoryLine.query.delete(synchronize_session=False)
    InventorySession.query.delete(synchronize_session=False)

    # 5. Depenses puis caisse (les depenses referencent une session)
    Expense.query.delete(synchronize_session=False)
    CashMovement.query.delete(synchronize_session=False)
    CashSession.query.delete(synchronize_session=False)

    # 6. Files et journaux
    Notification.query.delete(synchronize_session=False)
    OutboxMessage.query.delete(synchronize_session=False)
    SyncEvent.query.delete(synchronize_session=False)
    AuditLog.query.delete(synchronize_session=False)

    # 7. Partenaires (optionnel) : plus aucun credit / achat / entree lie
    if include_partners:
        Customer.query.delete(synchronize_session=False)
        Supplier.query.delete(synchronize_session=False)

    # 8. Catalogue (optionnel)
    if include_catalog:
        PriceHistory.query.delete(synchronize_session=False)
        ProductUnit.query.delete(synchronize_session=False)
        Product.query.delete(synchronize_session=False)
    else:
        # Les produits restent, mais leur stock repart de zero.
        Product.query.update({"stock_qty": 0}, synchronize_session=False)

    db.session.commit()
    return counts
