"""Validation and durable storage for anonymous level-crossing observations."""

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import json
import re
import threading

from services.sports_editorial.supabase_rest import SupabaseRestClient


CROSSINGS = {
    "whyke-road": {"name": "Whyke Road", "what3words": "awake.mason.melon"},
    "basin-road": {"name": "Basin Road", "what3words": "cubs.glare.photo"},
    "stockbridge-road": {"name": "Stockbridge Road", "what3words": "placed.bless.dance"},
}
STATES = {"OPEN", "CLOSING", "CLOSED", "OPENING", "TRAIN_PASSED"}
EVENT_KINDS = {"quick", "watch"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


class ObservationValidationError(ValueError):
    pass


def _parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ObservationValidationError("Observation time is required.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ObservationValidationError("Observation time is invalid.") from error
    if parsed.tzinfo is None:
        raise ObservationValidationError("Observation time must include a timezone.")
    parsed = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if parsed > now + timedelta(minutes=5) or parsed < now - timedelta(days=30):
        raise ObservationValidationError("Observation time is outside the accepted range.")
    return parsed.isoformat()


def _safe_json_object(value, label, max_length=5000):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ObservationValidationError(f"{label} must be an object.")
    encoded = json.dumps(value, separators=(",", ":"))
    if len(encoded) > max_length:
        raise ObservationValidationError(f"{label} is too large.")
    return json.loads(encoded)


class ObservationRateLimiter:
    """Small process-local guard against accidental or automated public endpoint spam."""

    def __init__(self, limit=60, window_seconds=300):
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self._events = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key, now=None):
        now = now or datetime.now(timezone.utc)
        with self._lock:
            events = self._events[str(key or "unknown")]
            cutoff = now - self.window
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


class LevelCrossingObservationStore:
    def __init__(self, client=None):
        self.client = client or SupabaseRestClient()

    @property
    def configured(self):
        return self.client.configured

    def build_row(self, payload, td_snapshot):
        if not isinstance(payload, dict):
            raise ObservationValidationError("A JSON observation is required.")

        observation_id = str(payload.get("id", "")).strip()
        session_id = str(payload.get("sessionId", "")).strip()
        crossing_id = str(payload.get("crossingId", "")).strip()
        state = str(payload.get("state", "")).strip().upper()
        event_kind = str(payload.get("eventKind", "quick")).strip().lower()
        note = str(payload.get("note", "")).strip()

        if not IDENTIFIER.fullmatch(observation_id):
            raise ObservationValidationError("Observation identifier is invalid.")
        if session_id and not IDENTIFIER.fullmatch(session_id):
            raise ObservationValidationError("Watch-session identifier is invalid.")
        if crossing_id not in CROSSINGS:
            raise ObservationValidationError("Crossing is not recognised.")
        if state not in STATES:
            raise ObservationValidationError("Barrier state is not recognised.")
        if event_kind not in EVENT_KINDS:
            raise ObservationValidationError("Observation type is not recognised.")
        if len(note) > 300:
            raise ObservationValidationError("Observation note is too long.")

        snapshot = td_snapshot if isinstance(td_snapshot, dict) else {}
        safe_snapshot = {
            "area": snapshot.get("area"),
            "status": snapshot.get("status"),
            "lastMessageAt": snapshot.get("lastMessageAt"),
            "messageCount": snapshot.get("messageCount", 0),
            "recentEvents": list(snapshot.get("recentEvents") or [])[:12],
            "activeBerths": dict(snapshot.get("activeBerths") or {}),
        }

        return {
            "id": observation_id,
            "crossing_id": crossing_id,
            "crossing_name": CROSSINGS[crossing_id]["name"],
            "what3words": CROSSINGS[crossing_id]["what3words"],
            "state": state,
            "event_kind": event_kind,
            "observed_at": _parse_timestamp(payload.get("observedAt")),
            "session_id": session_id or None,
            "note": note or None,
            "client_prediction": _safe_json_object(payload.get("prediction"), "Prediction"),
            "td_snapshot": _safe_json_object(safe_snapshot, "TD snapshot", max_length=20000),
        }

    def save(self, payload, td_snapshot):
        row = self.build_row(payload, td_snapshot)
        result = self.client.request(
            "level_crossing_observations",
            "POST",
            payload=row,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return result[0] if isinstance(result, list) and result else row

    def calibration_summary(self, now=None, limit=1000):
        """Return anonymous evidence totals and fresh gate reports.

        Notes, session identifiers and raw TD snapshots are never returned to
        the browser. The summary is diagnostic only; it does not claim that a
        predictive model is already trained.
        """
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        summaries = {
            crossing_id: {
                "id": crossing_id,
                "name": crossing["name"],
                "total": 0,
                "byState": {state: 0 for state in sorted(STATES)},
                "tdLinked": 0,
                "watchSessions": 0,
                "latestObservedAt": None,
                "calibrationState": "collecting",
            }
            for crossing_id, crossing in CROSSINGS.items()
        }
        if not self.configured:
            return {
                "status": "not_configured",
                "totalObservations": 0,
                "predictionUse": "not_active",
                "crossings": list(summaries.values()),
                "latestReports": [],
            }

        rows = self.client.request(
            "level_crossing_observations",
            "GET",
            query={
                "select": "crossing_id,state,observed_at,event_kind,session_id,td_snapshot",
                "order": "observed_at.desc",
                "limit": str(max(1, min(int(limit), 2000))),
            },
        )
        rows = rows if isinstance(rows, list) else []
        sessions = defaultdict(set)
        latest_reports = []
        latest_crossings = set()
        for row in rows:
            crossing_id = row.get("crossing_id")
            state = str(row.get("state", "")).upper()
            summary = summaries.get(crossing_id)
            if not summary or state not in STATES:
                continue
            try:
                observed_at = datetime.fromisoformat(str(row.get("observed_at", "")).replace("Z", "+00:00")).astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            summary["total"] += 1
            summary["byState"][state] += 1
            if summary["latestObservedAt"] is None:
                summary["latestObservedAt"] = observed_at.isoformat()
            snapshot = row.get("td_snapshot") if isinstance(row.get("td_snapshot"), dict) else {}
            if snapshot.get("status") == "connected" and snapshot.get("recentEvents"):
                summary["tdLinked"] += 1
            session_id = str(row.get("session_id") or "")
            if session_id:
                sessions[crossing_id].add(session_id)
            age_seconds = (now - observed_at).total_seconds()
            if crossing_id not in latest_crossings and 0 <= age_seconds <= 10 * 60 and state != "TRAIN_PASSED":
                latest_reports.append({
                    "crossingId": crossing_id,
                    "state": state,
                    "observedAt": observed_at.isoformat(),
                    "eventKind": str(row.get("event_kind") or "quick"),
                })
                latest_crossings.add(crossing_id)

        for crossing_id, summary in summaries.items():
            summary["watchSessions"] = len(sessions[crossing_id])
            states = summary["byState"]
            if summary["watchSessions"] >= 3 and states["CLOSED"] and states["OPEN"] and states["TRAIN_PASSED"]:
                summary["calibrationState"] = "ready_to_review"
            elif summary["total"] >= 5 and summary["tdLinked"] >= 3:
                summary["calibrationState"] = "early_evidence"

        return {
            "status": "ready",
            "totalObservations": sum(summary["total"] for summary in summaries.values()),
            "predictionUse": "not_active",
            "crossings": list(summaries.values()),
            "latestReports": latest_reports,
        }


observation_store = LevelCrossingObservationStore()
observation_rate_limiter = ObservationRateLimiter()
