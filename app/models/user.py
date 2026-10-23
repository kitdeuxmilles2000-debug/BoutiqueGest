"""Utilisateurs, roles, permissions et sessions."""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import BaseModel, utcnow


class RolePermission(db.Model):
    __tablename__ = "role_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = db.Column(
        db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (db.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60))

    def __repr__(self):
        return f"<Permission {self.code}>"


class Role(BaseModel):
    __tablename__ = "roles"

    name = db.Column(db.String(60), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_system = db.Column(db.Boolean, default=False, nullable=False)

    users = db.relationship("User", back_populates="role")
    permissions = db.relationship("Permission", secondary="role_permissions", lazy="joined")

    @property
    def permission_codes(self):
        return {p.code for p in self.permissions}

    def __repr__(self):
        return f"<Role {self.name}>"


class User(UserMixin, BaseModel):
    __tablename__ = "users"

    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    password_hash = db.Column(db.String(255), nullable=False)
    pin_hash = db.Column(db.String(255))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))
    active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)

    role = db.relationship("Role", back_populates="users")

    # --- Flask-Login ---------------------------------------------------
    @property
    def is_active(self):
        return bool(self.active)

    def get_id(self):
        return str(self.id)

    # --- Mots de passe / PIN ------------------------------------------
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_pin(self, pin):
        self.pin_hash = generate_password_hash(str(pin))

    def check_pin(self, pin):
        return bool(self.pin_hash) and check_password_hash(self.pin_hash, str(pin))

    # --- Permissions ---------------------------------------------------
    @property
    def is_super_admin(self):
        return bool(self.role and self.role.is_super_admin)

    def has_permission(self, code):
        if self.is_super_admin:
            return True
        if not self.role:
            return False
        return code in self.role.permission_codes

    def has_any(self, *codes):
        return any(self.has_permission(c) for c in codes)

    # --- Verrouillage --------------------------------------------------
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > utcnow())

    def __repr__(self):
        return f"<User {self.username}>"


class UserSession(BaseModel):
    __tablename__ = "user_sessions"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    device_id = db.Column(db.String(80))
    ip = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    started_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime)
    revoked = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User")


class AppSetting(BaseModel):
    """Parametres applicatifs (cle/valeur), dont ceux de synchronisation."""

    __tablename__ = "app_settings"

    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)

    def __repr__(self):
        return f"<AppSetting {self.key}>"


def get_setting(key, default=None):
    row = AppSetting.query.filter_by(key=key).first()
    return row.value if row and row.value is not None else default


def set_setting(key, value):
    row = AppSetting.query.filter_by(key=key).first()
    if row is None:
        row = AppSetting(key=key)
        db.session.add(row)
    row.value = value
    return row
