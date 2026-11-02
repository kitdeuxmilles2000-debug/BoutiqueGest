import os
import unittest
from unittest.mock import patch

from app.config import _database_uri


class DatabaseConfigTests(unittest.TestCase):
    def test_production_requires_database_url(self):
        with patch.dict(os.environ, {"FLASK_CONFIG": "prod", "DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL est obligatoire"):
                _database_uri()

    def test_production_accepts_explicit_sqlite_database_url(self):
        with patch.dict(
            os.environ,
            {"FLASK_CONFIG": "prod", "DATABASE_URL": "sqlite:///local.db"},
        ):
            self.assertEqual(_database_uri(), "sqlite:///local.db")


if __name__ == "__main__":
    unittest.main()
