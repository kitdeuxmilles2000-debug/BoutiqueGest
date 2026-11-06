import copy
import tempfile
import unittest
import uuid
from unittest.mock import patch

from app import create_app
from app.config import CONFIG_MAP, DevConfig
from app.extensions import db
from app.models.catalog import Category, Product, Unit, UnitKind
from app.models.user import set_setting
from app.services.github_sync import (
    GitHubConflictError,
    _assert_private_repository,
    _apply_tombstones,
    _find_local_deletions,
    _snapshots_equal,
    sync_now,
)
from app.services.sync import build_snapshot


class GitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_name = f"github_sync_test_{uuid.uuid4().hex}"

        class TestConfig(DevConfig):
            pass

        TestConfig.SQLALCHEMY_DATABASE_URI = (
            "sqlite:///" + f"{self.temp_dir.name}\\test.db".replace("\\", "/")
        )
        CONFIG_MAP[self.config_name] = TestConfig
        self.app = create_app(self.config_name)
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            GITHUB_SYNC_ENABLED=True,
            GITHUB_SYNC_REPOSITORY="owner/repository",
            GITHUB_SYNC_TOKEN="test-token",
            GITHUB_SYNC_BRANCH="boutiquegest-data",
            GITHUB_SYNC_PATH="sync/snapshot.json.gz",
        )
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        CONFIG_MAP.pop(self.config_name, None)
        self.temp_dir.cleanup()

    def test_sync_publishes_all_business_tables_and_reports_commit(self):
        with self.app.app_context():
            with patch(
                "app.services.github_sync._read_snapshot",
                return_value=(None, [], None),
            ), patch(
                "app.services.github_sync._write_snapshot",
                return_value={"commit": {"sha": "commit-sha"}},
            ) as write_snapshot:
                result = sync_now()

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["result"]["commit"]["sha"], "commit-sha")
            published = write_snapshot.call_args.args[1]
            self.assertEqual(set(published), set(build_snapshot()))
            self.assertNotIn("password_hash", str(published))
            self.assertNotIn("pin_hash", str(published))

    def test_sync_retries_if_the_github_file_changed_concurrently(self):
        with self.app.app_context():
            snapshot = build_snapshot()
            with patch(
                "app.services.github_sync._read_snapshot",
                side_effect=[(snapshot, [], "sha-1"), (snapshot, [], "sha-2")],
            ), patch(
                "app.services.github_sync._snapshots_equal",
                return_value=False,
            ), patch(
                "app.services.github_sync._write_snapshot",
                side_effect=[
                    GitHubConflictError("conflit"),
                    {"commit": {"sha": "commit-sha"}},
                ],
            ) as write_snapshot:
                result = sync_now()

            self.assertTrue(result["ok"], result)
            self.assertEqual(write_snapshot.call_count, 2)

    def test_local_deletion_is_recorded_and_applied_on_another_copy(self):
        with self.app.app_context():
            category = Category(name="Boisson")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            product = Product(
                code="TEST-DELETE",
                name="Produit test",
                category_id=category.id,
                base_unit_id=unit.id,
            )
            db.session.add(product)
            db.session.commit()
            snapshot = build_snapshot()
            product_uuid = product.uuid
            set_setting("sync.github_last_sync_at", "2099-01-01T00:00:00")
            db.session.commit()

            db.session.delete(product)
            db.session.commit()
            tombstones = _find_local_deletions(snapshot)
            self.assertEqual(
                [(item["table"], item["uuid"]) for item in tombstones],
                [("products", product_uuid)],
            )

            from app.services.sync import apply_snapshot

            apply_snapshot(snapshot)
            _apply_tombstones(tombstones)
            self.assertIsNone(Product.query.filter_by(uuid=product_uuid).first())

    def test_equal_snapshots_ignore_database_local_integer_ids(self):
        with self.app.app_context():
            category = Category(name="Boisson")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            db.session.add(
                Product(
                    code="TEST-ID",
                    name="Produit test",
                    category_id=category.id,
                    base_unit_id=unit.id,
                )
            )
            db.session.commit()
            local = build_snapshot()
            remote = copy.deepcopy(local)
            models = {
                mapper.local_table.name: mapper.class_
                for mapper in db.Model.registry.mappers
                if mapper.local_table.name in remote["tables"]
            }
            id_maps = {
                table: {row["id"]: row["id"] + 100 for row in rows}
                for table, rows in remote["tables"].items()
            }
            user_id_map = {user["id"]: user["id"] + 100 for user in remote["users"]}
            for table, rows in remote["tables"].items():
                model = models[table]
                for row in rows:
                    row["id"] = id_maps[table][row["id"]]
                    for column in model.__table__.columns:
                        if column.foreign_keys and row[column.name] is not None:
                            target = next(iter(column.foreign_keys)).column.table.name
                            if target == "users":
                                row[column.name] = user_id_map[row[column.name]]
                            elif target in id_maps:
                                row[column.name] = id_maps[target][row[column.name]]
            for user in remote["users"]:
                user["id"] = user_id_map[user["id"]]

            self.assertTrue(_snapshots_equal(local, remote))

    def test_http_mutations_trigger_automatic_sync(self):
        @self.app.get("/sync-test")
        def sync_test_page():
            return "ok"

        @self.app.post("/sync-test")
        def sync_test_mutation():
            return "saved"

        with patch(
            "app.services.github_sync.pull_snapshot",
            return_value={"ok": True, "configured": True, "found": True},
        ) as pull, patch(
            "app.services.github_sync.sync_now",
            return_value={"ok": True, "configured": True},
        ) as push:
            client = self.app.test_client()
            self.assertEqual(client.get("/sync-test").status_code, 200)
            self.assertEqual(client.post("/sync-test").status_code, 200)

        pull.assert_called_once()
        push.assert_called_once()

    def test_public_repository_is_allowed(self):
        with self.app.app_context():
            with patch(
                "app.services.github_sync._api_request",
                return_value={"private": False},
            ):
                result = _assert_private_repository("owner/repository", "test-token")
            self.assertEqual(result, {"private": False})


if __name__ == "__main__":
    unittest.main()
