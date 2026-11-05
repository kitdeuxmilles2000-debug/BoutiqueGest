import tempfile
import unittest
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app import create_app
from app.config import CONFIG_MAP, DevConfig
from app.extensions import db
from app.models.catalog import Category, Product, Unit, UnitKind
from app.models.stock import StockEntryRequest, StockEntryStatus
from app.services.stock_validation import next_entry_reference
from app.services.stock import stock_valuation_report


class StockEntryReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_name = f"stock_test_{uuid.uuid4().hex}"

        class TestConfig(DevConfig):
            pass

        database_path = f"{self.temp_dir.name}\\{uuid.uuid4().hex}.db"
        TestConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + database_path.replace("\\", "/")
        CONFIG_MAP[self.config_name] = TestConfig
        self.app = create_app(self.config_name)
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        CONFIG_MAP.pop(self.config_name, None)
        self.temp_dir.cleanup()

    def test_reference_uses_highest_existing_number_when_sequence_has_gap(self):
        day = date(2026, 11, 2)
        with self.app.app_context():
            category = Category(name="Test")
            unit = Unit(code="PIECE", label="Pièce", kind=UnitKind.PIECE)
            db.session.add_all((category, unit))
            db.session.flush()
            product = Product(
                code="TEST-01",
                name="Produit test",
                category_id=category.id,
                base_unit_id=unit.id,
            )
            db.session.add(product)
            db.session.flush()
            db.session.add_all(
                StockEntryRequest(
                    reference=f"ENT-{day:%Y%m%d}-{number:04d}",
                    product_id=product.id,
                    status=StockEntryStatus.EN_ATTENTE,
                    quantity=1,
                    qty_base=1,
                    cost_unit=1,
                )
                for number in (1, 3)
            )
            db.session.commit()

            self.assertEqual(next_entry_reference(day), f"ENT-{day:%Y%m%d}-0004")


class StockValuationReportTests(unittest.TestCase):
    def make_product(self, currency, quantity, cost, sale_price, factor=1):
        unit = SimpleNamespace(label="Pièce")
        sale_unit = SimpleNamespace(
            active=True,
            currency=currency,
            factor=Decimal(str(factor)),
            prix_vente=Decimal(str(sale_price)),
            is_sale_default=True,
            unit=unit,
        )
        return SimpleNamespace(
            currency=currency,
            stock_qty=Decimal(str(quantity)),
            cost_avg=Decimal(str(cost)),
            stock_value=Decimal(str(quantity)) * Decimal(str(cost)),
            selling_units=[sale_unit],
        )

    def test_values_are_reported_in_cdf_and_usd_using_current_rate(self):
        product = self.make_product("CDF", 10, 100, 250, factor=2)

        rows, native_totals, converted_totals = stock_valuation_report([product], Decimal("2500"))

        self.assertEqual(rows[0]["cost_value"], Decimal("1000"))
        self.assertEqual(rows[0]["sale_value"], Decimal("1250"))
        self.assertEqual(rows[0]["cost_usd"], Decimal("0.40"))
        self.assertEqual(rows[0]["sale_usd"], Decimal("0.50"))
        self.assertEqual(converted_totals["CDF"]["cost_value"], Decimal("1000"))
        self.assertEqual(converted_totals["USD"]["sale_value"], Decimal("0.50"))
        self.assertEqual(native_totals["CDF"]["sale_value"], Decimal("1250"))

    def test_without_rate_keeps_currency_subtotals_separate(self):
        products = [
            self.make_product("CDF", 2, 100, 150),
            self.make_product("USD", 3, 2, 5),
        ]

        rows, native_totals, converted_totals = stock_valuation_report(products)

        self.assertEqual(rows[0]["cost_usd"], None)
        self.assertEqual(rows[1]["cost_cdf"], None)
        self.assertEqual(native_totals["CDF"]["cost_value"], Decimal("200"))
        self.assertEqual(native_totals["USD"]["cost_value"], Decimal("6"))
        self.assertEqual(converted_totals, {})


if __name__ == "__main__":
    unittest.main()
