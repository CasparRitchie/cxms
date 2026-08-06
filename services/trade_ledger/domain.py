from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CATEGORIES = {
    "sale": (
        ("turnover", "Building work and services"),
        ("materials_recharged", "Materials charged to customer"),
        ("other_income", "Other business income"),
        ("unsure", "Not sure"),
    ),
    "purchase": (
        ("materials", "Materials and supplies"),
        ("tools", "Tools and equipment"),
        ("vehicle", "Vehicle and travel"),
        ("subcontractors", "Subcontractors"),
        ("premises", "Premises and storage"),
        ("admin", "Phone, office and admin"),
        ("insurance", "Insurance and professional costs"),
        ("other_expense", "Other business expense"),
        ("unsure", "Not sure"),
    ),
}


class TransactionValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("Please check the highlighted fields.")
        self.errors = errors


def money(value, field, required=True):
    raw = str(value or "").strip().replace("£", "").replace(",", "")
    if not raw and not required:
        return Decimal("0.00")
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise TransactionValidationError({field: "Enter an amount in pounds and pence."}) from exc
    if amount < 0:
        raise TransactionValidationError({field: "Enter an amount of zero or more."})
    return amount


def validate_transaction(values, kind):
    errors = {}
    if kind not in CATEGORIES:
        raise TransactionValidationError({"kind": "Choose sale or purchase."})
    try:
        transaction_date = date.fromisoformat(str(values.get("transaction_date") or ""))
    except ValueError:
        transaction_date = None
        errors["transaction_date"] = "Enter a valid date."
    description = str(values.get("description") or "").strip()
    if not description:
        errors["description"] = "Say what this transaction was for."
    category = str(values.get("category") or "")
    if category not in dict(CATEGORIES[kind]):
        errors["category"] = "Choose a category."
    try:
        amount = money(values.get("amount"), "amount")
        cis_deduction = money(values.get("cis_deduction"), "cis_deduction", required=False) if kind == "sale" else Decimal("0.00")
        received_amount = money(values.get("received_amount"), "received_amount", required=False) if kind == "sale" else amount
    except TransactionValidationError as exc:
        errors.update(exc.errors)
        amount = cis_deduction = received_amount = Decimal("0.00")
    if kind == "sale" and cis_deduction > amount:
        errors["cis_deduction"] = "CIS deducted cannot be more than the gross sale."
    if errors:
        raise TransactionValidationError(errors)
    return {
        "kind": kind,
        "transaction_date": transaction_date.isoformat(),
        "contact": str(values.get("contact") or "").strip(),
        "reference": str(values.get("reference") or "").strip(),
        "description": description,
        "category": category,
        "amount": str(amount),
        "cis_deduction": str(cis_deduction),
        "received_amount": str(received_amount),
        "payment_method": str(values.get("payment_method") or "").strip(),
        "notes": str(values.get("notes") or "").strip(),
    }


def quarter_bounds(year, quarter):
    quarter = int(quarter)
    if quarter not in (1, 2, 3, 4):
        raise ValueError("Quarter must be between 1 and 4.")
    start_month = 1 + (quarter - 1) * 3
    start = date(int(year), start_month, 1)
    end = date(int(year) + (1 if quarter == 4 else 0), 1 if quarter == 4 else start_month + 3, 1)
    return start, end


def current_quarter(today=None):
    today = today or date.today()
    return today.year, ((today.month - 1) // 3) + 1


def summarise(rows):
    sales = sum((Decimal(str(row["amount"])) for row in rows if row["kind"] == "sale"), Decimal("0"))
    purchases = sum((Decimal(str(row["amount"])) for row in rows if row["kind"] == "purchase"), Decimal("0"))
    cis = sum((Decimal(str(row.get("cis_deduction") or 0)) for row in rows if row["kind"] == "sale"), Decimal("0"))
    by_category = {}
    for row in rows:
        key = (row["kind"], row["category"])
        by_category[key] = by_category.get(key, Decimal("0")) + Decimal(str(row["amount"]))
    return {"sales": sales, "purchases": purchases, "profit": sales - purchases, "cis": cis, "by_category": by_category}
