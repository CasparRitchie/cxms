import json
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, send_file, session, url_for

from .json_export import build_pilot_export
from .formatting import render_entity_links, render_entity_tags, sanitise_rich_text
from .fis_client import FisApiError, fis_configuration, get_fis_client
from .fis_export import FisPayloadValidationError, build_fis_payload
from .repository import repository
from .validation import ACTIVE_STATUSES, VALID_ENTITY_TYPES, VALID_STATUSES, STATUS_LABELS, validate_editorial_limits, validate_status_transition, validate_submission
from .auth import COOKIE_NAME, auth_configuration, authenticate, current_user, list_workspace_users, make_token, provision_workspace_user, require_editor, require_reviewer, require_editorial_user_admin, require_supervisor, update_workspace_editorial_user
from .supabase_rest import SupabaseError
from .calendar import RepositoryCalendarProvider
from .fis_entities import countries_from_athletes, fis_nation_url
from .fis_public_api import FisPublicApiError, fetch_public_athletes, fetch_public_calendar_feed
from .stat_insights import build_stat_insights, demo_result_rows
from .dashboard_metrics import COVERAGE_RANGE_OPTIONS, build_dashboard_metrics, resolve_coverage_range
from .fis_results import FisResultError, fetch_alpine_results
from .result_coverage import build_result_coverage, competition_result_status, result_coverage_scope
from .race_status import decorate_submission_fis_schedule, decorate_submission_race_status, effective_race_status, matching_competitions
from .creation import (
    MAX_SEASON, MIN_SEASON, canonical_calendar_events, creation_options,
    event_discipline_code, event_discipline_codes, format_display_date, parse_display_date, resolve_calendar_event,
    SPORT_CODES, SPORT_DISPLAY_CODES, SPORT_LABELS, validate_choice_combination,
)
from .edit_locks import lock_timeout_seconds, parse_timestamp


blueprint = Blueprint("sports_editorial_workspace", __name__, url_prefix="/workspace/sports-editorial")
VALID_ROLES = ("researcher", "sub_editor", "supervisor", "fis_specialist")
RESEARCH_ASSIGNMENT_ROLES = ("researcher", "sub_editor", "supervisor")
SUB_EDITOR_ASSIGNMENT_ROLES = ("sub_editor", "supervisor")
QUEUE_PATH_PATTERN = re.compile(r"^/workspace/sports-editorial/queue(?:/modern-preview)?(?:\?|$)")
FIS_ATHLETE_DISCIPLINES = (
    ("", "All supported sports"),
    ("AL", "Alpine Skiing (AL)"),
    ("JP", "Ski Jumping (JP)"),
    ("CC", "Cross-Country Skiing (CC)"),
    ("NK", "Nordic Combined (NK)"),
    ("FS", "Freestyle / Freeski (FS)"),
    ("SB", "Snowboard (SB)"),
)


def _queue_return_url(value=""):
    """Return only a local Sports Editorial queue URL supplied by the queue."""
    candidate = str(value or "").strip()
    return candidate if QUEUE_PATH_PATTERN.match(candidate) else url_for("sports_editorial_workspace.queue")


def _queue_highlight_url(value, submission_id):
    """Add a one-use visual return marker without changing queue filters."""
    base = _queue_return_url(value)
    parts = urlsplit(base)
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True) if key != "highlight"]
    query.append(("highlight", submission_id))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


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
        return int(raw_value) if re.fullmatch(r"\d{4}", raw_value) and 2000 <= int(raw_value) <= 2100 else None
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


CORE_DATA_FIELDS = {
    "title", "sport", "client_name", "competition", "event_name", "gender",
    "location", "season_code", "event_date", "fis_event_ids",
    "publication_deadline", "researcher_deadline", "researcher_user_id",
    "sub_editor_user_id",
}


def _attempts_core_data_change(form_data, submission):
    """Permit stale forms to echo core values, but never let non-supervisors alter them."""
    for field in CORE_DATA_FIELDS:
        if field not in form_data:
            continue
        if field == "fis_event_ids":
            submitted = _event_ids_from_form(" ".join(form_data.getlist(field)))
            if submitted != list(submission.get(field) or []):
                return True
            continue
        submitted = str(form_data.get(field, "")).strip()
        stored = submission.get(field)
        if field in ("event_date", "publication_deadline", "researcher_deadline"):
            parsed, error = parse_display_date(submitted, field.replace("_", " ").title())
            if error or (parsed or "") != (stored or ""):
                return True
        elif submitted != ("" if stored is None else str(stored)):
            return True
    return False


def _invalid_review_entity_links(form_data, submission):
    block_ids = form_data.getlist("content_id") or [block["id"] for block in submission.get("stats", [])]
    requested = list(dict.fromkeys(value for block_id in block_ids for value in form_data.getlist(f"entity_ids_{block_id}")))
    entities = {entity["id"]: entity for entity in repository.get_entities_by_ids(requested)}
    invalid = []
    for entity_id in requested:
        entity = entities.get(entity_id) or {}
        canonical_id = str(entity.get("canonical_id") or "")
        entity_type = entity.get("entity_type")
        valid = bool(re.fullmatch(r"-?\d+", canonical_id)) if entity_type == "athlete" else canonical_id.isdigit() if entity_type in ("event", "competition") else bool(re.fullmatch(r"[A-Z]{3}", canonical_id)) if entity_type == "country" else False
        if not valid:
            invalid.append(entity.get("name") or entity_id)
    return invalid


def _review_form_preview(submission, form_data, parsed_dates=None):
    """Redisplay a rejected review without persisting or discarding its edits."""
    preview = deepcopy(submission)
    parsed_dates = parsed_dates or {}
    for field in (
        "title", "amp_id", "sport", "client_name", "competition", "event_name", "gender",
        "location", "season_code", "publication_deadline", "researcher_deadline",
        "researcher_user_id", "sub_editor_user_id", "working_notes", "unused_stats",
    ):
        if field in form_data:
            preview[field] = form_data.get(field, "")
    if "event_date" in form_data:
        preview["event_date"] = parsed_dates.get("event_date") or form_data.get("event_date", "")
    if "fis_event_ids" in form_data:
        preview["fis_event_ids"] = _event_ids_from_form(" ".join(form_data.getlist("fis_event_ids")))

    existing = {block["id"]: block for block in preview.get("stats", [])}
    block_ids = form_data.getlist("content_id")
    block_types = form_data.getlist("content_type")
    if block_ids:
        blocks = []
        for index, block_id in enumerate(block_ids):
            kind = block_types[index] if index < len(block_types) else "stat"
            kind = "section" if kind == "heading" else kind
            block = deepcopy(existing.get(block_id) or {
                "id": block_id, "stat_text": "", "edited_text": "", "entity_ids": [],
                "entity_mentions": {}, "entity_ranges": {}, "tags": [],
            })
            block["content_type"] = kind
            block["sort_order"] = index
            block["edited_text"] = sanitise_rich_text(
                form_data.get(f"edited_text_{block_id}", block.get("edited_text") or block.get("stat_text", ""))
            )
            accepted = form_data.get(f"accepted_{block_id}") == "1"
            block["accepted_at"] = (block.get("accepted_at") or "pending") if accepted else None
            blocks.append(block)
        preview["stats"] = blocks
    return preview


@blueprint.app_context_processor
def workspace_context():
    user = current_user() or {}
    mode = auth_configuration()["mode"]
    return {"workspace_role": user.get("role", "researcher"), "workspace_account_role": user.get("workspace_role", "member"), "workspace_mode": "Local demo mode" if mode == "demo" else "Authenticated workspace", "workspace_user": user.get("full_name") or user.get("email") or "Workspace user", "workspace_auth_mode": mode, "status_labels": STATUS_LABELS, "sport_codes": SPORT_DISPLAY_CODES, "sport_labels": SPORT_LABELS, "format_display_date": format_display_date, "research_assignment_roles": RESEARCH_ASSIGNMENT_ROLES, "sub_editor_assignment_roles": SUB_EDITOR_ASSIGNMENT_ROLES}


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
    admin = require_editorial_user_admin()
    if request.method == "POST":
        try:
            provision_workspace_user(admin["workspace_id"], request.form.get("email", ""), request.form.get("full_name", ""), request.form.get("temporary_password", ""), request.form.get("editorial_role", ""))
            flash("User access created. Share the temporary password securely and separately.", "success")
            return redirect(url_for("sports_editorial_workspace.users"))
        except (ValueError, SupabaseError) as exc:
            flash(str(exc), "error")
    return render_template("sports-editorial-workspace/users.html", users=list_workspace_users(admin["workspace_id"]))


@blueprint.post("/users/<user_id>")
def update_user(user_id):
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    admin = require_editorial_user_admin()
    if user_id == admin.get("id") and request.form.get("is_active") != "1":
        abort(400, description="You cannot deactivate your own Sports Editorial access.")
    try:
        update_workspace_editorial_user(
            admin["workspace_id"], user_id, request.form.get("full_name", ""),
            request.form.get("editorial_role", ""), request.form.get("is_active") == "1",
        )
        flash("User access updated.", "success")
    except (ValueError, SupabaseError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("sports_editorial_workspace.users"))


@blueprint.route("/manage/stat-sheets")
def manage_stat_sheets():
    require_supervisor()
    query = request.args.get("q", "").strip().casefold()
    competitions = repository.list_entities(entity_type="competition")
    all_submissions = [decorate_submission_race_status(item, competitions) for item in repository.list_submissions(include_inactive=True)]
    users = _assignment_users()
    filter_fields = (
        "status", "client_name", "sport", "season_code", "competition", "event_name",
        "gender", "location", "researcher_user_id", "sub_editor_user_id", "race_status", "visibility",
    )
    filters = {
        field: list(dict.fromkeys(value.strip() for value in request.args.getlist(field) if value.strip()))
        for field in filter_fields
    }
    filters["status"] = [value for value in filters["status"] if value in VALID_STATUSES]

    def admin_filter_values(item, field):
        if field == "event_name":
            return [str(value) for value in (item.get("event_names") or [item.get("event_name")]) if value]
        if field == "gender":
            return [str(value) for value in (item.get("genders") or [item.get("gender")]) if value]
        if field == "visibility":
            return ["active" if item.get("is_active", True) else "inactive"]
        return [str(item.get(field) or "")]

    submissions = [
        item for item in all_submissions
        if all(not values or any(value in values for value in admin_filter_values(item, field))
               for field, values in filters.items())
    ]
    if query:
        submissions = [item for item in submissions if query in " ".join((
            str(item.get("amp_id") or ""), str(item.get("title") or ""),
            str(item.get("location") or ""), " ".join(map(str, item.get("fis_event_ids") or [])),
        )).casefold()]
    options = {
        field: sorted({value for item in all_submissions for value in admin_filter_values(item, field) if value}, key=str.casefold)
        for field in filter_fields if field != "status"
    }
    return render_template(
        "sports-editorial-workspace/manage-stat-sheets.html", submissions=submissions,
        q=request.args.get("q", ""), assignment_users=users, filters=filters, options=options,
        statuses=ACTIVE_STATUSES, result_count=len(submissions),
        assignment_user_labels={user["id"]: user.get("full_name") or user.get("email") for user in users},
        reset_filters_url=url_for("sports_editorial_workspace.manage_stat_sheets"),
    )


@blueprint.post("/manage/stat-sheets/<submission_id>")
def administer_stat_sheet(submission_id):
    supervisor = require_supervisor()
    submission = _submission_or_404(submission_id)
    action = request.form.get("admin_action", "")
    changes = {}
    audit_action = "stat_sheet_administered"
    if action in ("delete", "inactivate"):
        changes["is_active"] = False
        # Keep the deployed audit constraint's historical action name. The UI
        # presents this recoverable state change as Delete.
        audit_action = "stat_sheet_inactivated"
    elif action in ("restore", "reactivate"):
        changes["is_active"] = True
        audit_action = "stat_sheet_reactivated"
    elif action == "change_status":
        requested = request.form.get("status_override") or request.form.get("status", "")
        if submission.get("status") == "exported":
            abort(409, description="Withdraw this sheet through the FIS workflow before changing its internal status.")
        if requested not in ("draft", "in_review", "approved", "fis_review"):
            abort(400, description="Choose an available internal workflow status. Published FIS can only be set by a successful FIS publication.")
        changes["status"] = requested
        audit_action = "status_overridden"
    else:
        abort(400, description="Choose a stat-sheet administration action.")
    repository.administer_submission(submission_id, changes)
    repository.record_audit_event(submission_id, supervisor, audit_action, {
        "previous_status": submission.get("status"), "previous_active": submission.get("is_active", True),
        "previous_race_status": submission.get("race_status", "scheduled"), "changes": changes,
        "reason": request.form.get("reason", "").strip(),
    })
    flash("Stat sheet deleted. It can be restored from the Deleted filter." if changes.get("is_active") is False
          else "Stat sheet restored." if changes.get("is_active") is True
          else "Stat sheet administration updated.", "success")
    return_args = {"q": request.form.get("q", "")}
    for field in (
        "status", "client_name", "sport", "season_code", "competition", "event_name",
        "gender", "location", "researcher_user_id", "sub_editor_user_id", "race_status", "visibility",
    ):
        values = [value for value in request.form.getlist(field) if value]
        if values:
            return_args[field] = values
    return redirect(url_for("sports_editorial_workspace.manage_stat_sheets", **return_args))


@blueprint.route("/calendar", methods=["GET", "POST"])
def calendar():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_supervisor()
    season_code = request.form.get("season_code", "2027") if request.method == "POST" else request.args.get("season_code", "2027")
    discipline_code = (request.form.get("discipline_code", "") if request.method == "POST" else request.args.get("discipline_code", "")).strip().upper()
    valid_discipline_codes = {code for code, _ in FIS_ATHLETE_DISCIPLINES}
    if discipline_code not in valid_discipline_codes:
        discipline_code = ""
    if request.method == "POST":
        try:
            events, _, source_url = fetch_public_calendar_feed(season_code)
            if discipline_code:
                events = [event for event in events if (event.get("metadata") or {}).get("discipline_code") == discipline_code]
            count = repository.upsert_calendar_events(events)
            flash(f"Imported {count} supported events from the FIS Public API calendar feed.", "success")
            return redirect(url_for("sports_editorial_workspace.calendar", season_code=season_code, discipline_code=discipline_code))
        except (FisPublicApiError, SupabaseError) as exc:
            flash(str(exc), "error")
    all_events = _calendar_events()
    event_filter_fields = ("event_season", "event_discipline", "event_category", "event_location")
    event_filters = {
        field: list(dict.fromkeys(value for value in request.args.getlist(field) if value))
        for field in event_filter_fields
    }
    if discipline_code and not event_filters["event_discipline"]:
        event_filters["event_discipline"] = [discipline_code]
    event_options = {
        "event_season": sorted({str((item.get("metadata") or {}).get("season_code")) for item in all_events
                                if (item.get("metadata") or {}).get("season_code")}, reverse=True),
        "event_discipline": sorted({str((item.get("metadata") or {}).get("discipline_code")) for item in all_events
                                    if (item.get("metadata") or {}).get("discipline_code")}),
        "event_category": sorted({str((item.get("metadata") or {}).get("category_code")) for item in all_events
                                  if (item.get("metadata") or {}).get("category_code")}),
        "event_location": sorted({str((item.get("metadata") or {}).get("location_label") or item.get("name"))
                                  for item in all_events if (item.get("metadata") or {}).get("location_label") or item.get("name")}, key=str.casefold),
    }
    event_query = request.args.get("q", "").strip().casefold()

    def event_values(item):
        metadata = item.get("metadata") or {}
        return {
            "event_season": str(metadata.get("season_code") or ""),
            "event_discipline": str(metadata.get("discipline_code") or ""),
            "event_category": str(metadata.get("category_code") or ""),
            "event_location": str(metadata.get("location_label") or item.get("name") or ""),
        }

    events = [item for item in all_events if all(
        not event_filters[field] or event_values(item)[field] in event_filters[field]
        for field in event_filter_fields
    )]
    if event_query:
        events = [item for item in events if event_query in " ".join((
            str(item.get("name") or ""), str(item.get("canonical_id") or ""),
            str((item.get("metadata") or {}).get("location_label") or ""),
        )).casefold()]
    return render_template(
        "sports-editorial-workspace/calendar.html", events=events, event_count=len(events),
        total_event_count=len(all_events), result_count=len(events), season_code=season_code, discipline_code=discipline_code,
        event_disciplines=FIS_ATHLETE_DISCIPLINES, event_filters=event_filters,
        event_discipline_labels=dict(FIS_ATHLETE_DISCIPLINES),
        event_options=event_options, q=request.args.get("q", ""),
        reset_filters_url=url_for("sports_editorial_workspace.calendar"),
    )


@blueprint.route("/athletes", methods=["GET", "POST"])
def athletes():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_supervisor()
    discipline_code = (request.form.get("discipline_code", "") if request.method == "POST" else request.args.get("discipline_code", "")).strip().upper()
    valid_discipline_codes = {code for code, _ in FIS_ATHLETE_DISCIPLINES}
    if discipline_code not in valid_discipline_codes:
        discipline_code = ""
    if request.method == "POST":
        try:
            imported, source_url, list_name = fetch_public_athletes()
            if discipline_code:
                imported = [athlete for athlete in imported if (athlete.get("metadata") or {}).get("discipline_code") == discipline_code]
            count = repository.upsert_athletes(imported)
            country_count = repository.upsert_entities(countries_from_athletes(imported))
            scope = dict(FIS_ATHLETE_DISCIPLINES).get(discipline_code) if discipline_code else "supported-sport"
            flash(f"Imported {count} {scope} athletes and {country_count} FIS nations from {list_name}.", "success")
            return redirect(url_for("sports_editorial_workspace.athletes", discipline_code=discipline_code))
        except (FisPublicApiError, SupabaseError) as exc:
            flash(str(exc), "error")
    catalogue = [entity for entity in repository.list_entities(entity_type="athlete", limit=200) if re.fullmatch(r"-?\d+", str(entity.get("canonical_id") or ""))]
    athlete_count = repository.count_entities(entity_type="athlete")
    return render_template("sports-editorial-workspace/athletes.html", athletes=catalogue, athlete_count=athlete_count,
                           discipline_code=discipline_code, athlete_disciplines=FIS_ATHLETE_DISCIPLINES)


@blueprint.route("/competitions", methods=["GET", "POST"])
def competitions():
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_supervisor()
    if request.method == "POST":
        try:
            _, imported, _ = fetch_public_calendar_feed(request.form.get("season_code", "2027"))
            count = repository.upsert_entities(imported)
            stored = {str(item.get("canonical_id")): item for item in repository.list_entities(entity_type="competition")}
            submissions = repository.list_submissions(include_inactive=True)
            linked = _sync_submission_race_links(list(stored.values()), submissions=submissions)
            for competition in (stored.get(str(item.get("canonical_id")), item) for item in imported):
                _sync_competition_status_to_sheets(competition, submissions=submissions)
            flash(f"Imported {count} supported competitions and refreshed race links on {linked} stat sheets from the FIS Public API calendar feed.", "success")
            return redirect(url_for("sports_editorial_workspace.competitions"))
        except (FisPublicApiError, SupabaseError) as exc:
            flash(str(exc), "error")
    all_competitions = repository.list_entities(entity_type="competition")
    competition_filter_fields = ("race_season", "race_discipline", "race_event", "race_gender", "race_location", "race_status")
    competition_filters = {
        field: list(dict.fromkeys(value for value in request.args.getlist(field) if value))
        for field in competition_filter_fields
    }
    competition_options = {
        "race_season": sorted({str((item.get("metadata") or {}).get("season_code")) for item in all_competitions if (item.get("metadata") or {}).get("season_code")}, reverse=True),
        "race_discipline": sorted({str((item.get("metadata") or {}).get("discipline_code")) for item in all_competitions if (item.get("metadata") or {}).get("discipline_code")}),
        "race_event": sorted({str((item.get("metadata") or {}).get("event_code")) for item in all_competitions if (item.get("metadata") or {}).get("event_code")}),
        "race_gender": sorted({str((item.get("metadata") or {}).get("gender")) for item in all_competitions if (item.get("metadata") or {}).get("gender")}),
        "race_location": sorted({str((item.get("metadata") or {}).get("location")) for item in all_competitions if (item.get("metadata") or {}).get("location")}, key=str.casefold),
        "race_status": ["scheduled", "cancelled"],
    }
    race_query = request.args.get("race_query", "").strip().casefold()
    race_field_keys = {"race_season": "season_code", "race_discipline": "discipline_code", "race_event": "event_code",
                       "race_gender": "gender", "race_location": "location", "race_status": "race_status"}
    catalogue = []
    for item in all_competitions:
        metadata = item.get("metadata") or {}
        values = {field: str(metadata.get(metadata_field) or "") for field, metadata_field in race_field_keys.items()}
        values["race_status"] = str(metadata.get("race_status") or "scheduled")
        if all(not competition_filters[field] or values[field] in competition_filters[field]
               for field in competition_filter_fields):
            catalogue.append(item)
    if race_query:
        catalogue = [item for item in catalogue if race_query in " ".join((
            str(item.get("name") or ""), str(item.get("canonical_id") or ""),
            str((item.get("metadata") or {}).get("codex") or ""),
            str((item.get("metadata") or {}).get("event_id") or ""),
        )).casefold()]
    countries = repository.list_entities(entity_type="country", limit=300)
    country_query = request.args.get("country_query", "").strip()
    if country_query:
        needle = country_query.casefold()
        countries = [country for country in countries if needle in str(country.get("name") or "").casefold()
                     or needle in str(country.get("canonical_id") or "").casefold()]
    return render_template("sports-editorial-workspace/competitions.html", competitions=catalogue, countries=countries,
                           country_count=repository.count_entities(entity_type="country"), country_query=country_query,
                           competition_count=repository.count_entities(entity_type="competition"),
                           competition_result_count=len(catalogue), competition_filters=competition_filters,
                           competition_options=competition_options, race_query=request.args.get("race_query", ""),
                           race_filter_reset_url=url_for("sports_editorial_workspace.competitions", season_code=request.args.get("season_code", "2027")),
                           discipline_labels=dict(FIS_ATHLETE_DISCIPLINES), season_code=request.args.get("season_code", "2027"))


def _sync_competition_status_to_sheets(competition, actor=None, reason="", submissions=None):
    updated = 0
    competition_catalogue = repository.list_entities(entity_type="competition")
    for submission in submissions if submissions is not None else repository.list_submissions(include_inactive=True):
        if not matching_competitions(submission, [competition]):
            continue
        decorated = decorate_submission_race_status(submission, competition_catalogue)
        linked_races = decorated.get("linked_fis_races") or []
        cancelled = [race for race in linked_races if race.get("effective_race_status") == "cancelled"]
        status = "cancelled" if cancelled else "scheduled"
        source = ("fis" if any(race.get("effective_race_status_source") == "fis" for race in cancelled) else "manual") if cancelled else "fis"
        if submission.get("race_status") == status and (status == "scheduled" or submission.get("race_status_source") == source):
            continue
        repository.administer_submission(submission["id"], {"race_status": status, "race_status_source": source})
        if actor:
            repository.record_audit_event(submission["id"], actor,
                                          "race_cancelled" if status == "cancelled" else "race_reinstated", {
                "fis_race_id": competition.get("canonical_id"),
                "codex": (competition.get("metadata") or {}).get("codex"),
                "source": source, "reason": reason,
            })
        updated += 1
    return updated


def _sync_submission_race_links(competitions, submissions=None):
    """Refresh explicit race links from the sheet's FIS event and editorial choices."""
    updated = 0
    for submission in submissions if submissions is not None else repository.list_submissions(include_inactive=True):
        candidate = {**submission, "fis_race_ids": []}
        race_ids = sorted(int(item["canonical_id"]) for item in matching_competitions(candidate, competitions))
        if race_ids == list(submission.get("fis_race_ids") or []):
            continue
        repository.set_submission_race_ids(submission["id"], race_ids)
        submission["fis_race_ids"] = race_ids
        updated += 1
    return updated


@blueprint.get("/race-status")
def race_status():
    require_supervisor()
    query = request.args.get("q", "").strip().casefold()
    competitions = [
        item for item in repository.list_entities(entity_type="competition")
        if str((item.get("metadata") or {}).get("competition_kind") or "race").casefold()
        not in ("training", "qualification")
    ]
    for item in competitions:
        item["effective_race_status"], item["effective_race_status_source"] = effective_race_status(item)
    seasons = sorted({
        str((item.get("metadata") or {}).get("season_code"))
        for item in competitions if (item.get("metadata") or {}).get("season_code")
    }, reverse=True)
    current_season = str(date.today().year + (1 if date.today().month >= 7 else 0))
    filters_submitted = request.args.get("filters") == "1"
    selected_seasons = list(dict.fromkeys(
        value for value in request.args.getlist("season") if value in seasons
    ))
    if not filters_submitted and not selected_seasons:
        future_seasons = sorted(season for season in seasons if season >= current_season)
        default_season = current_season if current_season in seasons else (
            future_seasons[0] if future_seasons else (seasons[0] if seasons else "")
        )
        selected_seasons = [default_season] if default_season else []
    valid_statuses = ("scheduled", "fis_cancelled", "amp_cancelled")
    selected_statuses = list(dict.fromkeys(
        value for value in request.args.getlist("status") if value in valid_statuses
    ))
    filter_options = {
        "discipline_code": sorted({str((item.get("metadata") or {}).get("discipline_code"))
                                   for item in competitions if (item.get("metadata") or {}).get("discipline_code")}),
        "gender": sorted({str((item.get("metadata") or {}).get("gender"))
                          for item in competitions if (item.get("metadata") or {}).get("gender")}),
        "location": sorted({str((item.get("metadata") or {}).get("location"))
                            for item in competitions if (item.get("metadata") or {}).get("location")}, key=str.casefold),
    }
    selected_metadata = {
        field: list(dict.fromkeys(value for value in request.args.getlist(field)
                                 if value in filter_options[field]))
        for field in filter_options
    }
    if selected_seasons:
        competitions = [item for item in competitions
                        if str((item.get("metadata") or {}).get("season_code") or "") in selected_seasons]
    if query:
        competitions = [item for item in competitions if query in " ".join((
            str(item.get("name") or ""), str(item.get("canonical_id") or ""),
            str((item.get("metadata") or {}).get("codex") or ""),
            str((item.get("metadata") or {}).get("event_id") or ""),
        )).casefold()]
    if selected_statuses:
        competitions = [item for item in competitions if (
            ("scheduled" in selected_statuses and item["effective_race_status"] == "scheduled")
            or ("fis_cancelled" in selected_statuses and item["effective_race_status"] == "cancelled"
                and item["effective_race_status_source"] == "fis")
            or ("amp_cancelled" in selected_statuses and item["effective_race_status"] == "cancelled"
                and item["effective_race_status_source"] == "manual")
        )]
    for field, selected in selected_metadata.items():
        if selected:
            competitions = [item for item in competitions
                            if str((item.get("metadata") or {}).get(field) or "") in selected]
    competitions.sort(key=lambda item: (
        str((item.get("metadata") or {}).get("date") or "9999-12-31"), item.get("name", ""),
    ))
    events_by_id = {
        str(item.get("canonical_id") or ""): item
        for item in repository.list_entities(entity_type="event")
    }
    event_groups = []
    for competition in competitions:
        metadata = competition.get("metadata") or {}
        event_id = str(metadata.get("event_id") or "Unassigned")
        group = next((item for item in event_groups if item["event_id"] == event_id), None)
        if group is None:
            event = events_by_id.get(event_id, {})
            event_metadata = event.get("metadata") or {}
            group = {
                "event_id": event_id,
                "event_name": event.get("name") or metadata.get("location") or f"FIS event {event_id}",
                "event_url": event.get("canonical_url") or "",
                "location": event_metadata.get("location_label") or metadata.get("location") or "",
                "races": [],
            }
            event_groups.append(group)
        group["races"].append(competition)
    for group in event_groups:
        dates = [str((item.get("metadata") or {}).get("date") or "") for item in group["races"]]
        dates = sorted(value for value in dates if value)
        group["start_date"] = dates[0] if dates else ""
        group["end_date"] = dates[-1] if dates else ""
        group["manual_cancelled_count"] = sum(
            str((item.get("metadata") or {}).get("manual_race_status") or "").lower() == "cancelled"
            for item in group["races"]
        )
        group["scheduled_count"] = sum(item["effective_race_status"] == "scheduled" for item in group["races"])
    return render_template(
        "sports-editorial-workspace/race-status.html", competitions=competitions, event_groups=event_groups,
        q=request.args.get("q", ""), seasons=seasons, selected_seasons=selected_seasons,
        selected_statuses=selected_statuses, selected_metadata=selected_metadata,
        filter_options=filter_options, result_count=len(competitions),
        reset_filters_url=url_for("sports_editorial_workspace.race_status"),
        discipline_labels=dict(FIS_ATHLETE_DISCIPLINES),
    )


@blueprint.post("/race-status/<race_id>")
def update_race_status(race_id):
    supervisor = require_supervisor()
    competition = next((item for item in repository.list_entities(entity_type="competition")
                        if str(item.get("canonical_id")) == str(race_id)), None)
    if not competition:
        abort(404)
    action = request.form.get("action")
    if action not in ("report_cancelled", "reinstate"):
        abort(400, description="Choose a valid race-status action.")
    metadata = dict(competition.get("metadata") or {})
    metadata.update({
        "manual_race_status": "cancelled" if action == "report_cancelled" else "scheduled",
        "manual_race_status_at": datetime.now(timezone.utc).isoformat(),
        "manual_race_status_by": supervisor.get("full_name") or supervisor.get("email"),
        "manual_race_status_note": request.form.get("reason", "").strip() or None,
    })
    competition["metadata"] = metadata
    repository.upsert_entities([competition])
    linked = _sync_competition_status_to_sheets(competition, supervisor, request.form.get("reason", "").strip())
    flash(f"Race status updated. {linked} linked stat sheet{'s' if linked != 1 else ''} updated.", "success")
    return_args = {"filters": "1", "q": request.form.get("q", "")}
    for field in ("season", "status", "discipline_code", "gender", "location"):
        values = [value for value in request.form.getlist(field) if value]
        if values:
            return_args[field] = values
    return redirect(url_for("sports_editorial_workspace.race_status", **return_args))


@blueprint.post("/race-status/event/<event_id>")
def update_event_race_status(event_id):
    supervisor = require_supervisor()
    action = request.form.get("action")
    if action not in ("report_event_cancelled", "reinstate_event"):
        abort(400, description="Choose a valid event race-status action.")
    competitions = [
        item for item in repository.list_entities(entity_type="competition")
        if str((item.get("metadata") or {}).get("event_id") or "") == str(event_id)
        and str((item.get("metadata") or {}).get("competition_kind") or "race").casefold()
        not in ("training", "qualification")
    ]
    if not competitions:
        abort(404)
    reason = request.form.get("reason", "").strip()
    manual_status = "cancelled" if action == "report_event_cancelled" else "scheduled"
    now = datetime.now(timezone.utc).isoformat()
    for competition in competitions:
        metadata = dict(competition.get("metadata") or {})
        metadata.update({
            "manual_race_status": manual_status,
            "manual_race_status_at": now,
            "manual_race_status_by": supervisor.get("full_name") or supervisor.get("email"),
            "manual_race_status_note": reason or None,
        })
        competition["metadata"] = metadata
    repository.upsert_entities(competitions)
    linked_sheet_ids = set()
    for competition in competitions:
        before = {
            item["id"] for item in repository.list_submissions(include_inactive=True)
            if matching_competitions(item, [competition])
        }
        linked_sheet_ids.update(before)
        _sync_competition_status_to_sheets(competition, supervisor, reason)
    flash(
        f"{len(competitions)} races {'reported cancelled' if manual_status == 'cancelled' else 'reinstated'} "
        f"for FIS event {event_id}. {len(linked_sheet_ids)} linked stat sheet"
        f"{'s' if len(linked_sheet_ids) != 1 else ''} updated.",
        "success",
    )
    return_args = {"filters": "1", "q": request.form.get("q", "")}
    for field in ("season", "status", "discipline_code", "gender", "location"):
        values = [value for value in request.form.getlist(field) if value]
        if values:
            return_args[field] = values
    return redirect(url_for("sports_editorial_workspace.race_status", **return_args))


@blueprint.post("/entities/refresh/<step>")
def refresh_entities(step):
    if auth_configuration()["mode"] != "workspace":
        abort(404)
    require_supervisor()
    season_code = request.form.get("season_code", "2027")
    try:
        if step == "events":
            events, _, _ = fetch_public_calendar_feed(season_code)
            count = repository.upsert_calendar_events(events)
            return jsonify({"ok": True, "message": f"{count} events updated."})
        if step == "athletes":
            athletes, _, list_name = fetch_public_athletes()
            athlete_count = repository.upsert_athletes(athletes)
            country_count = repository.upsert_entities(countries_from_athletes(athletes))
            return jsonify({"ok": True, "message": f"{athlete_count} athletes and {country_count} countries updated from {list_name or 'the official points list'}."})
        if step == "competitions":
            _, competitions, _ = fetch_public_calendar_feed(season_code)
            count = repository.upsert_entities(competitions)
            stored = {str(item.get("canonical_id")): item for item in repository.list_entities(entity_type="competition")}
            submissions = repository.list_submissions(include_inactive=True)
            linked = _sync_submission_race_links(list(stored.values()), submissions=submissions)
            for competition in (stored.get(str(item.get("canonical_id")), item) for item in competitions):
                _sync_competition_status_to_sheets(competition, submissions=submissions)
            return jsonify({"ok": True, "message": f"{count} competitions updated and race links refreshed on {linked} stat sheets from the FIS Public API calendar feed."})
        return jsonify({"ok": False, "error": "Unknown refresh step."}), 400
    except (FisPublicApiError, SupabaseError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


def _submission_or_404(submission_id):
    submission = repository.get_submission(submission_id)
    if not submission:
        abort(404)
    return decorate_submission_race_status(submission, repository.list_entities(entity_type="competition"))


def _entities_by_id(submission=None):
    if submission is None:
        return {}
    entity_ids = [entity_id for stat in submission.get("stats", []) for entity_id in stat.get("entity_ids", [])]
    entities = repository.get_entities_by_ids(entity_ids)
    for entity in entities:
        if entity.get("entity_type") == "country" and not entity.get("canonical_url"):
            entity["canonical_url"] = fis_nation_url(
                entity.get("canonical_id") or entity.get("country_code")
            )
    return {entity["id"]: entity for entity in entities}


def _calendar_events():
    return RepositoryCalendarProvider(repository).list_events()


def _require_sub_editor():
    return require_editor()


def _require_reviewer():
    return require_reviewer()


def _is_fis_specialist(user):
    """FIS review is a shared workspace queue; its edit lock selects one editor."""
    return user.get("role") == "fis_specialist"


def _flash_fis_error(exc):
    if isinstance(exc, FisPayloadValidationError):
        for message in exc.errors:
            flash(message, "error")
        return
    flash(f"FIS request failed ({exc.status_code}): {exc}", "error")
    if exc.details.get("code"):
        flash(f"FIS error code: {exc.details['code']}.", "error")
    for path, messages in (exc.details.get("errors") or {}).items():
        for message in messages if isinstance(messages, list) else [messages]:
            flash(f"{path}: {message}", "error")
    if "currentVersion" in exc.details:
        if exc.details["currentVersion"] is None:
            flash("FIS does not currently hold this stat sheet. Retry it as a new submission without a previous version.", "error")
        else:
            flash(f"FIS currently has version {exc.details['currentVersion']}. Reload, review the latest sheet and try again.", "error")
    if exc.details.get("closesAt"):
        flash(f"The FIS submission window closed at {exc.details['closesAt']}.", "error")
    if exc.details.get("retryAfter"):
        flash(f"FIS has rate-limited requests. Try again after {exc.details['retryAfter']} seconds.", "error")


def _lock_display(lock):
    if not lock:
        return None
    result = dict(lock)
    for field in ("acquired_at", "last_active_at", "expires_at"):
        value = parse_timestamp(result.get(field))
        result[f"{field}_display"] = value.strftime("%d %b %Y, %H:%M UTC") if value else "—"
    return result


def _remember_lock(submission_id, lock):
    if not lock or lock.get("owner_id") != (current_user() or {}).get("id"):
        return
    held = dict(session.get("sports_editorial_edit_locks") or {})
    held[submission_id] = {"token": lock["token"], "version": lock["version"]}
    session["sports_editorial_edit_locks"] = held


def _forget_lock(submission_id):
    held = dict(session.get("sports_editorial_edit_locks") or {})
    held.pop(submission_id, None)
    session["sports_editorial_edit_locks"] = held


def _require_owned_lock(submission_id):
    user = current_user() or {}
    remembered = (session.get("sports_editorial_edit_locks") or {}).get(submission_id, {})
    token = request.form.get("lock_token") or remembered.get("token", "")
    version = request.form.get("lock_version") or remembered.get("version", "")
    if not token and not repository.get_edit_lock(submission_id):
        _submission, lock = repository.acquire_edit_lock(submission_id, user)
        _remember_lock(submission_id, lock)
        token, version = lock.get("token", ""), lock.get("version", "")
    if not repository.verify_edit_lock(submission_id, user.get("id"), token, version):
        abort(409, description="Your editing lock has expired or been replaced. Your changes were not saved.")
    return user, token


@blueprint.route("")
@blueprint.route("/")
def dashboard():
    user = current_user() or {}
    if user.get("role") != "supervisor":
        return redirect(url_for("sports_editorial_workspace.queue"))
    coverage_start, coverage_end, coverage_preset = resolve_coverage_range(
        request.args.get("coverage_range", "next_14_days"),
        request.args.get("coverage_start"), request.args.get("coverage_end"),
    )
    metrics = build_dashboard_metrics(
        repository.list_submissions(include_inactive=True), _assignment_users(),
        events=repository.list_entities(entity_type="event"),
        competitions=repository.list_entities(entity_type="competition"),
        coverage_start=coverage_start, coverage_end=coverage_end,
        coverage_preset=coverage_preset,
    )
    return render_template(
        "sports-editorial-workspace/dashboard.html", metrics=metrics,
        coverage_range_options=COVERAGE_RANGE_OPTIONS,
    )


@blueprint.get("/stat-insights")
def stat_insights():
    race_ids = list(dict.fromkeys(re.findall(r"\d+", request.args.get("race_ids", ""))))[:10]
    coverage = repository.list_result_competitions()
    seasons = sorted({str(item["season_code"]) for item in coverage if item.get("season_code")}, reverse=True)
    requested_season = request.args.get("season", "").strip()
    season = requested_season if requested_season in seasons else (seasons[0] if seasons else "")
    coverage_audit = build_result_coverage(
        repository.list_entities(entity_type="competition"), coverage
    )
    eligible_race_ids = set(coverage_audit["eligible_race_ids"])
    analysis_race_ids = (
        [race_id for race_id in race_ids if race_id in eligible_race_ids]
        if race_ids else [
            str(item["race_id"]) for item in coverage
            if str(item.get("season_code") or "") == season
            and str(item.get("race_id")) in eligible_race_ids
            and item.get("import_status") == "complete"
        ]
    )
    rows = repository.list_results(race_ids=analysis_race_ids) if analysis_race_ids else []
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
    gender = request.args.get("gender", "").strip().upper()
    nation = request.args.get("nation", "").strip().upper()
    category = request.args.get("category", "").strip().casefold()
    allowed_categories = {"career", "streak", "milestone", "venue", "margin", "drought", "recent_form", "nation", "age"}
    category = category if category in allowed_categories else ""
    scenario_athlete_ids = list(dict.fromkeys(re.findall(r"\d+", request.args.get("scenario_athlete_ids", ""))))[:10]
    if source == "fis_official_results":
        rows = [row for row in rows if (not season or str(row.get("season_code") or "") == season)
                and (not gender or row.get("gender") == gender) and (not nation or row.get("nation") == nation)]
    venues = sorted({row["venue"] for row in rows})
    disciplines = sorted({row["discipline"] for row in rows})
    nations = sorted({row["nation"] for row in rows if row.get("nation")})
    venue = venue if venue in venues else ""
    discipline = discipline if discipline in disciplines else ""
    selected_race_ids = set(analysis_race_ids)
    selected_imports = [item for item in coverage if str(item.get("race_id")) in selected_race_ids]
    selected_scopes = {
        item.get("coverage_scope") or result_coverage_scope(
            item.get("season_code"), partial=item.get("import_status") == "partial"
        ) for item in selected_imports
    }
    coverage_warnings = []
    if "official_top_10" in selected_scopes:
        coverage_warnings.append(
            "For these early seasons, the FIS historical result archive exposes the top 10 only. "
            "Wins, podiums and top-ten finishes are supported, but field size, starts, finish rates, "
            "non-finishers and positions below tenth are incomplete."
        )
    if "official_top_25" in selected_scopes:
        coverage_warnings.append(
            "For these historical seasons, the FIS result archive exposes the top 25 only. "
            "Field size, starts, finish rates, non-finishers and positions below 25th are incomplete."
        )
    if "unknown_partial" in selected_scopes or any(item.get("import_status") == "partial" for item in selected_imports):
        coverage_warnings.append("One or more selected competition imports have unknown or partial classification depth.")
    coverage_metadata = {
        "coverage_type": "stored_fis_classifications" if source == "fis_official_results" else "demonstration",
        # Imports are individually complete, but the catalogue does not yet prove
        # complete historical coverage for an athlete, venue or competition.
        "is_known_complete": False,
        "warnings": coverage_warnings,
    }
    return render_template("sports-editorial-workspace/stat-insights.html",
                           insights=build_stat_insights(rows, venue, discipline, athlete,
                                                       coverage=coverage_metadata,
                                                       scenario_athlete_ids=scenario_athlete_ids,
                                                       category=category),
                           venues=venues, disciplines=disciplines, seasons=seasons, nations=nations, coverage=coverage,
                           coverage_audit=coverage_audit,
                           filters={"venue": venue, "discipline": discipline, "athlete": athlete, "race_ids": ", ".join(race_ids),
                                    "season": season, "gender": gender, "nation": nation,
                                    "category": category, "scenario_athlete_ids": ", ".join(scenario_athlete_ids)},
                           result_source=source, result_failures=0)


@blueprint.post("/stat-insights/import")
def import_stat_results():
    require_supervisor()
    limit = min(max(int(request.form.get("limit", "5")) if request.form.get("limit", "5").isdigit() else 5, 1), 5)
    season = request.form.get("season", "").strip()
    requested_ids = list(dict.fromkeys(re.findall(r"\d+", request.form.get("race_ids", ""))))[:limit]
    imported = {str(item["race_id"]): item for item in repository.list_result_competitions()}
    candidates = []
    for race in repository.list_entities(entity_type="competition"):
        race_id = str(race.get("canonical_id") or "")
        metadata = race.get("metadata") or {}
        if (not race_id.isdigit() or not race.get("canonical_url") or competition_result_status(race) != "result"
                or imported.get(race_id, {}).get("import_status") == "complete"):
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
                saved += repository.save_result_import(race, race_rows)
            else:
                repository.save_result_failure(race, "No completed classification rows were returned.")
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
            {"id": "demo-fis-specialist", "full_name": "FIS Specialist Demo", "editorial_role": "fis_specialist"},
        ]
    user = current_user() or {}
    return list_workspace_users(user.get("workspace_id"))


def _fis_creation_prefill(event_id="", race_id=""):
    """Build trusted creation-form defaults from the local FIS catalogue."""
    events = repository.list_entities(entity_type="event")
    competitions = repository.list_entities(entity_type="competition")
    selected_race = next((item for item in competitions if str(item.get("canonical_id") or "") == str(race_id or "")), None)
    if selected_race:
        event_id = str((selected_race.get("metadata") or {}).get("event_id") or "")
    event = next((item for item in events if str(item.get("canonical_id") or "") == str(event_id or "")), None)
    if not event:
        return {}, None
    canonical = canonical_calendar_events([event])
    if not canonical:
        return {}, None
    calendar_event = canonical[0]
    sport = calendar_event.get("sport") or ""
    competition = calendar_event.get("competition") or ""
    event_races = [item for item in competitions if str((item.get("metadata") or {}).get("event_id") or "") == str(event_id)]
    event_races = [item for item in event_races if str((item.get("metadata") or {}).get("competition_kind") or "race").casefold() not in ("training", "qualification")]
    selected_races = [selected_race] if selected_race else event_races
    event_codes = {str((item.get("metadata") or {}).get("event_code") or "").upper() for item in selected_races}
    configured_events = creation_options()["events"].get((sport, competition), ())
    event_names = [item["value"] for item in configured_events if item.get("discipline_code") in event_codes]
    genders = []
    for item in selected_races:
        gender = str((item.get("metadata") or {}).get("gender") or "").upper()
        gender = "X" if gender == "A" else gender
        if gender in ("M", "W", "X") and gender not in genders:
            genders.append(gender)
    metadata = event.get("metadata") or {}
    race_metadata = (selected_race or {}).get("metadata") or {}
    event_date = race_metadata.get("date") or metadata.get("start_date") or ""
    location = calendar_event.get("location") or event.get("name") or ""
    event_label = " / ".join(event_names) or event.get("name") or "FIS event"
    title = " – ".join(part for part in (competition, location, event_label) if part)[:160]
    values = {
        "title": [title], "sport": [sport], "competition": [competition],
        "season_code": [str(calendar_event.get("season_code") or "")],
        "event_name": event_names, "gender": genders,
        "calendar_event_query": [location], "calendar_event_id": [str(event_id)],
        "fis_event_ids": [str(event_id)], "event_date": [format_display_date(event_date)],
        "client_name": ["FIS"],
    }
    context = {
        "event_id": str(event_id), "race_id": str(race_id or ""),
        "location": location, "race_count": len(selected_races),
        "uses_event_start_date": not selected_race and bool(event_date),
    }
    return values, context


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
    require_supervisor()
    prefill_context = None
    if request.method == "POST":
        values = request.form.to_dict(flat=False)
    else:
        values, prefill_context = _fis_creation_prefill(
            request.args.get("from_fis_event", ""), request.args.get("from_fis_race", "")
        )
    raw_calendar_events = _calendar_events()
    calendar_events = canonical_calendar_events(raw_calendar_events)
    options = creation_options()
    browser_options = {
        "sport_capabilities": {item["value"]: {"multiple_events": bool(item.get("multiple_events")), "multiple_genders": bool(item.get("multiple_genders"))} for item in options["sports"]},
        "competitions": {sport: list(items) for sport, items in options["competitions"].items()},
        "events": {f"{sport}|{competition}": list(items) for (sport, competition), items in options["events"].items()},
        "genders": {f"{sport}|{competition}": list(items) for (sport, competition), items in options["genders"].items()},
        "calendar_events": calendar_events,
    }
    if request.method == "POST":
        values["content_html"] = [sanitise_rich_text(value) for value in request.form.getlist("content_html")]
        action = request.form.get("action", "draft")
        status = "in_review" if action == "submit" else "draft"
        sport = request.form.get("sport", "").strip()
        competition = request.form.get("competition", "").strip()
        event_names = [value.strip() for value in request.form.getlist("event_name") if value.strip()]
        raw_season = request.form.get("season_code", "").strip()
        errors = []
        if not request.form.get("title", "").strip():
            errors.append("Title is required.")
        elif len(request.form.get("title", "")) > 160:
            errors.append("Title must be 160 characters or fewer.")
        genders = [value.strip().upper() for value in request.form.getlist("gender") if value.strip()]
        errors.extend(validate_choice_combination(sport, competition, event_names, genders))
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
            "competition": competition, "event_name": event_names[0] if event_names else "", "event_names": event_names,
            "gender": genders[0] if genders else "", "genders": genders, "fis_discipline_code": SPORT_CODES.get(sport),
            "fis_event_discipline_code": event_discipline_code(sport, competition, event_names),
            "fis_event_discipline_codes": list(event_discipline_codes(sport, competition, event_names)),
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
        race_matches = matching_competitions(data, repository.list_entities(entity_type="competition"))
        data["fis_race_ids"] = sorted(int(item["canonical_id"]) for item in race_matches)
        users_by_id = {item["id"]: item for item in _assignment_users()}
        researcher = users_by_id.get(data["researcher_user_id"]) if data["researcher_user_id"] else None
        sub_editor = users_by_id.get(data["sub_editor_user_id"]) if data["sub_editor_user_id"] else None
        if data["researcher_user_id"] and (not researcher or researcher.get("editorial_role") not in RESEARCH_ASSIGNMENT_ROLES):
            errors.append("Choose an active Researcher, Sub-editor or Supervisor for Researcher assignment.")
        if data["sub_editor_user_id"] and (not sub_editor or sub_editor.get("editorial_role") not in SUB_EDITOR_ASSIGNMENT_ROLES):
            errors.append("Choose an active Sub-editor or Supervisor for Sub-editor assignment.")
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
        creation_browser_options=browser_options,
        prefill_context=prefill_context,
    )


@blueprint.route("/confirmation/<submission_id>")
def confirmation(submission_id):
    return render_template("sports-editorial-workspace/confirmation.html", submission=_submission_or_404(submission_id))


@blueprint.route("/queue/modern-preview", endpoint="modern_queue_preview")
@blueprint.route("/queue")
def queue():
    queue_endpoint = request.endpoint
    clean_query_args = request.args.to_dict(flat=False)
    requested_highlight = str(request.args.get("highlight") or "").strip()
    clean_query_args.pop("highlight", None)
    queue_return_url = url_for(queue_endpoint, **clean_query_args)
    filter_fields = (
        "amp_id", "client_name", "sport", "competition", "event_name", "gender", "location",
        "season_code", "event_date", "fis_event_ids", "publication_deadline", "researcher_deadline", "status",
        "researcher_user_id", "sub_editor_user_id", "race_status", "updated_at", "last_modified_by",
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
    competition_catalogue = repository.list_entities(entity_type="competition")
    all_submissions = [decorate_submission_race_status(item, competition_catalogue) for item in repository.list_submissions()]

    def item_filter_values(item, field):
        value = item.get(field)
        if field == "fis_event_ids":
            return [str(event_id) for event_id in (value or [])]
        return [str(value or "")]

    submissions = [
        dict(item) for item in all_submissions
        if all(not values or any(value in values for value in item_filter_values(item, field)) for field, values in filters.items())
    ]
    show_race_status_column = any(item.get("race_status") == "cancelled" for item in submissions)
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
        "race_status": "Race status",
        "updated_at": "Last modified", "last_modified_by": "Last modified by",
    }
    active_filters = []
    for field in filter_fields:
        for value in filters[field]:
            if field == "status":
                display_value = STATUS_LABELS.get(value, value)
            elif field == "sport":
                display_value = SPORT_LABELS.get(value, value)
            else:
                display_value = user_names.get(value, value)
            remaining_values = [selected for selected in filters[field] if selected != value]
            remove_args = {key: list(values) for key, values in clean_query_args.items()}
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
        sort_args = {key: list(values) for key, values in clean_query_args.items()}
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
        add_args = {key: list(values) for key, values in clean_query_args.items()}
        add_args["sort"] = ",".join(f"{sort_field}:{direction}" for sort_field, direction in added)
        add_args.pop("direction", None)
        sort_add_urls[field] = url_for(queue_endpoint, **add_args)
    reset_args = {"sort": sort_value}
    reset_filters_url = url_for(queue_endpoint, **reset_args)
    clear_sort_args = {key: list(values) for key, values in clean_query_args.items()}
    clear_sort_args.pop("sort", None)
    clear_sort_args.pop("direction", None)
    clear_sort_url = url_for(queue_endpoint, **clear_sort_args)
    view_args = {key: list(values) for key, values in clean_query_args.items()}
    standard_view_url = url_for("sports_editorial_workspace.queue", **view_args)
    enhanced_view_url = url_for("sports_editorial_workspace.modern_queue_preview", **view_args)
    queue_view = "enhanced" if queue_endpoint.endswith("modern_queue_preview") else "standard"
    known_submission_ids = {item["id"] for item in all_submissions}
    recent_submission_id = requested_highlight if requested_highlight in known_submission_ids else ""
    recent_submission_visible = bool(recent_submission_id and any(item["id"] == recent_submission_id for item in submissions))
    role = (current_user() or {}).get("role", "researcher")
    for item in submissions:
        if item["status"] == "draft" or (role == "researcher" and item["status"] == "changes_requested"):
            item["queue_url"] = url_for("sports_editorial_workspace.research", submission_id=item["id"], return_to=queue_return_url)
        elif item["status"] == "fis_review" and (role == "supervisor" or _is_fis_specialist(current_user() or {})):
            item["queue_url"] = url_for("sports_editorial_workspace.detail", submission_id=item["id"], edit=1, return_to=queue_return_url)
        elif role in ("sub_editor", "supervisor") and item["status"] != "exported":
            item["queue_url"] = url_for("sports_editorial_workspace.detail", submission_id=item["id"], edit=1, return_to=queue_return_url)
        else:
            item["queue_url"] = url_for("sports_editorial_workspace.detail", submission_id=item["id"], return_to=queue_return_url)
    return render_template(
        "sports-editorial-workspace/queue-modern-preview.html" if queue_endpoint.endswith("modern_queue_preview") else "sports-editorial-workspace/queue.html",
        submissions=submissions,
        options=options,
        assignment_users=users,
        filters=filters,
        statuses=ACTIVE_STATUSES,
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
        show_race_status_column=show_race_status_column,
        queue_return_url=queue_return_url,
        recent_submission_id=recent_submission_id if recent_submission_visible else "",
        recent_submission_hidden=bool(recent_submission_id and not recent_submission_visible),
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
        "researcher_user_id": set(RESEARCH_ASSIGNMENT_ROLES),
        "sub_editor_user_id": set(SUB_EDITOR_ASSIGNMENT_ROLES),
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
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid result offset."}), 400
    limit = 10
    if len(query) < 2:
        return jsonify({"ok": True, "results": [], "has_more": False, "next_offset": 0})
    matches = repository.search_entities(query, entity_type=entity_type, limit=limit + 1, offset=offset)
    results, has_more = matches[:limit], len(matches) > limit
    def public_entity(item):
        metadata = item.get("metadata") or {}
        if item["entity_type"] != "athlete":
            athlete_active = False
        elif isinstance(metadata.get("is_active"), bool):
            athlete_active = metadata["is_active"]
        elif metadata.get("source_name") == "fis_official_results":
            athlete_active = False
        else:
            # Records created before active status was stored came from the
            # current points-list catalogue. Preserve their sponsor wording;
            # result-only historic athletes are identified by source_name.
            athlete_active = True
        canonical_url = item.get("canonical_url")
        if item["entity_type"] == "country" and not canonical_url:
            canonical_url = fis_nation_url(
                item.get("canonical_id") or item.get("country_code")
            )
        return {
            "id": item["id"], "type": item["entity_type"], "name": item["name"],
            "canonical_id": item.get("canonical_id"), "canonical_url": canonical_url,
            "country_code": item.get("country_code"), "athlete_active": athlete_active,
            "ski_sponsor": metadata.get("ski_sponsor") if athlete_active else None,
        }

    return jsonify({"ok": True, "provider": "local_pilot", "results": [
        public_entity(item) for item in results
    ], "has_more": has_more, "next_offset": offset + len(results)})


@blueprint.route("/submissions/<submission_id>", methods=["GET", "POST"])
def detail(submission_id):
    submission = _submission_or_404(submission_id)
    queue_return_url = _queue_return_url(request.values.get("return_to"))
    rejected_form = None
    rejected_dates = {}
    if request.method == "POST":
        is_autosave = request.form.get("autosave") == "1"
        user = _require_reviewer()
        if submission["status"] == "fis_review":
            if user.get("role") != "supervisor" and not _is_fis_specialist(user):
                abort(403, description="FIS Specialist or Supervisor access is required.")
        elif user.get("role") == "fis_specialist":
            abort(403, description="FIS specialists can edit only sheets awaiting FIS review.")
        if submission["status"] in ("approved", "exported"):
            abort(409, description="Use Edit to return this sheet to In Progress before making changes.")
        user, lock_token = _require_owned_lock(submission_id)
        can_edit_core = user.get("role") in ("sub_editor", "supervisor")
        if "amp_id" in request.form:
            abort(403, description="AMP ID is system controlled and cannot be changed.")
        if not can_edit_core and _attempts_core_data_change(request.form, submission):
            abort(403, description="Sub-editor or Supervisor access is required to edit core data.")
        requested_status = submission["status"] if is_autosave else request.form.get("status", submission["status"])
        # Older open tabs may still submit "approved". Approval now hands the
        # sheet directly to the shared FIS Specialist queue.
        # Client Event ID is never accepted directly from review request data.
        # Editable roles select a local catalogue record and the server resolves
        # both its canonical location and numeric identifier below.
        raw_event_ids = " ".join(str(value) for value in submission.get("fis_event_ids", []))
        event_ids = _event_ids_from_form(raw_event_ids)
        valid, message = validate_status_transition(submission["status"], requested_status)
        review_content = [
            {"content_type": kind, "content_html": request.form.get(f"edited_text_{block_id}", "")}
            for block_id, kind in zip(request.form.getlist("content_id"), request.form.getlist("content_type"))
        ]
        length_errors = validate_editorial_limits({
            "title": request.form.get("title", submission.get("title", "")),
            "sport": request.form.get("sport", submission.get("sport", "")),
            "content": review_content,
            "working_notes": request.form.get("working_notes", submission.get("working_notes", "")),
            "unused_stats": request.form.get("unused_stats", submission.get("unused_stats", "")),
        })
        if valid and length_errors:
            valid, message = False, length_errors[0]
        parsed_dates = {}
        for field_name, label in (
            ("event_date", "Race Date"),
            ("researcher_deadline", "Researcher Deadline"),
            ("publication_deadline", "Publication Deadline"),
        ):
            if can_edit_core and field_name in request.form:
                parsed_dates[field_name], error = parse_display_date(request.form.get(field_name), label)
                if error:
                    valid, message = False, error
                    break
        if valid and can_edit_core:
            assignable_users = {item["id"]: item for item in _assignment_users()}
            for field_name, allowed_roles, field_label in (
                ("researcher_user_id", RESEARCH_ASSIGNMENT_ROLES, "Researcher"),
                ("sub_editor_user_id", SUB_EDITOR_ASSIGNMENT_ROLES, "Sub-editor"),
            ):
                if field_name not in request.form or not request.form.get(field_name, "").strip():
                    continue
                assigned = assignable_users.get(request.form.get(field_name))
                if not assigned or assigned.get("editorial_role") not in allowed_roles:
                    valid, message = False, f"Choose an active user eligible for {field_label} assignment."
                    break
        if not can_edit_core and _invalid_event_id_tokens(raw_event_ids):
            valid, message = False, "FIS calendar event IDs must contain digits only, for example 123456."
        elif can_edit_core and "client_name" in request.form and request.form.get("client_name") != "FIS":
            valid, message = False, "Select a supported Client."
        elif can_edit_core:
            submitted_sport = request.form.get("sport", submission.get("sport", "")).strip()
            submitted_competition = request.form.get("competition", submission.get("competition", "")).strip()
            submitted_events = ([value.strip() for value in request.form.getlist("event_name") if value.strip()]
                                if "event_name" in request.form else (submission.get("event_names") or ([submission.get("event_name")] if submission.get("event_name") else [])))
            submitted_genders = ([value.strip().upper() for value in request.form.getlist("gender") if value.strip()]
                                 if "gender" in request.form else (submission.get("genders") or ([submission.get("gender")] if submission.get("gender") else [])))
            unchanged_legacy = (
                submitted_sport == submission.get("sport")
                and submitted_competition == submission.get("competition")
                and submitted_events == (submission.get("event_names") or ([submission.get("event_name")] if submission.get("event_name") else []))
            )
            controlled_errors = validate_choice_combination(submitted_sport, submitted_competition, submitted_events, submitted_genders)
            if controlled_errors and not unchanged_legacy:
                valid, message = False, controlled_errors[0]
        if valid and "season_code" in request.form and _season_code(request.form.get("season_code"), event_ids, parsed_dates.get("event_date", request.form.get("event_date"))) is None:
            valid, message = False, "Season must be the four-digit year in which the season ends, for example 2027."
        elif valid and can_edit_core and "calendar_event_id" in request.form:
            calendar_id = request.form.get("calendar_event_id", "").strip()
            current_ids = [str(value) for value in submission.get("fis_event_ids") or []]
            if calendar_id:
                selected_event, calendar_error = resolve_calendar_event(
                    _calendar_events(), calendar_id,
                    request.form.get("sport", submission.get("sport", "")).strip(),
                    request.form.get("competition", submission.get("competition", "")).strip(),
                    _season_code(request.form.get("season_code"), event_ids, parsed_dates.get("event_date", submission.get("event_date"))),
                )
                if calendar_error and calendar_id not in current_ids:
                    valid, message = False, calendar_error
                elif not calendar_error:
                    event_ids = [int(selected_event["canonical_id"])]
            else:
                event_ids = []
        if valid and requested_status in ("approved", "fis_review", "exported") and not event_ids:
            valid, message = False, "Select at least one FIS calendar event before approval."
        elif valid and requested_status in ("approved", "fis_review", "exported"):
            review_ids = request.form.getlist("content_id") or [block["id"] for block in submission.get("stats", [])]
            review_types = request.form.getlist("content_type") or [block.get("content_type", "stat") for block in submission.get("stats", [])]
            if any(kind in ("stat", "section", "heading") and request.form.get(f"accepted_{block_id}") != "1" for block_id, kind in zip(review_ids, review_types)):
                valid, message = False, "Accept and lock every statistic and sub-heading before approval."
            else:
                invalid_entities = _invalid_review_entity_links(request.form, submission)
                if invalid_entities:
                    valid, message = False, "Fix entity links without valid FIS IDs before approval: " + ", ".join(invalid_entities)
        if not valid:
            if is_autosave:
                return jsonify({"ok": False, "error": message}), 400
            flash(message, "error")
            rejected_form = request.form.copy()
            rejected_dates = parsed_dates
        else:
            mutable_form = request.form.copy()
            if not can_edit_core:
                for field_name in CORE_DATA_FIELDS:
                    mutable_form.pop(field_name, None)
                mutable_form["fis_event_ids"] = raw_event_ids
            else:
                mutable_form["fis_event_ids"] = " ".join(str(value) for value in event_ids)
                selected_sport = mutable_form.get("sport", submission.get("sport"))
                selected_competition = mutable_form.get("competition", submission.get("competition"))
                selected_event_names = ([value.strip() for value in mutable_form.getlist("event_name") if value.strip()]
                                        if "event_name" in mutable_form else (submission.get("event_names") or ([submission.get("event_name")] if submission.get("event_name") else [])))
                selected_genders = ([value.strip().upper() for value in mutable_form.getlist("gender") if value.strip()]
                                    if "gender" in mutable_form else (submission.get("genders") or ([submission.get("gender")] if submission.get("gender") else [])))
                mutable_form["fis_discipline_code"] = SPORT_CODES.get(selected_sport, "")
                mutable_form["event_names"] = selected_event_names
                mutable_form["genders"] = selected_genders
                mutable_form["fis_event_discipline_code"] = event_discipline_code(selected_sport, selected_competition, selected_event_names) or ""
                mutable_form["fis_event_discipline_codes"] = list(event_discipline_codes(selected_sport, selected_competition, selected_event_names))
                race_candidate = {
                    **submission, "fis_event_ids": event_ids, "fis_race_ids": [],
                    "fis_event_discipline_code": mutable_form.get("fis_event_discipline_code"),
                    "fis_event_discipline_codes": mutable_form.get("fis_event_discipline_codes"),
                    "genders": selected_genders, "gender": selected_genders[0] if selected_genders else None,
                    "event_date": parsed_dates.get("event_date", submission.get("event_date")),
                }
                race_matches = matching_competitions(race_candidate, repository.list_entities(entity_type="competition"))
                mutable_form["fis_race_ids"] = " ".join(str(value) for value in sorted(int(item["canonical_id"]) for item in race_matches))
                selected = next((item for item in canonical_calendar_events(_calendar_events()) if item["canonical_id"] in {str(value) for value in event_ids}), None)
                mutable_form["location"] = selected["location"] if selected else ""
            for field_name, parsed_value in parsed_dates.items():
                mutable_form[field_name] = parsed_value
            renewed_lock = repository.heartbeat_edit_lock(submission_id, user["id"], lock_token) if is_autosave else None
            if is_autosave and not renewed_lock:
                return jsonify({"ok": False, "error": "Your editing lock has expired or been replaced. Your changes were not saved."}), 409
            repository.update_review(submission_id, mutable_form, requested_status, preserve_status=is_autosave)
            if is_autosave:
                return jsonify({"ok": True, "saved_at": renewed_lock["last_active_at"], "lock": _lock_display(renewed_lock)})
            if requested_status in ("draft", "approved", "fis_review", "exported") or request.form.get("save_action") == "close":
                repository.release_edit_lock(submission_id, user["id"], lock_token)
                _forget_lock(submission_id)
            if requested_status == "fis_review" and submission.get("status") != "fis_review":
                repository.record_audit_event(submission_id, user, "sent_to_fis_review", {
                    "previous_status": submission.get("status"), "shared_pool": True,
                })
            workflow_messages = {
                "draft": "Stat sheet returned to In Progress for further research.",
                "approved": "Stat sheet approved. The FIS JSON is ready to review.",
                "fis_review": "Stat sheet approved and added to the FIS Specialist queue.",
                "in_review": "Stat sheet is now in sub edit.",
            }
            flash(workflow_messages.get(requested_status, "Review changes saved."), "success")
            if request.form.get("save_action") == "close" or requested_status != submission["status"]:
                return redirect(_queue_highlight_url(queue_return_url, submission_id))
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id, edit=1, return_to=queue_return_url))
    grouped_entities = {entity_type: [] for entity_type in VALID_ENTITY_TYPES}
    role = (current_user() or {}).get("role", "researcher")
    editable_role = (
        submission.get("status") == "fis_review"
        and (role == "supervisor" or _is_fis_specialist(current_user() or {}))
    ) or (submission.get("status") != "fis_review" and role in ("sub_editor", "supervisor"))
    final_state = submission["status"] in ("approved", "exported")
    wants_edit = request.args.get("edit") == "1"
    refreshed, edit_lock = repository.acquire_edit_lock(submission_id, current_user()) if editable_role and wants_edit and not final_state else (repository.get_submission(submission_id), None if final_state else repository.get_edit_lock(submission_id))
    if rejected_form is not None:
        refreshed = _review_form_preview(refreshed, rejected_form, rejected_dates)
    refreshed = decorate_submission_fis_schedule(
        refreshed,
        repository.list_entities(entity_type="event"),
        repository.list_entities(entity_type="competition"),
    )
    owns_lock = bool(edit_lock and edit_lock["owner_id"] == (current_user() or {}).get("id"))
    if owns_lock:
        _remember_lock(submission_id, edit_lock)
    entity_map = _entities_by_id(refreshed)
    calendar_events = canonical_calendar_events(_calendar_events())
    choices = creation_options()
    core_choice_options = {
        "sport_capabilities": {item["value"]: {"multiple_events": bool(item.get("multiple_events")), "multiple_genders": bool(item.get("multiple_genders"))} for item in choices["sports"]},
        "competitions": {sport: list(values) for sport, values in choices["competitions"].items()},
        "events": {f"{sport}|||{competition}": list(values) for (sport, competition), values in choices["events"].items()},
        "genders": {f"{sport}|||{competition}": list(values) for (sport, competition), values in choices["genders"].items()},
    }
    return render_template("sports-editorial-workspace/detail.html", submission=refreshed, grouped_entities=grouped_entities, entities_by_id=entity_map, render_entity_tags=render_entity_tags, statuses=ACTIVE_STATUSES, fis_publication=repository.get_fis_publication(submission_id), fis_config=fis_configuration(), calendar_events=calendar_events, assignment_users=_assignment_users(), creation_options=choices, core_choice_options=core_choice_options, can_review=editable_role and owns_lock and not final_state, can_edit_core=role in ("sub_editor", "supervisor") and owns_lock and not final_state, can_start_review=editable_role and not final_state and not edit_lock, can_edit_research=role in ("researcher", "sub_editor", "supervisor", "fis_specialist") and refreshed["status"] in ("draft", "changes_requested"), final_state=final_state, edit_lock=_lock_display(edit_lock), owns_lock=owns_lock and not final_state, lock_timeout_seconds=lock_timeout_seconds(), format_display_date=format_display_date, queue_return_url=queue_return_url, queue_highlight_url=_queue_highlight_url(queue_return_url, submission_id))


@blueprint.route("/submissions/<submission_id>/research", methods=["GET", "POST"])
def research(submission_id):
    user = current_user() or {}
    if user.get("role") not in ("researcher", "sub_editor", "supervisor", "fis_specialist"):
        abort(403, description="Editorial access is required.")
    submission = _submission_or_404(submission_id)
    queue_return_url = _queue_return_url(request.values.get("return_to"))
    if submission["status"] not in ("draft", "changes_requested"):
        abort(403, description="This stat sheet is locked while it is in sub edit or publication.")
    submission, edit_lock = repository.acquire_edit_lock(submission_id, user)
    submission = decorate_submission_fis_schedule(
        submission,
        repository.list_entities(entity_type="event"),
        repository.list_entities(entity_type="competition"),
    )
    owns_lock = bool(edit_lock and edit_lock["owner_id"] == user.get("id"))
    if owns_lock:
        _remember_lock(submission_id, edit_lock)
    if request.method == "POST":
        is_autosave = request.form.get("autosave") == "1"
        user, lock_token = _require_owned_lock(submission_id)
        action = "draft" if is_autosave else request.form.get("action", "draft")
        parsed_date, date_error = parse_display_date(
            request.form.get("event_date", format_display_date(submission.get("event_date"))),
            "Race Date",
        )
        if date_error:
            if is_autosave:
                return jsonify({"ok": False, "error": date_error}), 400
            flash(date_error, "error")
            entity_map = _entities_by_id(submission)
            return render_template("sports-editorial-workspace/research.html", submission=submission, entities_by_id=entity_map, render_entity_tags=render_entity_tags, edit_lock=_lock_display(edit_lock), owns_lock=owns_lock, lock_timeout_seconds=lock_timeout_seconds(), format_display_date=format_display_date, queue_return_url=queue_return_url, queue_highlight_url=_queue_highlight_url(queue_return_url, submission_id)), 400
        mutable_form = request.form.copy()
        mutable_form["event_date"] = parsed_date
        content = [{"content_type": kind, "content_html": sanitise_rich_text(value)} for kind, value in zip(request.form.getlist("content_type"), request.form.getlist("content_html"))]
        errors = validate_submission({"title": submission["title"], "sport": submission["sport"], "fis_event_ids": submission.get("fis_event_ids", []), "content": content, "working_notes": request.form.get("working_notes", ""), "unused_stats": request.form.get("unused_stats", "")}, submitting=action == "submit")
        if not errors:
            renewed_lock = repository.heartbeat_edit_lock(submission_id, user["id"], lock_token) if is_autosave else None
            if is_autosave and not renewed_lock:
                return jsonify({"ok": False, "error": "Your editing lock has expired or been replaced. Your changes were not saved."}), 409
            repository.update_research(submission_id, mutable_form, submit=action == "submit", preserve_status=is_autosave)
            if is_autosave:
                return jsonify({"ok": True, "saved_at": renewed_lock["last_active_at"], "lock": _lock_display(renewed_lock)})
            if action == "submit" or request.form.get("save_action") == "close":
                repository.release_edit_lock(submission_id, user["id"], lock_token)
                _forget_lock(submission_id)
            flash("Stat sheet submitted for sub edit." if action == "submit" else "Research saved.", "success")
            if request.form.get("save_action") == "close":
                return redirect(_queue_highlight_url(queue_return_url, submission_id))
            if action == "submit":
                return redirect(_queue_highlight_url(queue_return_url, submission_id))
            return redirect(url_for("sports_editorial_workspace.research", submission_id=submission_id, return_to=queue_return_url))
        if is_autosave:
            return jsonify({"ok": False, "error": errors[0], "errors": errors}), 400
        for error in errors:
            flash(error, "error")
    entity_map = _entities_by_id(submission)
    return render_template("sports-editorial-workspace/research.html", submission=submission, entities_by_id=entity_map, render_entity_tags=render_entity_tags, edit_lock=_lock_display(edit_lock), owns_lock=owns_lock, lock_timeout_seconds=lock_timeout_seconds(), format_display_date=format_display_date, queue_return_url=queue_return_url, queue_highlight_url=_queue_highlight_url(queue_return_url, submission_id))


@blueprint.post("/submissions/<submission_id>/edit-lock/heartbeat")
def edit_lock_heartbeat(submission_id):
    user = current_user() or {}
    payload = request.get_json(silent=True) or {}
    lock = repository.heartbeat_edit_lock(submission_id, user.get("id"), payload.get("lock_token"))
    if not lock:
        return jsonify({"ok": False, "error": "The editing lock has been released or replaced."}), 409
    return jsonify({"ok": True, "lock": _lock_display(lock)})


@blueprint.post("/submissions/<submission_id>/edit-lock/release")
def edit_lock_release(submission_id):
    user = current_user() or {}
    _submission_or_404(submission_id)
    payload = request.get_json(silent=True) or request.form
    token = payload.get("lock_token")
    if not token or not repository.release_edit_lock(submission_id, user.get("id"), token):
        return jsonify({"ok": False, "error": "The editing lock is no longer owned by this session."}), 409
    held = dict(session.get("sports_editorial_edit_locks") or {})
    held.pop(submission_id, None)
    session["sports_editorial_edit_locks"] = held
    return ("", 204)


@blueprint.post("/submissions/<submission_id>/force-unlock")
def force_unlock(submission_id):
    user = current_user() or {}
    if user.get("role") != "supervisor":
        abort(403, description="Supervisor access is required.")
    submission = _submission_or_404(submission_id)
    previous_lock = repository.get_edit_lock(submission_id)
    _submission, lock = repository.force_takeover_edit_lock(submission_id, user)
    if not lock or lock.get("owner_id") != user.get("id"):
        abort(409, description="The previous lock was removed, but a new editing lock could not be acquired.")
    _remember_lock(submission_id, lock)
    repository.record_audit_event(submission_id, user, "force_unlock", {
        "previous_owner_id": (previous_lock or {}).get("owner_id"),
        "previous_owner_name": (previous_lock or {}).get("owner_name"),
        "previous_status": submission.get("status"),
    })
    flash("Previous editing lock invalidated. You now hold the editing lock.", "success")
    return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id, edit=1))


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
    entity_map = _entities_by_id(submission)
    return render_template("sports-editorial-workspace/publication-preview.html", submission=submission, entities_by_id=entity_map, render_entity_links=render_entity_links, format_display_date=format_display_date)


@blueprint.post("/submissions/<submission_id>/fis-publish")
def fis_publish(submission_id):
    user = _require_reviewer()
    submission = _submission_or_404(submission_id)
    if submission["status"] != "fis_review":
        abort(403, description="Send the approved sheet to FIS review before publishing.")
    if user.get("role") != "supervisor" and not _is_fis_specialist(user):
        abort(403, description="Only an FIS Specialist or Supervisor can publish this sheet.")
    # Publishing is a write operation too. A second specialist must not publish
    # while somebody else owns the sheet's editing lock.
    _require_owned_lock(submission_id)
    if any(block.get("content_type") in ("stat", "section", "heading") and not block.get("accepted_at") for block in submission.get("stats", [])):
        abort(409, description="Accept and lock every statistic and sub-heading before publishing to FIS.")
    previous = repository.get_fis_publication(submission_id) or {}
    config = fis_configuration()
    try:
        payload = build_fis_payload(submission, _entities_by_id(submission), expected_version=previous.get("version"), organisation_uuid=config["organisation_uuid"], calendar_events=_calendar_events())
        publication = get_fis_client().publish(submission.get("fis_external_id") or f"cxms-{submission_id}", payload, previous=previous, submission=submission)
        repository.save_fis_publication(submission_id, publication)
        repository.set_submission_status(submission_id, "exported")
        repository.release_edit_lock(submission_id, force=True)
        _forget_lock(submission_id)
        repository.record_audit_event(submission_id, current_user() or {}, "published", {
            "mode": config["mode"], "version": publication.get("version"),
        })
        flash("FIS simulation completed. No data was transmitted." if config["mode"] == "mock" else "Published to FIS.", "success")
    except (FisPayloadValidationError, FisApiError) as exc:
        _flash_fis_error(exc)
    return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id))


@blueprint.post("/submissions/<submission_id>/fis-withdraw")
def fis_withdraw(submission_id):
    user = _require_reviewer()
    if user.get("role") not in ("sub_editor", "supervisor"):
        abort(403, description="Sub-editor or Supervisor access is required to withdraw a FIS handoff.")
    submission = _submission_or_404(submission_id)
    previous = repository.get_fis_publication(submission_id)
    if submission.get("status") == "fis_review" and (not previous or previous.get("status") != "published"):
        repository.administer_submission(submission_id, {"status": "in_review"})
        repository.record_audit_event(submission_id, user, "fis_review_withdrawn", {"previous_status": "fis_review"})
        flash("The FIS handoff was withdrawn and the sheet returned to In Sub Edit.", "success")
        return redirect(_queue_highlight_url(request.form.get("return_to"), submission_id))
    if not previous or previous.get("status") != "published":
        abort(409, description="This sheet is not awaiting FIS review or currently published to FIS.")
    try:
        publication = get_fis_client().withdraw(submission.get("fis_external_id") or f"cxms-{submission_id}", previous=previous)
        repository.save_fis_publication(submission_id, publication)
        repository.administer_submission(submission_id, {"status": "in_review"})
        repository.record_audit_event(submission_id, current_user() or {}, "withdrawn", {
            "mode": fis_configuration()["mode"], "previous_status": submission.get("status"),
        })
        flash("FIS simulation withdrawn." if fis_configuration()["mode"] == "mock" else "FIS sheet withdrawn.", "success")
    except FisApiError as exc:
        _flash_fis_error(exc)
    return redirect(_queue_highlight_url(request.form.get("return_to"), submission_id))


@blueprint.post("/submissions/<submission_id>/send-to-fis-review")
def send_to_fis_review(submission_id):
    user = require_editor()
    submission = _submission_or_404(submission_id)
    if submission.get("status") != "approved":
        abort(409, description="Only an Approved sheet can be sent to FIS review.")
    repository.administer_submission(submission_id, {"status": "fis_review"})
    repository.record_audit_event(submission_id, user, "sent_to_fis_review", {
        "previous_status": "approved", "shared_pool": True,
    })
    flash("Stat sheet added to the shared FIS Specialist queue.", "success")
    return redirect(_queue_highlight_url(request.form.get("return_to"), submission_id))


@blueprint.post("/submissions/<submission_id>/edit")
def edit_published(submission_id):
    _require_reviewer()
    submission = _submission_or_404(submission_id)
    publication = repository.get_fis_publication(submission_id) or {}
    if submission.get("status") not in ("approved", "exported") and publication.get("status") != "published":
        abort(409, description="Only an Approved or Published FIS stat sheet can be returned to In Progress.")
    withdrawal_performed = publication.get("status") == "published"
    if withdrawal_performed:
        try:
            withdrawn = get_fis_client().withdraw(submission.get("fis_external_id") or f"cxms-{submission_id}", previous=publication)
            repository.save_fis_publication(submission_id, withdrawn)
        except FisApiError as exc:
            _flash_fis_error(exc)
            return redirect(url_for("sports_editorial_workspace.detail", submission_id=submission_id, return_to=_queue_return_url(request.form.get("return_to"))))
    repository.set_submission_status(submission_id, "draft")
    user = current_user() or {}
    repository.record_audit_event(submission_id, user, "returned_to_in_progress", {
        "previous_status": submission.get("status"),
        "withdrawal_performed": withdrawal_performed,
    })
    flash("The sheet is now In Progress and available from All stat sheets.", "success")
    return redirect(_queue_highlight_url(request.form.get("return_to"), submission_id))


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
    _require_reviewer()
    submission = _submission_or_404(submission_id)
    if submission["status"] not in ("approved", "fis_review", "exported"):
        abort(403, description="Only approved submissions can be downloaded.")
    payload = build_pilot_export(submission, _entities_by_id(submission))
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    return send_file(BytesIO(data), mimetype="application/json", as_attachment=True, download_name=f"sports-editorial-{submission_id}.json")
