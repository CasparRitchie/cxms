import json
import re
from datetime import date
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
from .creation import (
    MAX_SEASON, MIN_SEASON, canonical_calendar_events, creation_options,
    parse_display_date, resolve_calendar_event, validate_choice_combination,
)


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


def _season_code(raw_value, event_ids, event_date):
    raw_value = str(raw_value or "").strip()
    if raw_value:
        return int(raw_value) if raw_value.isdigit() and 2000 <= int(raw_value) <= 2100 else None
    requested = {str(event_id) for event_id in event_ids}
    seasons = {
        int(event.get("metadata", {}).get("season_code"))
        for event in _calendar_events()
        if str(event.get("canonical_id")) in requested
        and str(event.get("metadata", {}).get("season_code") or "").isdigit()
    }
    if len(seasons) == 1:
        return seasons.pop()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date or ""):
        year, month = (int(part) for part in event_date.split("-")[:2])
        return year + 1 if month >= 7 else year
    return None


def _invalid_review_entity_links(form_data, submission):
    block_ids = form_data.getlist("content_id") or [block["id"] for block in submission.get("stats", [])]
    requested = list(dict.fromkeys(value for block_id in block_ids for value in form_data.getlist(f"entity_ids_{block_id}")))
    entities = {entity["id"]: entity for entity in repository.get_entities_by_ids(requested)}
    invalid = []
    for entity_id in requested:
        entity = entities.get(entity_id) or {}
        canonical_id = str(entity.get("canonical_id") or "")
        entity_type = entity.get("entity_type")
        valid = canonical_id.isdigit() if entity_type in ("athlete", "event", "competition") else bool(re.fullmatch(r"[A-Z]{3}", canonical_id)) if entity_type == "country" else False
        if not valid:
            invalid.append(entity.get("name") or entity_id)
    return invalid


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
    return redirect(url_for("sports_editorial_workspace.queue"))


@blueprint.get("/stat-insights")
def stat_insights():
    race_ids = list(dict.fromkeys(re.findall(r"\d+", request.args.get("race_ids", ""))))[:10]
    coverage = repository.list_result_competitions()
    rows = repository.list_results(race_ids=race_ids) if coverage else []
    source = "demonstration"
    if rows:
        source = "fis_official_results"
    elif coverage and race_ids:
        flash("Those competitions have not been imported yet. A supervisor can add them with the controlled refresh.", "notice")
    if not rows:
        rows = demo_result_rows()
    venue = request.args.get("venue", "").strip()
    discipline = request.args.get("discipline", "").strip().upper()
    athlete = request.args.get("athlete", "").strip()
    season = request.args.get("season", "").strip()
    gender = request.args.get("gender", "").strip().upper()
    nation = request.args.get("nation", "").strip().upper()
    if source == "fis_official_results":
        rows = [row for row in rows if (not season or str(row.get("season_code") or "") == season)
                and (not gender or row.get("gender") == gender) and (not nation or row.get("nation") == nation)]
    venues = sorted({row["venue"] for row in rows})
    disciplines = sorted({row["discipline"] for row in rows})
    seasons = sorted({str(item["season_code"]) for item in coverage if item.get("season_code")}, reverse=True)
    nations = sorted({row["nation"] for row in rows if row.get("nation")})
    venue = venue if venue in venues else ""
    discipline = discipline if discipline in disciplines else ""
    return render_template("sports-editorial-workspace/stat-insights.html",
                           insights=build_stat_insights(rows, venue, discipline, athlete),
                           venues=venues, disciplines=disciplines, seasons=seasons, nations=nations, coverage=coverage,
                           filters={"venue": venue, "discipline": discipline, "athlete": athlete, "race_ids": ", ".join(race_ids),
                                    "season": season, "gender": gender, "nation": nation},
                           result_source=source, result_failures=0)


@blueprint.post("/stat-insights/import")
def import_stat_results():
    user = current_user() or {}
    if auth_configuration()["mode"] == "workspace":
        require_workspace_admin()
    elif user.get("role") != "supervisor":
        abort(403, description="Supervisor access is required to refresh official results.")
    limit = min(max(int(request.form.get("limit", "5")) if request.form.get("limit", "5").isdigit() else 5, 1), 5)
    season = request.form.get("season", "").strip()
    requested_ids = list(dict.fromkeys(re.findall(r"\d+", request.form.get("race_ids", ""))))[:limit]
    imported = {str(item["race_id"]): item for item in repository.list_result_competitions()}
    candidates = []
    for race in repository.list_entities(entity_type="competition"):
        race_id = str(race.get("canonical_id") or "")
        metadata = race.get("metadata") or {}
        if not race_id.isdigit() or not race.get("canonical_url") or race_id in imported:
            continue
        if requested_ids and race_id not in requested_ids:
            continue
        if season and str(metadata.get("season_code") or "") != season:
            continue
        race_date = str(metadata.get("date") or "")
        if not requested_ids and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", race_date) or race_date > date.today().isoformat()):
            continue
        candidates.append(race)
    candidates.sort(key=lambda item: ((item.get("metadata") or {}).get("date") or "", item.get("canonical_id") or ""), reverse=True)
    candidates = candidates[:limit]
    if not candidates:
        flash("No completed missing competitions are ready to import. Refresh a historical season in the competition catalogue, choose another season, or enter specific completed race IDs.", "notice")
        return redirect(url_for("sports_editorial_workspace.stat_insights"))
    try:
        rows, failures = fetch_alpine_results(candidates, request_interval=1.5)
        by_race = {}
        for row in rows:
            by_race.setdefault(str(row["race_id"]), []).append(row)
        saved = 0
        for race in candidates:
            race_rows = by_race.get(str(race["canonical_id"]), [])
            if race_rows:
                saved += repository.save_result_import(race, race_rows, partial=bool(failures))
        message = f"Stored {saved} official classification rows from {len(by_race)} FIS competitions."
        if failures:
            message += f" {failures} competition could not be read and remains available for a later retry."
        flash(message, "success")
    except (FisResultError, SupabaseError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("sports_editorial_workspace.stat_insights"))


def _assignment_users():
    if auth_configuration()["mode"] == "demo":
        return [
            {"id": "demo-user", "full_name": "Jamie Laurent", "editorial_role": "researcher"},
            {"id": "demo-researcher-2", "full_name": "Andrew Hendry", "editorial_role": "researcher"},
            {"id": "demo-test-user-1", "full_name": "Test User 1", "editorial_role": "researcher"},
            {"id": "demo-test-user-2", "full_name": "Test User 2", "editorial_role": "researcher"},
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
    raw_calendar_events = _calendar_events()
    calendar_events = canonical_calendar_events(raw_calendar_events)
    options = creation_options()
    browser_options = {
        "competitions": {sport: list(items) for sport, items in options["competitions"].items()},
        "events": {f"{sport}|{competition}": list(items) for (sport, competition), items in options["events"].items()},
    }
    if request.method == "POST":
        values["content_html"] = [sanitise_rich_text(value) for value in request.form.getlist("content_html")]
        action = request.form.get("action", "draft")
        status = "submitted" if action == "submit" else "draft"
        sport = request.form.get("sport", "").strip()
        competition = request.form.get("competition", "").strip()
        event_name = request.form.get("event_name", "").strip()
        raw_season = request.form.get("season_code", "").strip()
        errors = []
        if not request.form.get("title", "").strip():
            errors.append("Title is required.")
        errors.extend(validate_choice_combination(sport, competition, event_name))
        season_code = int(raw_season) if re.fullmatch(r"\d{4}", raw_season) else None
        if season_code is None or not MIN_SEASON <= season_code <= MAX_SEASON:
            errors.append(f"Season must be a four-digit year from {MIN_SEASON} to {MAX_SEASON}.")

        parsed_dates = {}
        for field_name, label in (
            ("event_date", "Race Date"),
            ("researcher_deadline", "Researcher Deadline"),
            ("publication_deadline", "Publication Deadline"),
        ):
            parsed_dates[field_name], error = parse_display_date(request.form.get(field_name), label)
            if error:
                errors.append(error)

        selected_event = None
        calendar_id = request.form.get("calendar_event_id", "").strip()
        supplied_event_ids = request.form.getlist("fis_event_ids")
        if calendar_id and season_code is not None:
            selected_event, error = resolve_calendar_event(raw_calendar_events, calendar_id, sport, competition, season_code)
            if error:
                errors.append(error)
        elif calendar_id:
            errors.append("Select a valid Season before choosing a Location.")
        elif any(value.strip() for value in supplied_event_ids) or request.form.get("location", "").strip():
            errors.append("Select Location from the local calendar catalogue.")

        if "amp_id" in request.form:
            errors.append("AMP ID is generated by the system and cannot be supplied.")
        # The existing field stores one client. A second simultaneous client
        # requires a collection/schema migration, not comma-separated storage.
        clients = request.form.getlist("client_name")
        if any(client != "FIS" for client in clients) or len(clients) > 1:
            errors.append("Select Client from the available choices.")

        data = {
            "title": request.form.get("title", ""), "sport": sport,
            "competition": competition, "event_name": event_name,
            "gender": request.form.get("gender", ""),
            "location": selected_event["location"] if selected_event else "",
            "fis_event_ids": [int(selected_event["canonical_id"])] if selected_event else [],
            "event_date": parsed_dates["event_date"], "author_name": (current_user() or {}).get("full_name") or (current_user() or {}).get("email") or "Workspace user",
            "author_email": (current_user() or {}).get("email", ""), "content": [
                {"content_type": content_type, "content_html": sanitise_rich_text(content_html)}
                for content_type, content_html in zip(request.form.getlist("content_type"), request.form.getlist("content_html"))
            ],
            "client_name": clients[0] if clients else "",
            "publication_deadline": parsed_dates["publication_deadline"], "researcher_deadline": parsed_dates["researcher_deadline"],
            "researcher_user_id": request.form.get("researcher_user_id", ""), "researcher_name": request.form.get("researcher_name", ""),
            "sub_editor_user_id": request.form.get("sub_editor_user_id", ""), "sub_editor_name": request.form.get("sub_editor_name", ""),
            "season_code": season_code,
        }
        users_by_id = {item["id"]: item for item in _assignment_users()}
        data["researcher_name"] = users_by_id.get(data["researcher_user_id"], {}).get("full_name", "")
        data["sub_editor_name"] = users_by_id.get(data["sub_editor_user_id"], {}).get("full_name", "")
        if not errors:
            submission = repository.create_submission(data, status)
            return redirect(url_for("sports_editorial_workspace.confirmation", submission_id=submission["id"]))
        for error in errors:
            flash(error, "error")
    return render_template(
        "sports-editorial-workspace/submit.html", values=values, calendar_events=calendar_events,
        assignment_users=_assignment_users(), creation_options=options,
        creation_options_json=json.dumps(browser_options),
    )


@blueprint.route("/confirmation/<submission_id>")
def confirmation(submission_id):
    return render_template("sports-editorial-workspace/confirmation.html", submission=_submission_or_404(submission_id))


@blueprint.route("/queue/modern-preview", endpoint="modern_queue_preview")
@blueprint.route("/queue")
def queue():
    queue_endpoint = request.endpoint
    filter_fields = (
        "amp_id", "client_name", "sport", "competition", "event_name", "gender", "location",
        "season_code", "event_date", "fis_event_ids", "publication_deadline", "researcher_deadline", "status",
        "researcher_user_id", "sub_editor_user_id", "updated_at", "last_modified_by",
    )
    filters = {
        field: list(dict.fromkeys(value.strip() for value in request.args.getlist(field) if value.strip()))
        for field in filter_fields
    }
    filters["status"] = [value for value in filters["status"] if value in VALID_STATUSES]
    sortable = {"amp_id", "client_name", "sport", "competition", "event_name", "gender", "location", "season_code", "event_date", "fis_event_ids", "publication_deadline", "researcher_deadline", "status", "researcher_name", "sub_editor_name", "updated_at", "last_modified_by"}
    raw_sort = request.args.get("sort", "")
    legacy_direction = request.args.get("direction", "desc")
    sort_criteria = []
    for token in raw_sort.split(","):
        field, separator, direction = token.strip().partition(":")
        if not separator:
            direction = legacy_direction
        if field in sortable and direction in ("asc", "desc") and field not in {item[0] for item in sort_criteria}:
            sort_criteria.append((field, direction))
    if not sort_criteria:
        sort_criteria = [("updated_at", "desc")]
    sort_value = ",".join(f"{field}:{direction}" for field, direction in sort_criteria)
    all_submissions = repository.list_submissions()

    def item_filter_values(item, field):
        value = item.get(field)
        if field == "fis_event_ids":
            return [str(event_id) for event_id in (value or [])]
        return [str(value or "")]

    submissions = [
        dict(item) for item in all_submissions
        if all(not values or any(value in values for value in item_filter_values(item, field)) for field, values in filters.items())
    ]
    for field, direction in reversed(sort_criteria):
        submissions.sort(key=lambda item: str(item.get(field) or "").casefold(), reverse=direction == "desc")
    options = {
        field: sorted(
            {value for item in all_submissions for value in item_filter_values(item, field) if value},
            key=str.casefold,
        )
        for field in filter_fields if field != "status"
    }
    users = _assignment_users()
    user_names = {user["id"]: user.get("full_name") or user.get("email") for user in users}
    filter_labels = {
        "amp_id": "AMP ID", "client_name": "Client", "sport": "Sport", "competition": "Competition",
        "event_name": "Event", "gender": "Gender", "location": "Location", "season_code": "Season", "event_date": "Race date",
        "fis_event_ids": "Client event ID", "publication_deadline": "Publication deadline",
        "researcher_deadline": "Researcher deadline", "status": "Status",
        "researcher_user_id": "Researcher", "sub_editor_user_id": "Sub-editor",
        "updated_at": "Last modified", "last_modified_by": "Last modified by",
    }
    active_filters = []
    for field in filter_fields:
        for value in filters[field]:
            display_value = STATUS_LABELS.get(value, value) if field == "status" else user_names.get(value, value)
            remaining_values = [selected for selected in filters[field] if selected != value]
            remove_args = request.args.to_dict(flat=False)
            if remaining_values:
                remove_args[field] = remaining_values
            else:
                remove_args.pop(field, None)
            active_filters.append({
                "field": field, "label": filter_labels[field], "value": display_value,
                "remove_url": url_for(queue_endpoint, **remove_args),
            })
    visible_filter_fields = (
        "status", "client_name", "sport", "season_code", "competition", "event_name", "gender", "location",
        "researcher_user_id", "sub_editor_user_id",
    )
    sort_urls = {}
    sort_add_urls = {}
    for field in sortable:
        sort_args = request.args.to_dict(flat=False)
        primary_direction = sort_criteria[0][1] if sort_criteria[0][0] == field else "desc"
        sort_args["sort"] = f"{field}:{'desc' if primary_direction == 'asc' else 'asc'}"
        sort_args.pop("direction", None)
        sort_urls[field] = url_for(queue_endpoint, **sort_args)
        existing = next((direction for sort_field, direction in sort_criteria if sort_field == field), None)
        added = [
            (sort_field, ("desc" if direction == "asc" else "asc") if sort_field == field else direction)
            for sort_field, direction in sort_criteria
        ]
        if existing is None:
            added.append((field, "asc"))
        add_args = request.args.to_dict(flat=False)
        add_args["sort"] = ",".join(f"{sort_field}:{direction}" for sort_field, direction in added)
        add_args.pop("direction", None)
        sort_add_urls[field] = url_for(queue_endpoint, **add_args)
    reset_args = {"sort": sort_value}
    reset_filters_url = url_for(queue_endpoint, **reset_args)
    clear_sort_args = request.args.to_dict(flat=False)
    clear_sort_args.pop("sort", None)
    clear_sort_args.pop("direction", None)
    clear_sort_url = url_for(queue_endpoint, **clear_sort_args)
    view_args = request.args.to_dict(flat=False)
    standard_view_url = url_for("sports_editorial_workspace.queue", **view_args)
    enhanced_view_url = url_for("sports_editorial_workspace.modern_queue_preview", **view_args)
    queue_view = "enhanced" if queue_endpoint.endswith("modern_queue_preview") else "standard"
    for item in submissions:
        item["queue_url"] = url_for("sports_editorial_workspace.detail", submission_id=item["id"])
    return render_template(
        "sports-editorial-workspace/queue-modern-preview.html" if queue_endpoint.endswith("modern_queue_preview") else "sports-editorial-workspace/queue.html",
        submissions=submissions,
        options=options,
        assignment_users=users,
        filters=filters,
        statuses=VALID_STATUSES,
        active_filters=active_filters,
        filter_fields=filter_fields,
        visible_filter_fields=visible_filter_fields,
        sort_urls=sort_urls,
        sort_add_urls=sort_add_urls,
        sort_criteria=sort_criteria,
        sort_value=sort_value,
        clear_sort_url=clear_sort_url,
        reset_filters_url=reset_filters_url,
        standard_view_url=standard_view_url,
        enhanced_view_url=enhanced_view_url,
        queue_view=queue_view,
        result_count=len(submissions),
        total_count=len(all_submissions),
    )


@blueprint.post("/queue/bulk-assign")
def bulk_assign_queue():
    actor = require_editor()
    submission_ids = list(dict.fromkeys(value for value in request.form.getlist("submission_id") if value))
    assignment_field = request.form.get("assignment_field", "")
    assignment_action = request.form.get("assignment_action", "allocate")
    user_id = request.form.get("user_id", "") if assignment_action == "allocate" else ""
    if not submission_ids:
        abort(400, description="Select at least one stat sheet.")
    required_roles = {
        "researcher_user_id": {"researcher"},
        "sub_editor_user_id": {"sub_editor", "supervisor"},
    }
    if assignment_field not in required_roles:
        abort(400, description="Choose Researcher or Sub-editor allocation.")
    user_name = ""
    if user_id:
        assigned_user = next((user for user in _assignment_users() if user.get("id") == user_id), None)
        if not assigned_user or assigned_user.get("editorial_role") not in required_roles[assignment_field]:
            abort(400, description="Choose a user with the correct editorial role.")
        user_name = assigned_user.get("full_name") or assigned_user.get("email") or ""
    elif assignment_action != "unallocate":
        abort(400, description="Choose a user to allocate.")
    try:
        updated = repository.bulk_assign(
            submission_ids, assignment_field, user_id or None, user_name,
            actor.get("id"), actor.get("full_name") or actor.get("email") or "Workspace user",
        )
    except ValueError as exc:
        abort(400, description=str(exc))
    label = "researcher" if assignment_field == "researcher_user_id" else "sub-editor"
    flash(f"{updated} stat sheet{'s' if updated != 1 else ''} {'unallocated' if not user_id else f'allocated to {user_name}'} as {label}.", "success")
    destination = request.form.get("next", "")
    if not destination.startswith("/workspace/sports-editorial/queue"):
        destination = url_for("sports_editorial_workspace.queue")
    return redirect(destination)


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
        {"id": item["id"], "type": item["entity_type"], "name": item["name"], "canonical_id": item.get("canonical_id"), "canonical_url": item.get("canonical_url"), "country_code": item.get("country_code")}
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
        elif request.form.get("season_code", "").strip() and _season_code(request.form.get("season_code"), event_ids, request.form.get("event_date")) is None:
            valid, message = False, "Season must be the four-digit year in which the season ends, for example 2027."
        elif requested_status in ("approved", "exported") and not event_ids:
            valid, message = False, "Select at least one FIS calendar event before approval."
        elif requested_status in ("approved", "exported"):
            review_ids = request.form.getlist("content_id") or [block["id"] for block in submission.get("stats", [])]
            review_types = request.form.getlist("content_type") or [block.get("content_type", "stat") for block in submission.get("stats", [])]
            if any(kind == "stat" and request.form.get(f"accepted_{block_id}") != "1" for block_id, kind in zip(review_ids, review_types)):
                valid, message = False, "Accept and lock every statistic before approval."
            else:
                invalid_entities = _invalid_review_entity_links(request.form, submission)
                if invalid_entities:
                    valid, message = False, "Fix entity links without valid FIS IDs before approval: " + ", ".join(invalid_entities)
        if valid and requested_status == "changes_requested" and not request.form.get("editor_notes", "").strip():
            valid, message = False, "Add instructions explaining what the researcher needs to change."
        if not valid:
            flash(message, "error")
        else:
            repository.update_review(submission_id, request.form, requested_status)
            workflow_messages = {
                "changes_requested": "Changes requested. The stat sheet is editable by the assigned researcher again.",
                "approved": "Stat sheet approved. The FIS JSON is ready to review.",
                "in_review": "Stat sheet is now in sub edit.",
            }
            flash(workflow_messages.get(requested_status, "Review changes saved."), "success")
            if request.form.get("save_action") == "close":
                return redirect(url_for("sports_editorial_workspace.queue"))
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))
    grouped_entities = {entity_type: [] for entity_type in VALID_ENTITY_TYPES}
    refreshed = repository.get_submission(submission_id)
    role = (current_user() or {}).get("role", "researcher")
    return render_template("sports-editorial-workspace/detail.html", submission=refreshed, grouped_entities=grouped_entities, entities_by_id=_entities_by_id(refreshed), statuses=VALID_STATUSES, fis_publication=repository.get_fis_publication(submission_id), fis_config=fis_configuration(), calendar_events=_calendar_events(), assignment_users=_assignment_users(), can_review=role in ("sub_editor", "supervisor"), can_edit_research=role in ("researcher", "sub_editor", "supervisor") and refreshed["status"] in ("draft", "changes_requested"))


@blueprint.route("/submissions/<submission_id>/research", methods=["GET", "POST"])
def research(submission_id):
    user = current_user() or {}
    if user.get("role") not in ("researcher", "sub_editor", "supervisor"):
        abort(403, description="Editorial access is required.")
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
    return render_template("sports-editorial-workspace/research.html", submission=submission, entities_by_id=_entities_by_id(submission))


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


@blueprint.get("/submissions/<submission_id>/publication-preview")
def publication_preview(submission_id):
    submission = _submission_or_404(submission_id)
    return render_template("sports-editorial-workspace/publication-preview.html", submission=submission, entities_by_id=_entities_by_id(submission))


@blueprint.post("/submissions/<submission_id>/fis-publish")
def fis_publish(submission_id):
    _require_sub_editor()
    submission = _submission_or_404(submission_id)
    if submission["status"] not in ("approved", "exported"):
        abort(403, description="Approve the submission in CXMS before publishing to FIS.")
    if any(block.get("content_type") == "stat" and not block.get("accepted_at") for block in submission.get("stats", [])):
        abort(409, description="Accept and lock every statistic before publishing to FIS.")
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
        repository.set_submission_status(submission_id, "in_review")
        flash("FIS simulation withdrawn." if fis_configuration()["mode"] == "mock" else "FIS sheet withdrawn.", "success")
    except FisApiError as exc:
        _flash_fis_error(exc)
    return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))


@blueprint.post("/submissions/<submission_id>/edit")
def edit_published(submission_id):
    _require_sub_editor()
    submission = _submission_or_404(submission_id)
    publication = repository.get_fis_publication(submission_id) or {}
    if submission.get("status") != "exported" and publication.get("status") != "published":
        abort(409, description="Only a published stat sheet needs to be taken back into edit.")
    if publication.get("status") == "published":
        try:
            withdrawn = get_fis_client().withdraw(submission.get("fis_external_id") or f"cxms-{submission_id}", previous=publication)
            repository.save_fis_publication(submission_id, withdrawn)
        except FisApiError as exc:
            _flash_fis_error(exc)
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))
    repository.set_submission_status(submission_id, "draft")
    flash("The published sheet is now In Progress. Edit it, then submit it for sub edit.", "success")
    return redirect(url_for("sports_editorial_workspace.research", submission_id=submission_id))


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
