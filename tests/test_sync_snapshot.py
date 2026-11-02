import gzip
import json
import uuid
import unittest
import tempfile
from datetime import datetime
from unittest.mock import patch

from app import create_app
from app.config import CONFIG_MAP, DevConfig
from app.extensions import db
from app.models.catalog import Category, Product, Unit, UnitKind
from app.models.user import User
from app.services.sync import apply_snapshot, build_snapshot, sync_now


class SnapshotSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.apps = []
        self.config_names = []

    def tearDown(self):
        for app in self.apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        for config_name in self.config_names:
            CONFIG_MAP.pop(config_name, None)
        self.temp_dir.cleanup()

    def _app(self, token="sync-test-token", read_only=False):
        path = f"{self.temp_dir.name}\\{uuid.uuid4().hex}.db"
        config_name = f"sync_test_{uuid.uuid4().hex}"

        class TestConfig(DevConfig):
            pass

        TestConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + path.replace("\\", "/")
        CONFIG_MAP[config_name] = TestConfig
        self.config_names.append(config_name)
        app = create_app(config_name)
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SYNC_API_TOKEN=token,
            CLOUD_READ_ONLY=read_only,
        )
        with app.app_context():
            db.create_all()
        self.apps.append(app)
        return app

    def test_snapshot_merges_by_uuid_and_never_transfers_credentials(self):
        source_app = self._app()
        with source_app.app_context():
            source_user = User(username="vendeur", full_name="Vendeur local")
            source_user.set_password("secret-local")
            category = Category(name="Boisson")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((source_user, category, unit))
            db.session.flush()
            product = Product(
                code="LOCAL-01",
                name="Produit local",
                category_id=category.id,
                base_unit_id=unit.id,
            )
            db.session.add(product)
            db.session.commit()
            snapshot = build_snapshot()

        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("password_hash", serialized)
        self.assertNotIn("pin_hash", serialized)
        self.assertNotIn("secret-local", serialized)
        self.assertEqual(set(snapshot["users"][0]), {"id", "uuid", "full_name"})

        cloud_app = self._app(read_only=True)
        with cloud_app.app_context():
            cloud_admin = User(username="cloud-admin", full_name="Administrateur Render")
            cloud_admin.set_password("cloud-secret")
            cloud_category = Category(name="Boisson")
            cloud_unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((cloud_admin, cloud_category, cloud_unit))
            db.session.flush()
            db.session.add(
                Product(
                    code="CLOUD-ONLY",
                    name="Produit Render",
                    category_id=cloud_category.id,
                    base_unit_id=cloud_unit.id,
                )
            )
            db.session.commit()
            cloud_category_id = cloud_category.id
            cloud_unit_id = cloud_unit.id

        compressed = gzip.compress(serialized.encode("utf-8"))
        with cloud_app.test_client() as client:
            unauthorized_download = client.get(
                "/api/sync/snapshot",
                headers={"Authorization": "Bearer wrong"},
            )
            self.assertEqual(unauthorized_download.status_code, 401)

            download = client.get(
                "/api/sync/snapshot",
                headers={"Authorization": "Bearer sync-test-token"},
            )
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.headers.get("Content-Encoding"), "gzip")
            remote_payload = json.loads(gzip.decompress(download.data).decode("utf-8"))
            self.assertTrue(remote_payload["ok"])
            self.assertNotIn("cloud-secret", json.dumps(remote_payload))

            unauthorized = client.post(
                "/api/sync/snapshot",
                data=compressed,
                headers={"Content-Encoding": "gzip", "Authorization": "Bearer wrong"},
            )
            self.assertEqual(unauthorized.status_code, 401)

            response = client.post(
                "/api/sync/snapshot",
                data=compressed,
                headers={
                    "Content-Encoding": "gzip",
                    "Authorization": "Bearer sync-test-token",
                },
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertTrue(response.get_json()["ok"])

            replay = client.post(
                "/api/sync/snapshot",
                data=compressed,
                headers={
                    "Content-Encoding": "gzip",
                    "Authorization": "Bearer sync-test-token",
                },
            )
            self.assertEqual(replay.status_code, 200, replay.get_json())

            blocked_write = client.post("/admin/taux")
            self.assertEqual(blocked_write.status_code, 403)

        with cloud_app.app_context():
            imported_product = Product.query.filter_by(code="LOCAL-01").one()
            self.assertEqual(imported_product.category_id, cloud_category_id)
            self.assertEqual(imported_product.base_unit_id, cloud_unit_id)
            self.assertEqual(Product.query.filter_by(code="LOCAL-01").count(), 1)
            self.assertEqual(Product.query.filter_by(code="CLOUD-ONLY").count(), 1)

            mirror = User.query.filter(User.username.startswith("sync_")).one()
            self.assertFalse(mirror.active)
            self.assertEqual(mirror.full_name, "Vendeur local")
            self.assertEqual(User.query.filter_by(username="cloud-admin").count(), 1)

    def test_latest_updated_at_wins_when_merging_the_same_product(self):
        source_app = self._app()
        with source_app.app_context():
            category = Category(name="Boisson")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            source_product = Product(
                code="SYNC-01",
                name="Version locale ancienne",
                category_id=category.id,
                base_unit_id=unit.id,
            )
            db.session.add(source_product)
            db.session.flush()
            source_product.updated_at = datetime(2026, 1, 1)
            source_uuid = source_product.uuid
            db.session.commit()
            older_snapshot = build_snapshot()

        target_app = self._app()
        with target_app.app_context():
            category = Category(name="Boisson")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            target_product = Product(
                uuid=source_uuid,
                code="SYNC-01",
                name="Version web récente",
                category_id=category.id,
                base_unit_id=unit.id,
            )
            db.session.add(target_product)
            db.session.flush()
            target_product.updated_at = datetime(2026, 2, 1)
            db.session.commit()

            apply_snapshot(older_snapshot)
            self.assertEqual(
                Product.query.filter_by(uuid=source_uuid).one().name,
                "Version web récente",
            )

            with source_app.app_context():
                source_product = Product.query.filter_by(uuid=source_uuid).one()
                source_product.name = "Version locale la plus récente"
                source_product.updated_at = datetime(2026, 3, 1)
                db.session.commit()
                newer_snapshot = build_snapshot()

            apply_snapshot(newer_snapshot)
            self.assertEqual(
                Product.query.filter_by(uuid=source_uuid).one().name,
                "Version locale la plus récente",
            )

    def test_sync_now_pulls_merges_and_pushes_combined_snapshot(self):
        local_app = self._app()
        remote_app = self._app()

        def add_product(app, code, name):
            with app.app_context():
                category = Category(name="Boisson")
                unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
                db.session.add_all((category, unit))
                db.session.flush()
                db.session.add(
                    Product(
                        code=code,
                        name=name,
                        category_id=category.id,
                        base_unit_id=unit.id,
                    )
                )
                db.session.commit()

        add_product(local_app, "LOCAL-01", "Produit local")
        add_product(remote_app, "WEB-01", "Produit web")
        with remote_app.app_context():
            remote_snapshot = build_snapshot()

        captured = {}

        def fake_send(snapshot):
            captured["snapshot"] = snapshot
            total = sum(len(rows) for rows in snapshot["tables"].values())
            return {"received": {"total": total}}

        with local_app.app_context():
            with patch(
                "app.services.sync._fetch_remote_snapshot",
                return_value=remote_snapshot,
            ), patch("app.services.sync._sender", return_value=fake_send):
                result = sync_now()

            self.assertTrue(result["ok"], result)
            local_names = {product.name for product in Product.query.all()}
            sent_names = {
                row["name"] for row in captured["snapshot"]["tables"]["products"]
            }
            self.assertEqual(local_names, {"Produit local", "Produit web"})
            self.assertEqual(sent_names, {"Produit local", "Produit web"})

    def test_unknown_snapshot_fields_are_rejected(self):
        app = self._app()
        with app.app_context():
            snapshot = build_snapshot()
            snapshot["tables"]["categories"].append(
                {"id": 1, "uuid": "category-uuid", "name": "Test", "unexpected": True}
            )
            with self.assertRaises(ValueError):
                apply_snapshot(snapshot)

    def test_unique_conflict_rolls_back_the_whole_import(self):
        source_app = self._app()
        with source_app.app_context():
            category = Category(name="Boisson", description="Local")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            db.session.add(
                Product(
                    code="CONFLICT-01",
                    name="Produit local",
                    category_id=category.id,
                    base_unit_id=unit.id,
                )
            )
            db.session.commit()
            snapshot = build_snapshot()

        cloud_app = self._app(read_only=True)
        with cloud_app.app_context():
            category = Category(name="Boisson", description="Render")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            db.session.add(
                Product(
                    code="CONFLICT-01",
                    name="Produit Render",
                    category_id=category.id,
                    base_unit_id=unit.id,
                )
            )
            db.session.commit()

        with cloud_app.test_client() as client:
            response = client.post(
                "/api/sync/snapshot",
                data=gzip.compress(json.dumps(snapshot).encode("utf-8")),
                headers={
                    "Content-Encoding": "gzip",
                    "Authorization": "Bearer sync-test-token",
                },
            )
            self.assertEqual(response.status_code, 409, response.get_json())

        with cloud_app.app_context():
            self.assertEqual(Category.query.filter_by(name="Boisson").one().description, "Render")
            self.assertEqual(User.query.filter(User.username.startswith("sync_")).count(), 0)


if __name__ == "__main__":
    unittest.main()
