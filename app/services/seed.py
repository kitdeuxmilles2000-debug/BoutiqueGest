"""Creation des donnees de reference : permissions, roles, administrateur."""
import os

from app.extensions import db
from app.models.catalog import Category, Unit, UnitKind
from app.models.sales import CashRegister
from app.models.user import Permission, Role, User
from app.security.permissions import DEFAULT_ROLES, PERMISSION_LABELS

DEFAULT_REGISTERS = [
    ("Caisse CDF", "CDF"),
    ("Caisse USD", "USD"),
]


def seed_registers():
    existing = {r.name for r in CashRegister.query.all()}
    created = 0
    for name, currency in DEFAULT_REGISTERS:
        if name not in existing:
            db.session.add(CashRegister(name=name, currency=currency))
            created += 1
    db.session.commit()
    return created

DEFAULT_UNITS = [
    ("L", "Litre", UnitKind.VOLUME),
    ("ML", "Millilitre", UnitKind.VOLUME),
    ("PIECE", "Pièce", UnitKind.PIECE),
    ("BIDON", "Bidon", UnitKind.CAPACITY),
    ("BOUTEILLE", "Bouteille", UnitKind.CAPACITY),
    ("VERRE", "Verre", UnitKind.CAPACITY),
    ("CASIER", "Casier", UnitKind.CAPACITY),
    ("CARTON", "Carton", UnitKind.CAPACITY),
    ("SACHET", "Sachet", UnitKind.CAPACITY),
    ("G", "Gramme", UnitKind.POIDS),
    ("KG", "Kilogramme", UnitKind.POIDS),
    ("CM", "Centimètre", UnitKind.LONGUEUR),
    ("M", "Mètre", UnitKind.LONGUEUR),
]

DEFAULT_CATEGORIES = ["Boisson", "Eau", "Lait", "Accessoire"]

DEFAULT_EXPENSE_CATEGORIES = [
    "Loyer",
    "Electricite / eau",
    "Salaires",
    "Transport",
    "Fournitures",
    "Entretien",
    "Taxes",
    "Divers",
]


def seed_expense_categories():
    from app.models.finance import ExpenseCategory

    existing = {c.name for c in ExpenseCategory.query.all()}
    created = 0
    for name in DEFAULT_EXPENSE_CATEGORIES:
        if name not in existing:
            db.session.add(ExpenseCategory(name=name))
            created += 1
    db.session.commit()
    return created


def seed_units():
    existing = {u.code for u in Unit.query.all()}
    created = 0
    for code, label, kind in DEFAULT_UNITS:
        if code not in existing:
            db.session.add(Unit(code=code, label=label, kind=kind, is_system=True))
            created += 1
    db.session.commit()
    return created


def seed_categories():
    existing = {c.name for c in Category.query.all()}
    created = 0
    for name in DEFAULT_CATEGORIES:
        if name not in existing:
            db.session.add(Category(name=name))
            created += 1
    db.session.commit()
    return created


def seed_permissions():
    existing = {p.code for p in Permission.query.all()}
    created = 0
    for code, (label, category) in PERMISSION_LABELS.items():
        if code not in existing:
            db.session.add(Permission(code=code, label=label, category=category))
            created += 1
    db.session.commit()
    return created


def seed_roles():
    created = 0
    for name, (label, description, is_super_admin, perms) in DEFAULT_ROLES.items():
        role = Role.query.filter_by(name=name).first()
        if role is None:
            role = Role(
                name=name,
                label=label,
                description=description,
                is_super_admin=is_super_admin,
                is_system=True,
            )
            db.session.add(role)
            db.session.flush()
            created += 1
        current = {p.code for p in role.permissions}
        for code in perms:
            if code not in current:
                perm = Permission.query.filter_by(code=code).first()
                if perm is not None:
                    role.permissions.append(perm)
    db.session.commit()
    return created


def seed_admin():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    full_name = os.environ.get("ADMIN_FULLNAME", "Administrateur")

    user = User.query.filter_by(username=username).first()
    if user is not None:
        return user, False

    role = Role.query.filter_by(name="proprietaire").first()
    user = User(
        username=username,
        full_name=full_name,
        role=role,
        active=True,
        must_change_password=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, True


def seed_all():
    seed_permissions()
    seed_roles()
    seed_units()
    seed_categories()
    seed_expense_categories()
    seed_registers()
    user, created = seed_admin()
    return user, created
