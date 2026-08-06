from copy import deepcopy
from uuid import uuid4
import os

from services.sports_editorial.supabase_rest import SupabaseRestClient


class MemoryTradeLedgerRepository:
    def __init__(self):
        self.reset()

    def reset(self):
        self.rows = []

    def list_transactions(self, ledger_id, start=None, end=None):
        rows = [row for row in self.rows if row["ledger_id"] == ledger_id]
        if start:
            rows = [row for row in rows if row["transaction_date"] >= start]
        if end:
            rows = [row for row in rows if row["transaction_date"] < end]
        return deepcopy(sorted(rows, key=lambda row: (row["transaction_date"], row["created_at"]), reverse=True))

    def create_transaction(self, ledger_id, values):
        row = {"id": str(uuid4()), "ledger_id": ledger_id, "created_at": "test", **values}
        self.rows.append(row)
        return deepcopy(row)

    def delete_transaction(self, ledger_id, transaction_id):
        before = len(self.rows)
        self.rows = [row for row in self.rows if not (row["ledger_id"] == ledger_id and row["id"] == transaction_id)]
        return len(self.rows) < before


class SupabaseTradeLedgerRepository:
    def __init__(self, client=None):
        self.client = client or SupabaseRestClient()

    def list_transactions(self, ledger_id, start=None, end=None):
        query = {"select": "id,ledger_id,kind,transaction_date,contact,reference,description,category,amount,cis_deduction,received_amount,payment_method,notes,created_at", "ledger_id": f"eq.{ledger_id}", "order": "transaction_date.desc,created_at.desc"}
        ranges = []
        if start:
            ranges.append(f"transaction_date.gte.{start}")
        if end:
            ranges.append(f"transaction_date.lt.{end}")
        if ranges:
            query["and"] = f"({','.join(ranges)})"
        return self.client.request("trade_ledger_transactions", query=query)

    def create_transaction(self, ledger_id, values):
        rows = self.client.request("trade_ledger_transactions", "POST", payload={"ledger_id": ledger_id, **values}, prefer="return=representation")
        return rows[0]

    def delete_transaction(self, ledger_id, transaction_id):
        rows = self.client.request("trade_ledger_transactions", "DELETE", query={"ledger_id": f"eq.{ledger_id}", "id": f"eq.{transaction_id}"}, prefer="return=representation")
        return bool(rows)


repository = SupabaseTradeLedgerRepository()


def ledger_id():
    return os.getenv("TRADE_LEDGER_ID", "pilot")
