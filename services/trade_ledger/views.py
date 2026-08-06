import csv
import hmac
import io
import os
import secrets
from functools import wraps

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, session, url_for

from services.sports_editorial.supabase_rest import SupabaseError
from .domain import CATEGORIES, TransactionValidationError, current_quarter, quarter_bounds, summarise, validate_transaction
from .repository import ledger_id, repository


blueprint = Blueprint("trade_ledger", __name__)


def enabled():
    return os.getenv("TRADE_LEDGER_ENABLED", "1").lower() in ("1", "true", "yes")


def csrf_token():
    if not session.get("trade_ledger_csrf"):
        session["trade_ledger_csrf"] = secrets.token_urlsafe(24)
    return session["trade_ledger_csrf"]


def check_csrf():
    if not hmac.compare_digest(str(session.get("trade_ledger_csrf") or ""), str(request.form.get("csrf_token") or "")):
        abort(400, description="This form expired. Go back and try again.")


def require_access(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not enabled():
            abort(404)
        if not session.get("trade_ledger_access"):
            return redirect(url_for("trade_ledger.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@blueprint.app_context_processor
def trade_ledger_context():
    return {"trade_ledger_csrf": csrf_token, "trade_ledger_categories": CATEGORIES}


@blueprint.route("/trade-ledger")
@blueprint.route("/trade-ledger/")
def landing():
    if not enabled():
        abort(404)
    return render_template("trade-ledger/landing.html")


@blueprint.route("/workspace/trade-ledger/login", methods=["GET", "POST"])
def login():
    if not enabled():
        abort(404)
    configured_password = os.getenv("TRADE_LEDGER_ACCESS_PASSWORD", "")
    if request.method == "POST":
        check_csrf()
        if configured_password and hmac.compare_digest(request.form.get("password", ""), configured_password):
            session["trade_ledger_access"] = True
            destination = request.form.get("next", "")
            return redirect(destination if destination.startswith("/workspace/trade-ledger") else url_for("trade_ledger.dashboard"))
        flash("That password is not correct.", "error")
    return render_template("trade-ledger/login.html", configured=bool(configured_password), next=request.args.get("next", ""))


@blueprint.post("/workspace/trade-ledger/logout")
def logout():
    check_csrf()
    session.pop("trade_ledger_access", None)
    return redirect(url_for("trade_ledger.landing"))


def quarter_from_request():
    default_year, default_quarter = current_quarter()
    try:
        year = int(request.args.get("year", default_year))
        quarter = int(request.args.get("quarter", default_quarter))
        start, end = quarter_bounds(year, quarter)
    except (TypeError, ValueError):
        abort(400, description="Choose a valid quarter.")
    return year, quarter, start, end


@blueprint.route("/workspace/trade-ledger")
@blueprint.route("/workspace/trade-ledger/")
@require_access
def dashboard():
    year, quarter, start, end = quarter_from_request()
    try:
        rows = repository.list_transactions(ledger_id(), start.isoformat(), end.isoformat())
    except SupabaseError:
        return render_template("trade-ledger/unavailable.html"), 503
    previous = (year - 1, 4) if quarter == 1 else (year, quarter - 1)
    following = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return render_template("trade-ledger/dashboard.html", rows=rows, summary=summarise(rows), year=year, quarter=quarter, previous=previous, following=following)


@blueprint.route("/workspace/trade-ledger/add/<kind>", methods=["GET", "POST"])
@require_access
def add_transaction(kind):
    if kind not in CATEGORIES:
        abort(404)
    values = request.form.to_dict() if request.method == "POST" else {"kind": kind}
    errors = {}
    if request.method == "POST":
        check_csrf()
        try:
            clean = validate_transaction(request.form, kind)
            repository.create_transaction(ledger_id(), clean)
            flash("Sale saved." if kind == "sale" else "Purchase saved.", "success")
            return redirect(url_for("trade_ledger.dashboard"))
        except TransactionValidationError as exc:
            errors = exc.errors
        except SupabaseError:
            errors["storage"] = "Trade Ledger storage is unavailable. Nothing was saved."
    return render_template("trade-ledger/transaction-form.html", kind=kind, values=values, errors=errors)


@blueprint.post("/workspace/trade-ledger/transactions/<transaction_id>/delete")
@require_access
def delete_transaction(transaction_id):
    check_csrf()
    try:
        if not repository.delete_transaction(ledger_id(), transaction_id):
            abort(404)
    except SupabaseError:
        flash("The transaction could not be deleted because storage is unavailable.", "error")
    else:
        flash("Transaction deleted.", "success")
    return redirect(url_for("trade_ledger.dashboard"))


@blueprint.get("/workspace/trade-ledger/export.csv")
@require_access
def export_csv():
    year, quarter, start, end = quarter_from_request()
    try:
        rows = repository.list_transactions(ledger_id(), start.isoformat(), end.isoformat())
    except SupabaseError:
        return render_template("trade-ledger/unavailable.html"), 503
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Trade Ledger export version", "1.0"])
    writer.writerow(["Period start", start.isoformat()])
    writer.writerow(["Period end", end.isoformat()])
    writer.writerow([])
    writer.writerow(["Date", "Type", "Contact", "Reference", "Description", "Category code", "Gross amount", "CIS deducted", "Amount received", "Payment method", "Notes"])
    for row in sorted(rows, key=lambda item: item["transaction_date"]):
        writer.writerow([row["transaction_date"], row["kind"], row.get("contact", ""), row.get("reference", ""), row["description"], row["category"], row["amount"], row.get("cis_deduction", "0.00"), row.get("received_amount", "0.00"), row.get("payment_method", ""), row.get("notes", "")])
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="trade-ledger-{year}-q{quarter}.csv"'
    return response
