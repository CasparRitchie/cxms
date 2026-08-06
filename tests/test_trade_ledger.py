import os
import unittest
from unittest.mock import patch

from app import app
from services.trade_ledger.domain import TransactionValidationError, quarter_bounds, summarise, validate_transaction
from services.trade_ledger.repository import MemoryTradeLedgerRepository
from services.trade_ledger import views


class TradeLedgerDomainTests(unittest.TestCase):
    def test_sale_keeps_gross_cis_and_received_separate(self):
        row = validate_transaction({
            "transaction_date": "2026-08-06", "description": "Extension work", "category": "turnover",
            "amount": "1,000", "cis_deduction": "200", "received_amount": "800",
        }, "sale")
        self.assertEqual(row["amount"], "1000.00")
        self.assertEqual(row["cis_deduction"], "200.00")
        self.assertEqual(row["received_amount"], "800.00")

    def test_invalid_category_and_excess_cis_are_rejected(self):
        with self.assertRaises(TransactionValidationError) as context:
            validate_transaction({"transaction_date": "2026-08-06", "description": "Work", "category": "made_up", "amount": "100", "cis_deduction": "120"}, "sale")
        self.assertIn("category", context.exception.errors)
        self.assertIn("cis_deduction", context.exception.errors)

    def test_quarter_summary_uses_gross_sales(self):
        rows = [
            {"kind": "sale", "amount": "1000.00", "cis_deduction": "200.00", "category": "turnover"},
            {"kind": "purchase", "amount": "250.00", "cis_deduction": "0.00", "category": "materials"},
        ]
        summary = summarise(rows)
        self.assertEqual(str(summary["sales"]), "1000.00")
        self.assertEqual(str(summary["profit"]), "750.00")
        self.assertEqual(str(summary["cis"]), "200.00")
        self.assertEqual(tuple(value.isoformat() for value in quarter_bounds(2026, 4)), ("2026-10-01", "2027-01-01"))


class TradeLedgerPageTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryTradeLedgerRepository()
        self.original_repository = views.repository
        views.repository = self.repository
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.env = patch.dict(os.environ, {"TRADE_LEDGER_ENABLED": "1", "TRADE_LEDGER_ACCESS_PASSWORD": "pilot-password", "TRADE_LEDGER_ID": "test-ledger"})
        self.env.start()
        self.client = app.test_client()

    def tearDown(self):
        views.repository = self.original_repository
        self.env.stop()

    def csrf(self):
        with self.client.session_transaction() as session:
            return session["trade_ledger_csrf"]

    def login(self):
        self.client.get("/workspace/trade-ledger/login")
        return self.client.post("/workspace/trade-ledger/login", data={"csrf_token": self.csrf(), "password": "pilot-password"})

    def test_public_landing_and_protected_workspace(self):
        response = self.client.get("/trade-ledger")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Money in. Money out. Sorted.", response.data)
        protected = self.client.get("/workspace/trade-ledger")
        self.assertEqual(protected.status_code, 302)
        self.assertIn("/workspace/trade-ledger/login", protected.location)

    def test_login_rejects_wrong_password_and_accepts_correct_one(self):
        self.client.get("/workspace/trade-ledger/login")
        wrong = self.client.post("/workspace/trade-ledger/login", data={"csrf_token": self.csrf(), "password": "wrong"})
        self.assertIn(b"not correct", wrong.data)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/workspace/trade-ledger").status_code, 200)

    def test_add_sale_summary_help_and_csv_export(self):
        self.login()
        response = self.client.post("/workspace/trade-ledger/add/sale", data={
            "csrf_token": self.csrf(), "transaction_date": "2026-08-06", "contact": "Main Contractor",
            "description": "Extension", "category": "turnover", "amount": "1000", "cis_deduction": "200", "received_amount": "800",
        })
        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get("/workspace/trade-ledger?year=2026&quarter=3")
        self.assertIn(b"Extension", dashboard.data)
        self.assertIn(b"1000.00", dashboard.data)
        form = self.client.get("/workspace/trade-ledger/add/sale")
        self.assertIn(b"Help with CIS deducted", form.data)
        export = self.client.get("/workspace/trade-ledger/export.csv?year=2026&quarter=3")
        self.assertEqual(export.status_code, 200)
        self.assertIn("trade-ledger-2026-q3.csv", export.headers["Content-Disposition"])
        self.assertIn(b"Trade Ledger export version,1.0", export.data)
        self.assertIn(b"Extension", export.data)

    def test_forms_require_csrf(self):
        self.login()
        response = self.client.post("/workspace/trade-ledger/add/purchase", data={})
        self.assertEqual(response.status_code, 400)

    def test_disabled_product_is_not_public(self):
        with patch.dict(os.environ, {"TRADE_LEDGER_ENABLED": "0"}):
            self.assertEqual(self.client.get("/trade-ledger").status_code, 404)
            self.assertEqual(self.client.get("/workspace/trade-ledger").status_code, 404)
