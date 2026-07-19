import json
from io import BytesIO

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for

from .json_export import build_pilot_export
from .repository import repository
from .validation import VALID_ENTITY_TYPES, VALID_STATUSES, validate_status_transition, validate_submission


blueprint = Blueprint("sports_editorial_workspace", __name__, url_prefix="/workspace/sports-editorial")
VALID_ROLES = ("journalist", "sub_editor")


@blueprint.app_context_processor
def workspace_context():
    return {"workspace_role": session.get("sports_editorial_role", "journalist"), "workspace_mode": "Local demo mode"}


def _submission_or_404(submission_id):
    submission = repository.get_submission(submission_id)
    if not submission:
        abort(404)
    return submission


def _entities_by_id():
    return {entity["id"]: entity for entity in repository.list_entities()}


def _require_sub_editor():
    if session.get("sports_editorial_role", "journalist") != "sub_editor":
        abort(403, description="Switch to Sub-editor view to change editorial decisions.")


@blueprint.route("")
@blueprint.route("/")
def dashboard():
    submissions = repository.list_submissions()
    counts = {status: sum(item["status"] == status for item in submissions) for status in VALID_STATUSES}
    return render_template("sports-editorial-workspace/dashboard.html", submissions=submissions[:4], counts=counts)


@blueprint.post("/role")
def switch_role():
    role = request.form.get("role", "")
    if role not in VALID_ROLES:
        abort(400)
    session["sports_editorial_role"] = role
    destination = request.form.get("next", "")
    if not destination.startswith("/workspace/sports-editorial"):
        destination = url_for("sports_editorial_workspace.dashboard")
    return redirect(destination)


@blueprint.route("/submit", methods=["GET", "POST"])
def submit():
    values = request.form.to_dict(flat=False) if request.method == "POST" else {}
    if request.method == "POST":
        action = request.form.get("action", "draft")
        status = "submitted" if action == "submit" else "draft"
        data = {
            "title": request.form.get("title", ""), "sport": request.form.get("sport", ""),
            "competition": request.form.get("competition", ""), "event_name": request.form.get("event_name", ""),
            "event_date": request.form.get("event_date", ""), "author_name": request.form.get("author_name", ""),
            "author_email": request.form.get("author_email", ""), "stats": request.form.getlist("stats"),
        }
        errors = validate_submission(data, submitting=status == "submitted")
        if not errors:
            submission = repository.create_submission(data, status)
            return redirect(url_for("sports_editorial_workspace.confirmation", submission_id=submission["id"]))
        for error in errors:
            flash(error, "error")
    return render_template("sports-editorial-workspace/submit.html", values=values)


@blueprint.route("/confirmation/<submission_id>")
def confirmation(submission_id):
    return render_template("sports-editorial-workspace/confirmation.html", submission=_submission_or_404(submission_id))


@blueprint.route("/queue")
def queue():
    status = request.args.get("status", "")
    sport = request.args.get("sport", "")
    order = request.args.get("order", "newest")
    if status not in ("",) + VALID_STATUSES:
        status = ""
    if order not in ("newest", "oldest"):
        order = "newest"
    all_submissions = repository.list_submissions()
    sports = sorted({item["sport"] for item in all_submissions})
    submissions = repository.list_submissions(status=status, sport=sport, order=order)
    return render_template("sports-editorial-workspace/queue.html", submissions=submissions, sports=sports, filters={"status": status, "sport": sport, "order": order}, statuses=VALID_STATUSES)


@blueprint.route("/submissions/<submission_id>", methods=["GET", "POST"])
def detail(submission_id):
    submission = _submission_or_404(submission_id)
    if request.method == "POST":
        _require_sub_editor()
        requested_status = request.form.get("status", submission["status"])
        valid, message = validate_status_transition(submission["status"], requested_status)
        if not valid:
            flash(message, "error")
        else:
            repository.update_review(submission_id, request.form, requested_status)
            flash("Review changes saved.", "success")
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))
    entities = repository.list_entities()
    grouped_entities = {entity_type: [item for item in entities if item["entity_type"] == entity_type] for entity_type in VALID_ENTITY_TYPES}
    return render_template("sports-editorial-workspace/detail.html", submission=repository.get_submission(submission_id), grouped_entities=grouped_entities, entities_by_id=_entities_by_id(), statuses=VALID_STATUSES)


@blueprint.post("/submissions/<submission_id>/entities")
def add_entity(submission_id):
    _require_sub_editor()
    _submission_or_404(submission_id)
    entity_type = request.form.get("entity_type", "")
    name = request.form.get("name", "").strip()
    if entity_type not in VALID_ENTITY_TYPES or not name:
        flash("Choose an entity type and add a name.", "error")
    else:
        repository.add_entity({"entity_type": entity_type, "name": name, "canonical_id": request.form.get("canonical_id", ""), "canonical_url": request.form.get("canonical_url", ""), "country_code": request.form.get("country_code", "")})
        flash(f"{name} is now available to tag.", "success")
    return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id) + "#new-entity")


@blueprint.route("/submissions/<submission_id>/json")
def json_preview(submission_id):
    submission = _submission_or_404(submission_id)
    try:
        payload = build_pilot_export(submission, _entities_by_id())
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))
    return render_template("sports-editorial-workspace/json-preview.html", submission=submission, formatted_json=json.dumps(payload, indent=2, ensure_ascii=False))


@blueprint.route("/exports/<submission_id>.json")
def download_json(submission_id):
    _require_sub_editor()
    submission = _submission_or_404(submission_id)
    if submission["status"] not in ("approved", "exported"):
        abort(403, description="Only approved submissions can be downloaded.")
    payload = build_pilot_export(submission, _entities_by_id())
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    return send_file(BytesIO(data), mimetype="application/json", as_attachment=True, download_name=f"sports-editorial-{submission_id}.json")
