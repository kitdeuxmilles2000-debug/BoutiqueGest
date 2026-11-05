"""Codes de permission et roles par defaut.

Chaque permission est verifiee cote serveur (voir app.security.decorators).
"""
from __future__ import annotations


class P:
    """Constantes de permission (code = 'domaine.action')."""

    # Administration / securite
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_VIEW = "audit.view"
    BACKUP_MANAGE = "backup.manage"
    SYNC_MANAGE = "sync.manage"

    # Catalogue / stock
    PRODUCTS_VIEW = "products.view"
    PRODUCTS_MANAGE = "products.manage"
    STOCK_VIEW = "stock.view"
    STOCK_MANAGE = "stock.manage"
    INVENTORY_MANAGE = "inventory.manage"
    INVENTORY_VALIDATE = "inventory.validate"
    LOSS_MANAGE = "loss.manage"

    # Ventes
    SALES_CREATE = "sales.create"
    SALES_VIEW = "sales.view"
    SALES_VIEW_ALL = "sales.view_all"
    SALES_CANCEL = "sales.cancel"
    SALES_DISCOUNT = "sales.discount"

    # Achats / receptions
    PURCHASE_VIEW = "purchase.view"
    PURCHASE_PREPARE = "purchase.prepare"
    PURCHASE_VALIDATE = "purchase.validate"

    # Caisse
    CASH_OPEN = "cash.open"
    CASH_CLOSE = "cash.close"
    CASH_VIEW_ALL = "cash.view_all"
    CASH_VALIDATE = "cash.validate"

    # Depenses
    EXPENSES_VIEW = "expenses.view"
    EXPENSES_CREATE = "expenses.create"
    EXPENSES_VALIDATE = "expenses.validate"

    # Credits / dettes
    CREDITS_VIEW = "credits.view"
    CREDITS_MANAGE = "credits.manage"

    # Partenaires (clients / fournisseurs)
    PARTNERS_VIEW = "partners.view"
    PARTNERS_MANAGE = "partners.manage"

    # Rapports
    REPORTS_VIEW = "reports.view"
    REPORTS_EXPORT = "reports.export"


# Libelles lisibles : code -> (label, categorie)
PERMISSION_LABELS = {
    P.USERS_VIEW: ("Consulter les utilisateurs", "Administration"),
    P.USERS_MANAGE: ("Gerer les utilisateurs", "Administration"),
    P.ROLES_MANAGE: ("Gerer les roles et permissions", "Administration"),
    P.SETTINGS_MANAGE: ("Gerer les parametres", "Administration"),
    P.AUDIT_VIEW: ("Consulter le journal d'audit", "Administration"),
    P.BACKUP_MANAGE: ("Gerer les sauvegardes", "Administration"),
    P.SYNC_MANAGE: ("Gerer la synchronisation", "Administration"),
    P.PRODUCTS_VIEW: ("Consulter les produits", "Catalogue"),
    P.PRODUCTS_MANAGE: ("Gerer les produits et prix", "Catalogue"),
    P.STOCK_VIEW: ("Consulter le stock", "Stock"),
    P.STOCK_MANAGE: ("Gerer les mouvements de stock", "Stock"),
    P.INVENTORY_MANAGE: ("Faire les inventaires", "Stock"),
    P.INVENTORY_VALIDATE: ("Valider un inventaire", "Stock"),
    P.LOSS_MANAGE: ("Declarer pertes et peremptions", "Stock"),
    P.SALES_CREATE: ("Enregistrer une vente", "Ventes"),
    P.SALES_VIEW: ("Consulter ses ventes", "Ventes"),
    P.SALES_VIEW_ALL: ("Consulter toutes les ventes", "Ventes"),
    P.SALES_CANCEL: ("Annuler / rembourser une vente", "Ventes"),
    P.SALES_DISCOUNT: ("Accorder une remise", "Ventes"),
    P.PURCHASE_VIEW: ("Consulter les achats", "Achats"),
    P.PURCHASE_PREPARE: ("Preparer une reception", "Achats"),
    P.PURCHASE_VALIDATE: ("Valider une reception", "Achats"),
    P.CASH_OPEN: ("Ouvrir une caisse", "Caisse"),
    P.CASH_CLOSE: ("Soumettre une cloture", "Caisse"),
    P.CASH_VIEW_ALL: ("Consulter toutes les caisses", "Caisse"),
    P.CASH_VALIDATE: ("Valider une cloture", "Caisse"),
    P.EXPENSES_VIEW: ("Consulter les depenses", "Depenses"),
    P.EXPENSES_CREATE: ("Saisir une depense", "Depenses"),
    P.EXPENSES_VALIDATE: ("Valider une depense", "Depenses"),
    P.CREDITS_VIEW: ("Consulter les credits et dettes", "Credits"),
    P.CREDITS_MANAGE: ("Gerer les credits et reglements", "Credits"),
    P.PARTNERS_VIEW: ("Consulter clients et fournisseurs", "Partenaires"),
    P.PARTNERS_MANAGE: ("Gerer clients et fournisseurs", "Partenaires"),
    P.REPORTS_VIEW: ("Consulter les rapports", "Rapports"),
    P.REPORTS_EXPORT: ("Exporter les rapports", "Rapports"),
}


# Roles par defaut : nom technique -> (label, description, super_admin, permissions)
DEFAULT_ROLES = {
    "proprietaire": (
        "Proprietaire",
        "Acces complet a toutes les fonctions et validations",
        True,
        set(PERMISSION_LABELS.keys()),
    ),
    "vendeur": (
        "Vendeur",
        "Enregistre les ventes et consulte ses propres ventes",
        False,
        {
            P.PRODUCTS_VIEW, P.STOCK_VIEW, P.SALES_CREATE, P.SALES_VIEW,
            P.CASH_OPEN, P.CASH_CLOSE, P.PARTNERS_VIEW,
        },
    ),
    "responsable_stock": (
        "Responsable de stock",
        "Prepare les receptions, inventaires, pertes et peremptions",
        False,
        {
            P.PRODUCTS_VIEW, P.PRODUCTS_MANAGE, P.STOCK_VIEW, P.STOCK_MANAGE,
            P.INVENTORY_MANAGE, P.LOSS_MANAGE, P.PURCHASE_VIEW, P.PURCHASE_PREPARE,
            P.PARTNERS_VIEW, P.EXPENSES_CREATE,
        },
    ),
    "comptable": (
        "Comptable",
        "Consulte et exporte les rapports, verifie dettes et depenses",
        False,
        {
            P.PRODUCTS_VIEW, P.STOCK_VIEW, P.SALES_VIEW, P.SALES_VIEW_ALL,
            P.PURCHASE_VIEW, P.CASH_VIEW_ALL, P.EXPENSES_VIEW, P.EXPENSES_CREATE,
            P.CREDITS_VIEW, P.CREDITS_MANAGE, P.REPORTS_VIEW, P.REPORTS_EXPORT,
            P.PARTNERS_VIEW, P.PARTNERS_MANAGE,
        },
    ),
    "auditeur": (
        "Auditeur",
        "Consultation en lecture seule des journaux et rapports",
        False,
        {
            P.PRODUCTS_VIEW, P.STOCK_VIEW, P.SALES_VIEW_ALL, P.PURCHASE_VIEW,
            P.CASH_VIEW_ALL, P.EXPENSES_VIEW, P.CREDITS_VIEW, P.REPORTS_VIEW,
            P.PARTNERS_VIEW, P.AUDIT_VIEW,
        },
    ),
}
