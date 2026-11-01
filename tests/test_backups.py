import os
import tempfile
import unittest
import uuid

from flask import render_template
from sqlalchemy import text

from app import create_app
from app.config import CONFIG_MAP, DevConfig
from app.extensions import db
from app.services import db_history


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_name = f"backup_test_{uuid.uuid4().hex}"
        self.database_path = os.path.join(self.temp_dir.name, "boutiquegest.db")
        self.backup_path = os.path.join(self.temp_dir.name, "backups")
        self.history_path = os.path.join(self.temp_dir.name, "history")

        class TestConfig(DevConfig):
            pass

        TestConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + self.database_path.replace("\\", "/")
        TestConfig.BACKUP_DIR = self.backup_path
        TestConfig.BACKUP_RETENTION = 1
        TestConfig.HISTORY_DIR = self.history_path
        CONFIG_MAP[self.config_name] = TestConfig
        self.app = create_app(self.config_name)
        self.app.config.update(TESTING=True)
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        CONFIG_MAP.pop(self.config_name, None)
        self.temp_dir.cleanup()

    def test_backup_cli_verifies_and_applies_retention(self):
        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["backup-db", "--label", "test"])
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertIn("Sauvegarde verifiee", first.output)

        old_backup = next(
            os.path.join(self.backup_path, name)
            for name in os.listdir(self.backup_path)
            if name.endswith(".db")
        )
        os.rename(old_backup, os.path.join(self.backup_path, "boutiquegest_20200101_000000.db"))

        second = runner.invoke(args=["backup-db", "--label", "automatique"])
        self.assertEqual(second.exit_code, 0, second.output)
        backups = [name for name in os.listdir(self.backup_path) if name.endswith(".db")]
        self.assertEqual(len(backups), 1)
        self.assertIn("Anciennes sauvegardes supprimees par retention : 1.", second.output)
        self.assertTrue(os.path.isfile(os.path.join(self.backup_path, "automatic_backup.log")))

    def test_history_snapshot_and_restore_use_configured_database(self):
        with self.app.app_context():
            db.session.execute(text("CREATE TABLE backup_probe (value TEXT NOT NULL)"))
            db.session.execute(text("INSERT INTO backup_probe (value) VALUES ('before')"))
            db.session.commit()

            snapshot = db_history.create_snapshot(label="manuel")
            db.session.execute(text("UPDATE backup_probe SET value = 'after'"))
            db.session.commit()

            restored = db_history.restore_snapshot(snapshot["filename"], reason="test")
            self.assertEqual(restored["restored_from"], snapshot["filename"])
            value = db.session.execute(text("SELECT value FROM backup_probe")).scalar_one()

        self.assertEqual(value, "before")
        self.assertTrue(os.path.isfile(os.path.join(self.history_path, snapshot["filename"])))

    def test_backup_page_distinguishes_sqlite_and_postgresql(self):
        with self.app.test_request_context():
            local_page = render_template(
                "admin/backups.html",
                backups=[],
                retention=None,
                snapshots=[],
                sqlite_database=True,
            )
            cloud_page = render_template(
                "admin/backups.html",
                backups=[],
                retention=None,
                snapshots=[],
                sqlite_database=False,
            )

        self.assertIn("Créer une sauvegarde maintenant", local_page)
        self.assertIn('name="csrf_token"', local_page)
        self.assertIn("Sauvegardes PostgreSQL Render", cloud_page)
        self.assertNotIn("Créer une sauvegarde maintenant", cloud_page)


if __name__ == "__main__":
    unittest.main()
