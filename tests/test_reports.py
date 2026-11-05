import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.services.reports import sales_currency_summary


class SalesCurrencySummaryTests(unittest.TestCase):
    def setUp(self):
        created_at = datetime(2026, 11, 5, 10, 30)
        self.sales = [
            SimpleNamespace(currency="CDF", montant_total=Decimal("5000"), created_at=created_at),
            SimpleNamespace(currency="USD", montant_total=Decimal("3"), created_at=created_at),
        ]
        self.start = datetime(2026, 11, 5)
        self.end = datetime(2026, 11, 6)

    @patch("app.services.reports._sales_in")
    def test_daily_totals_are_converted_in_both_currencies(self, sales_in):
        sales_in.return_value = self.sales

        result = sales_currency_summary(self.start, self.end, Decimal("2000"))

        self.assertEqual(result["totals"]["CDF"], Decimal("11000.00"))
        self.assertEqual(result["totals"]["USD"], Decimal("5.50"))
        self.assertEqual(result["daily"][0]["CDF"], Decimal("11000.00"))
        self.assertEqual(result["daily"][0]["USD"], Decimal("5.50"))

    @patch("app.services.reports._sales_in")
    def test_without_rate_daily_totals_remain_separated_by_native_currency(self, sales_in):
        sales_in.return_value = self.sales

        result = sales_currency_summary(self.start, self.end)

        self.assertEqual(result["totals"], {})
        self.assertEqual(result["daily"][0]["CDF"], Decimal("5000.00"))
        self.assertEqual(result["daily"][0]["USD"], Decimal("3.00"))


if __name__ == "__main__":
    unittest.main()
