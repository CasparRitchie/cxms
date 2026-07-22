import json
import re
from io import BytesIO

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, send_file, session, url_for

from .json_export import build_pilot_export
from .formatting import sanitise_rich_text
from .fis_client import FisApiError, fis_configuration, get_fis_client
from .fis_export import FisPayloadValidationError, build_fis_payload
from .repository import repository
from .validation import VALID_ENTITY_TYPES, VALID_STATUSES, STATUS_LABELS, validate_status_transition, validate_submission
from .auth import COOKIE_NAME, auth_configuration, authenticate, current_user, list_workspace_users, make_token, provision_workspace_user, require_editor, require_workspace_admin
from .supabase_rest import SupabaseError
from .calendar import RepositoryCalendarProvider
from .fis_calendar import FisCalendarError, fetch_alpine_world_cup_events
from .fis_athletes import FisAthleteError, fetch_alpine_athletes
from .fis_entities import FisEntityError, countries_from_athletes, fetch_alpine_competitions
from .stat_insights import build_stat_insights, demo_result_rows
from .fis_results import FisResultError, fetch_alpine_results


blueprint = Blueprint("sports_editorial_workspace", __name__, url_prefix="/workspace/sports-editorial")
VALID_ROLES = ("researcher", "sub_editor", "supervisor")


@blueprint.before_request
def require_workspace_session():
    if request.endpoint in ("sports_editorial_workspace.login", "sports_editorial_workspace.logout"):
        return None
    if auth_configuration()["mode"] == "workspace" and not current_user():
        return redirect(url_for("sports_editorial_workspace.login", next=request.path))
    return None


def _event_ids_from_form(value):
    return [int(part) for part in re.split(r"[\s,]+", value.strip()) if part.isdigit() and int(part) > 0]


def _invalid_event_id_tokens(value):
    return [part for part in re.split(r"[\s,]+", value.strip()) if part and (not part.isdigit() or int(part) <= 0)]


@blueprint.app_context_processor
def workspace_context():
    user = current_user() or {}
    mode = auth_configuration()["mode"]
    return {"workspace_role": user.get("role", "researcher"), "workspace_account_role": user.get("workspace_role", "member"), "workspace_mode": "Local demo mode" if mode == "demo" else "Authenticated workspace", "workspace_user": user.get("full_name") or user.get("email") or "Workspace user", "workspace_auth_mode": mode, "status_labels": STATUS_LABELS}


@blueprint.route("/login", methods=["GET", "POST"])
def login():
    if auth_configuration()["mode"] != "workspace":
        return redirect(url_for("sports_editorial_workspace.dashboard"))
    if request.method == "POST":
        try:
            user = authenticate(request.form.get("email", ""), request.form.get("password", ""))
        except SupabaseError:
            user = None
            flash("Workspace sign-in is temporarily unavailable.", "error")
        if user:
            destination = request.form.get("next", "")
            if not destination.startswith("/workspace/sports-editorial"):
                destination = url_for("sports_editorial_workspace.dashboard")
            response = make_response(redirect(destination))
            response.set_cookie(COOKIE_NAME, make_token(user), max_age=7 * 24 * 60 * 60, httponly=True, secure=not request.host.startswith(("localhost", "127.0.0.1")), samesite="Lax", path="/")
            return response
        if not get_flashed_messages_safe():
            flash("Email or password is incorrect, or this account has no Sports Editorial access.", "error")
    return render_template("sports-editorial-workspace/login.html", next=request.args.get("next", ""))


def get_flashed_messages_safe():
    # Avoid importing/consuming Flask's message queue; used only to distinguish an availability error.
    return bool(session.get("_flashes"))


@blueprint.post("/logout")
def logout():
    response = make_response(redirect(url_for("sports_editorial_workspace.login")))
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@blueprint.route("/users", methods=["GET", "POST"])
def users():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    admin = require_workspace_admin()
    if request.method == "POST":
        try:
            provision_workspace_user(admin["workspace_id"], request.form.get("email", ""), request.form.get("full_name", ""), request.form.get("temporary_password", ""), request.form.get("editorial_role", ""))
            flash("User access created. Share the temporary password securely and separately.", "success")
            return redirect(url_for("sports_editorial_workspace.users"))
        except (ValueError, SupabaseError) as exc:
            flash(str(exc), "error")
    return render_template("sports-editorial-workspace/users.html", users=list_workspace_users(admin["workspace_id"]))


@blueprint.route("/calendar", methods=["GET", "POST"])
def calendar():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_workspace_admin()
    season_code = request.form.get("season_code", "2027") if request.method == "POST" else request.args.get("season_code", "2027")
    if request.method == "POST":
        try:
            events, source_url = fetch_alpine_world_cup_events(season_code)
            count = repository.upsert_calendar_events(events)
            flash(f"Imported {count} Alpine World Cup events from the public FIS calendar.", "success")
            return redirect(url_for("sports_editorial_workspace.calendar", season_code=season_code))
        except (FisCalendarError, SupabaseError) as exc:
            flash(str(exc), "error")
    events = _calendar_events()
    return render_template("sports-editorial-workspace/calendar.html", events=events, season_code=season_code)


@blueprint.route("/athletes", methods=["GET", "POST"])
def athletes():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_workspace_admin()
    season_code = request.form.get("season_code", "2027") if request.method == "POST" else request.args.get("season_code", "2027")
    if request.method == "POST":
        try:
            imported, source_url, list_name = fetch_alpine_athletes(season_code)
            count = repository.upsert_athletes(imported)
            country_count = repository.upsert_entities(countries_from_athletes(imported))
            flash(f"Imported {count} Alpine athletes and {country_count} FIS nations from {list_name or 'the official FIS points list'}.", "success")
            return redirect(url_for("sports_editorial_workspace.athletes", season_code=season_code))
        except (FisAthleteError, SupabaseError) as exc:
            flash(str(exc), "error")
    catalogue = [entity for entity in repository.list_entities(entity_type="athlete", limit=200) if str(entity.get("canonical_id") or "").isdigit()]
    athlete_count = f"{len(catalogue)}+" if len(catalogue) == 200 else str(len(catalogue))
    return render_template("sports-editorial-workspace/athletes.html", athletes=catalogue, athlete_count=athlete_count, season_code=season_code)


@blueprint.route("/competitions", methods=["GET", "POST"])
def competitions():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_workspace_admin()
    if request.method == "POST":
        try:
            imported, failures = fetch_alpine_competitions(_calendar_events())
            count = repository.upsert_entities(imported)
            suffix = f" {failures} event pages could not be read and can be retried." if failures else ""
            flash(f"Imported {count} Alpine competitions from the public FIS event pages.{suffix}", "success")
            return redirect(url_for("sports_editorial_workspace.competitions"))
        except (FisEntityError, SupabaseError) as exc:
            flash(str(exc), "error")
    catalogue = repository.list_entities(entity_type="competition", limit=300)
    countries = repository.list_entities(entity_type="country", limit=300)
    return render_template("sports-editorial-workspace/competitions.html", competitions=catalogue, countries=countries, season_code=request.args.get("season_code", "2027"))


@blueprint.post("/entities/refresh/<step>")
def refresh_entities(step):
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_workspace_admin()
    season_code = request.form.get("season_code", "2027")
    try:
        if step == "events":
            events, _ = fetch_alpine_world_cup_events(season_code)
            count = repository.upsert_calendar_events(events)
            return jsonify({"ok": True, "message": f"{count} events updated."})
        if step == "athletes":
            athletes, _, list_name = fetch_alpine_athletes(season_code)
            athlete_count = repository.upsert_athletes(athletes)
            country_count = repository.upsert_entities(countries_from_athletes(athletes))
            return jsonify({"ok": True, "message": f"{athlete_count} athletes and {country_count} countries updated from {list_name or 'the official points list'}."})
        if step == "competitions":
            competitions, failures = fetch_alpine_competitions(_calendar_events())
            count = repository.upsert_entities(competitions)
            warning = f" {failures} event pages could not be read and can be retried." if failures else ""
            return jsonify({"ok": True, "message": f"{count} competitions updated.{warning}"})
        return jsonify({"ok": False, "error": "Unknown refresh step."}), 400
    except (FisCalendarError, FisAthleteError, FisEntityError, SupabaseError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


def _submission_or_404(submission_id):
    submission = repository.get_submission(submission_id)
    if not submission:
        abort(404)
    return submission


def _entities_by_id(submission=None):
    if submission is None:
        return {}
    entity_ids = [entity_id for stat in submission.get("stats", []) for entity_id in stat.get("entity_ids", [])]
    return {entity["id"]: entity for entity in repository.get_entities_by_ids(entity_ids)}


def _calendar_events():
    return RepositoryCalendarProvider(repository).list_events()


def _require_sub_editor():
    return require_editor()


def _flash_fis_error(exc):
    if isinstance(exc, FisPayloadValidationError):
        for message in exc.errors:
            flash(message, "error")
        return
    flash(f"FIS request failed ({exc.status_code}): {exc}", "error")
    for path, messages in (exc.details.get("errors") or {}).items():
        for message in messages if isinstance(messages, list) else [messages]:
            flash(f"{path}: {message}", "error")
    if exc.details.get("currentVersion") is not None:
        flash(f"FIS currently has version {exc.details['currentVersion']}. Reload, review the latest sheet and try again.", "error")
    if exc.details.get("retryAfter"):
        flash(f"FIS has rate-limited requests. Try again after {exc.details['retryAfter']} seconds.", "error")


@blueprint.route("")
@blueprint.route("/")
def dashboard():
    submissions = repository.list_submissions()
    counts = {status: sum(item["status"] == status for item in submissions) for status in VALID_STATUSES}
    return render_template("sports-editorial-workspace/dashboard.html", submissions=submissions[:4], counts=counts)


@blueprint.get("/stat-insights")
def stat_insights():
    race_ids = list(dict.fromkeys(re.findall(r"\d+", request.args.get("race_ids", ""))))[:10]
    rows = demo_result_rows()
    source = "demonstration"
    failures = 0
    if race_ids:
        known = {str(item.get("canonical_id")): item for item in repository.list_entities(entity_type="competition")}
        races = [known.get(race_id, {"canonical_id": race_id, "name": f"FIS competition {race_id}"}) for race_id in race_ids]
        try:
            rows, failures = fetch_alpine_results(races)
            source = "fis_official_results"
        except FisResultError as exc:
            flash(str(exc), "error")
    venue = request.args.get("venue", "").strip()
    discipline = request.args.get("discipline", "").strip().upper()
    athlete = request.args.get("athlete", "").strip()
    venues = sorted({row["venue"] for row in rows})
    disciplines = sorted({row["discipline"] for row in rows})
    venue = venue if venue in venues else ""
    discipline = discipline if discipline in disciplines else ""
    return render_template("sports-editorial-workspace/stat-insights.html",
                           insights=build_stat_insights(rows, venue, discipline, athlete),
                           venues=venues, disciplines=disciplines,
                           filters={"venue": venue, "discipline": discipline, "athlete": athlete, "race_ids": ", ".join(race_ids)},
                           result_source=source, result_failures=failures)


def _assignment_users():
    if auth_configuration()["mode"] == "demo":
        return [
            {"id": "demo-user", "full_name": "Jamie Laurent", "editorial_role": "researcher"},
            {"id": "demo-researcher-2", "full_name": "Andrew Hendry", "editorial_role": "researcher"},
            {"id": "demo-sub-editor", "full_name": "Nick L.", "editorial_role": "sub_editor"},
            {"id": "demo-supervisor", "full_name": "Supervisor Demo", "editorial_role": "supervisor"},
        ]
    user = current_user() or {}
    return list_workspace_users(user.get("workspace_id"))


@blueprint.post("/role")
def switch_role():
    if auth_configuration()["mode"] != "demo":
        abort(404)
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
    _require_sub_editor()
    values = request.form.to_dict(flat=False) if request.method == "POST" else {}
    if request.method == "POST":
        values["content_html"] = [sanitise_rich_text(value) for value in request.form.getlist("content_html")]
        action = request.form.get("action", "draft")
        status = "submitted" if action == "submit" else "draft"
        raw_event_ids = " ".join(request.form.getlist("fis_event_ids"))
        data = {
            "title": request.form.get("title", ""), "sport": "alpine_skiing",
            "competition": request.form.get("competition", ""), "event_name": request.form.get("event_name", ""),
            "gender": request.form.get("gender", ""), "location": request.form.get("location", ""), "fis_event_ids": _event_ids_from_form(raw_event_ids),
            "event_date": request.form.get("event_date", ""), "author_name": (current_user() or {}).get("full_name") or (current_user() or {}).get("email") or "Workspace user",
            "author_email": (current_user() or {}).get("email", ""), "content": [
                {"content_type": content_type, "content_html": sanitise_rich_text(content_html)}
                for content_type, content_html in zip(request.form.getlist("content_type"), request.form.getlist("content_html"))
            ],
            "amp_id": request.form.get("amp_id", ""), "client_name": request.form.get("client_name", "FIS"),
            "publication_deadline": request.form.get("publication_deadline", ""), "researcher_deadline": request.form.get("researcher_deadline", ""),
            "researcher_user_id": request.form.get("researcher_user_id", ""), "researcher_name": request.form.get("researcher_name", ""),
            "sub_editor_user_id": request.form.get("sub_editor_user_id", ""), "sub_editor_name": request.form.get("sub_editor_name", ""),
        }
        users_by_id = {item["id"]: item for item in _assignment_users()}
        data["researcher_name"] = users_by_id.get(data["researcher_user_id"], {}).get("full_name", "")
        data["sub_editor_name"] = users_by_id.get(data["sub_editor_user_id"], {}).get("full_name", "")
        errors = [] if data["title"].strip() else ["Add a title for this stat sheet."]
        if _invalid_event_id_tokens(raw_event_ids):
            errors.append("FIS calendar event IDs must contain digits only, for example 123456.")
        if not errors:
            submission = repository.create_submission(data, status)
            return redirect(url_for("sports_editorial_workspace.confirmation", submission_id=submission["id"]))
        for error in errors:
            flash(error, "error")
    return render_template("sports-editorial-workspace/submit.html", values=values, calendar_events=_calendar_events(), assignment_users=_assignment_users())


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


@blueprint.get("/entities/search")
def search_entities():
    query = request.args.get("q", "").strip()
    entity_type = request.args.get("type", "").strip()
    if entity_type and entity_type not in VALID_ENTITY_TYPES:
        return jsonify({"ok": False, "error": "Unknown entity type."}), 400
    if len(query) < 2:
        return jsonify({"ok": True, "results": []})
    results = repository.search_entities(query, entity_type=entity_type)
    return jsonify({"ok": True, "provider": "local_pilot", "results": [
        {"id": item["id"], "type": item["entity_type"], "name": item["name"], "canonical_id": item.get("canonical_id"), "country_code": item.get("country_code")}
        for item in results
    ]})


@blueprint.route("/submissions/<submission_id>", methods=["GET", "POST"])
def detail(submission_id):
    submission = _submission_or_404(submission_id)
    if request.method == "POST":
        _require_sub_editor()
        requested_status = request.form.get("status", submission["status"])
        raw_event_ids = " ".join(request.form.getlist("fis_event_ids"))
        event_ids = _event_ids_from_form(raw_event_ids)
        valid, message = validate_status_transition(submission["status"], requested_status)
        if _invalid_event_id_tokens(raw_event_ids):
            valid, message = False, "FIS calendar event IDs must contain digits only, for example 123456."
        elif requested_status in ("approved", "exported") and not event_ids:
            valid, message = False, "Select at least one FIS calendar event before approval."
        if not valid:
            flash(message, "error")
        else:
            repository.update_review(submission_id, request.form, requested_status)
            flash("Review changes saved.", "success")
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))
    grouped_entities = {entity_type: [] for entity_type in VALID_ENTITY_TYPES}
    refreshed = repository.get_submission(submission_id)
    role = (current_user() or {}).get("role", "researcher")
    return render_template("sports-editorial-workspace/detail.html", submission=refreshed, grouped_entities=grouped_entities, entities_by_id=_entities_by_id(refreshed), statuses=VALID_STATUSES, fis_publication=repository.get_fis_publication(submission_id), fis_config=fis_configuration(), calendar_events=_calendar_events(), assignment_users=_assignment_users(), can_review=role in ("sub_editor", "supervisor"), can_edit_research=role == "researcher" and refreshed["status"] in ("draft", "changes_requested"))


@blueprint.route("/submissions/<submission_id>/research", methods=["GET", "POST"])
def research(submission_id):
    user = current_user() or {}
    if user.get("role") != "researcher":
        abort(403, description="Researcher access is required.")
    submission = _submission_or_404(submission_id)
    if submission["status"] not in ("draft", "changes_requested"):
        abort(403, description="This stat sheet is locked while it is in sub edit or publication.")
    if request.method == "POST":
        action = request.form.get("action", "draft")
        content = [{"content_type": kind, "content_html": sanitise_rich_text(value)} for kind, value in zip(request.form.getlist("content_type"), request.form.getlist("content_html"))]
        errors = validate_submission({"title": submission["title"], "sport": submission["sport"], "fis_event_ids": submission.get("fis_event_ids", []), "content": content}, submitting=action == "submit")
        if not errors:
            repository.update_research(submission_id, request.form, submit=action == "submit")
            flash("Stat sheet submitted for sub edit." if action == "submit" else "Research saved.", "success")
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))
        for error in errors:
            flash(error, "error")
    return render_template("sports-editorial-workspace/research.html", submission=submission)


@blueprint.get("/submissions/<submission_id>/fis-preview")
def fis_preview(submission_id):
    submission = _submission_or_404(submission_id)
    publication = repository.get_fis_publication(submission_id) or {}
    try:
        payload = build_fis_payload(submission, _entities_by_id(submission), expected_version=publication.get("version"), organisation_uuid=fis_configuration()["organisation_uuid"], calendar_events=_calendar_events())
        errors = []
    except FisPayloadValidationError as exc:
        payload, errors = None, exc.errors
    return render_template("sports-editorial-workspace/fis-preview.html", submission=submission, payload=payload, formatted_json=json.dumps(payload, indent=2, ensure_ascii=False) if payload else "", errors=errors, fis_config=fis_configuration())


@blueprint.post("/submissions/<submission_id>/fis-publish")
def fis_publish(submission_id):
    _require_sub_editor()
    submission = _submission_or_404(submission_id)
    if submission["status"] not in ("approved", "exported"):
        abort(403, description="Approve the submission in CXMS before publishing to FIS.")
    previous = repository.get_fis_publication(submission_id) or {}
    config = fis_configuration()
    try:
        payload = build_fis_payload(submission, _entities_by_id(submission), expected_version=previous.get("version"), organisation_uuid=config["organisation_uuid"], calendar_events=_calendar_events())
        publication = get_fis_client().publish(submission.get("fis_external_id") or f"cxms-{submission_id}", payload, previous=previous, submission=submission)
        repository.save_fis_publication(submission_id, publication)
        flash("FIS simulation completed. No data was transmitted." if config["mode"] == "mock" else "Published to FIS.", "success")
    except (FisPayloadValidationError, FisApiError) as exc:
        _flash_fis_error(exc)
    return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))


@blueprint.post("/submissions/<submission_id>/fis-withdraw")
def fis_withdraw(submission_id):
    _require_sub_editor()
    submission = _submission_or_404(submission_id)
    previous = repository.get_fis_publication(submission_id)
    if not previous or previous.get("status") != "published":
        abort(409, description="This sheet is not currently published to FIS.")
    try:
        publication = get_fis_client().withdraw(submission.get("fis_external_id") or f"cxms-{submission_id}", previous=previous)
        repository.save_fis_publication(submission_id, publication)
        flash("FIS simulation withdrawn." if fis_configuration()["mode"] == "mock" else "FIS sheet withdrawn.", "success")
    except FisApiError as exc:
        _flash_fis_error(exc)
    return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))


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
        payload = build_pilot_export(submission, _entities_by_id(submission))
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
    payload = build_pilot_export(submission, _entities_by_id(submission))
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    return send_file(BytesIO(data), mimetype="application/json", as_attachment=True, download_name=f"sports-editorial-{submission_id}.json")
