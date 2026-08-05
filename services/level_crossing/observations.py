"""Validation and durable storage for anonymous level-crossing observations."""

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import json
import re
from statistics import median
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
BERTH_EVENT_TYPES = {"CA", "CB", "CC"}
PHASE_STATES = {
    "closing": {"CLOSING", "CLOSED"},
    "train_passed": {"TRAIN_PASSED"},
    "reopening": {"OPENING", "OPEN"},
}


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

    def calibration_analysis(self, crossing_id, limit=1000):
        """Compare watch-session gate states with nearby TD berth events.

        This is deliberately review-only. It returns aggregate signalling
        candidates and corrected state sequences, never notes, raw session
        identifiers or the full stored snapshots.
        """
        if crossing_id not in CROSSINGS:
            raise KeyError(crossing_id)
        if not self.configured:
            return self._empty_analysis(crossing_id, "not_configured")

        rows = self.client.request(
            "level_crossing_observations",
            "GET",
            query={
                "select": "crossing_id,state,observed_at,event_kind,session_id,td_snapshot",
                "crossing_id": f"eq.{crossing_id}",
                "event_kind": "eq.watch",
                "session_id": "not.is.null",
                "order": "observed_at.asc",
                "limit": str(max(1, min(int(limit), 2000))),
            },
        )
        rows = rows if isinstance(rows, list) else []
        sessions = defaultdict(list)
        for row in rows:
            if row.get("crossing_id") != crossing_id or str(row.get("event_kind", "")) != "watch":
                continue
            session_id = str(row.get("session_id") or "")
            observed_at = self._stored_timestamp(row.get("observed_at"))
            state = str(row.get("state", "")).upper()
            if not session_id or observed_at is None or state not in STATES:
                continue
            sessions[session_id].append({**row, "state": state, "_observedAt": observed_at})

        ordered_sessions = sorted(
            (sorted(values, key=lambda item: item["_observedAt"]) for values in sessions.values()),
            key=lambda values: values[0]["_observedAt"] if values else datetime.max.replace(tzinfo=timezone.utc),
        )
        candidates = {}
        session_summaries = []
        total_corrections = 0
        for session_number, raw_session in enumerate(ordered_sessions, start=1):
            effective, corrections = self._correct_watch_session(raw_session)
            total_corrections += len(corrections)
            session_key = f"session-{session_number}"
            self._collect_td_candidates(effective, session_key, candidates)
            states = [item["state"] for item in effective]
            td_linked = sum(self._snapshot_has_berth_events(item.get("td_snapshot")) for item in effective)
            duration = 0
            if len(raw_session) > 1:
                duration = round((raw_session[-1]["_observedAt"] - raw_session[0]["_observedAt"]).total_seconds())
            session_summaries.append({
                "number": session_number,
                "observationCount": len(raw_session),
                "effectiveObservationCount": len(effective),
                "sequence": states,
                "trainPasses": states.count("TRAIN_PASSED"),
                "durationSeconds": max(0, duration),
                "tdLinkedObservations": td_linked,
                "completeCycle": self._is_complete_cycle(states),
                "correctionsApplied": corrections,
            })

        ranked_candidates = self._rank_td_candidates(candidates)
        complete_sessions = sum(summary["completeCycle"] for summary in session_summaries)
        return {
            "status": "ready",
            "crossing": {"id": crossing_id, "name": CROSSINGS[crossing_id]["name"]},
            "predictionUse": "review_only",
            "sessionCount": len(session_summaries),
            "completeSessionCount": complete_sessions,
            "correctionCount": total_corrections,
            "correctionRule": "An OPEN without a preceding OPENING is treated as superseded when CLOSED or TRAIN_PASSED follows within 120 seconds of an already closed period.",
            "sessions": session_summaries,
            "candidateSignals": ranked_candidates[:20],
            "phaseHypotheses": {
                phase: self._phase_hypotheses(ranked_candidates, states)
                for phase, states in PHASE_STATES.items()
            },
            "method": "New CA/CB/CC berth events between consecutive corrected field observations; candidates must repeat across sessions before activation.",
        }

    @staticmethod
    def _stored_timestamp(value):
        try:
            return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _correct_watch_session(rows):
        effective = []
        corrections = []
        index = 0
        while index < len(rows):
            current = rows[index]
            if (
                current["state"] == "OPEN"
                and effective
                and effective[-1]["state"] in {"CLOSED", "TRAIN_PASSED"}
            ):
                contradicting_state = None
                for later in rows[index + 1:]:
                    delay = (later["_observedAt"] - current["_observedAt"]).total_seconds()
                    if delay < 0:
                        continue
                    if delay > 120 or later["state"] == "OPENING":
                        break
                    if later["state"] in {"CLOSED", "TRAIN_PASSED"}:
                        contradicting_state = later["state"]
                        break
                if contradicting_state:
                    corrections.append({
                        "kind": "superseded_tap",
                        "removedState": "OPEN",
                        "replacementState": "CLOSED_CONTINUED",
                        "followedBy": contradicting_state,
                    })
                    index += 1
                    continue
            effective.append(current)
            index += 1
        return effective, corrections

    def _collect_td_candidates(self, rows, session_key, candidates):
        previous_at = None
        seen_events = set()
        for row in rows:
            observed_at = row["_observedAt"]
            lower_bound = previous_at or observed_at - timedelta(minutes=3)
            snapshot = row.get("td_snapshot") if isinstance(row.get("td_snapshot"), dict) else {}
            for event in snapshot.get("recentEvents") or []:
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type", "")).upper()
                from_berth = str(event.get("from", "")).strip()
                to_berth = str(event.get("to", "")).strip()
                if event_type not in BERTH_EVENT_TYPES or not (from_berth or to_berth):
                    continue
                event_at = self._stored_timestamp(event.get("receivedAt"))
                if event_at is None or not (lower_bound < event_at <= observed_at + timedelta(seconds=15)):
                    continue
                event_key = (
                    event.get("messageTime"), event.get("receivedAt"), event_type,
                    from_berth, to_berth, event.get("descriptor"),
                )
                if event_key in seen_events:
                    continue
                seen_events.add(event_key)
                signature = f"{event_type}:{from_berth or '—'}>{to_berth or '—'}"
                candidate = candidates.setdefault(signature, {
                    "signature": signature,
                    "type": event_type,
                    "from": from_berth,
                    "to": to_berth,
                    "occurrences": 0,
                    "sessions": set(),
                    "states": defaultdict(int),
                    "descriptors": set(),
                    "lags": [],
                })
                candidate["occurrences"] += 1
                candidate["sessions"].add(session_key)
                candidate["states"][row["state"]] += 1
                descriptor = str(event.get("descriptor", "")).strip()
                if descriptor:
                    candidate["descriptors"].add(descriptor)
                candidate["lags"].append(max(0, round((observed_at - event_at).total_seconds())))
            previous_at = observed_at

    @staticmethod
    def _rank_td_candidates(candidates):
        ranked = []
        for candidate in candidates.values():
            session_count = len(candidate["sessions"])
            occurrence_count = candidate["occurrences"]
            ranked.append({
                "signature": candidate["signature"],
                "type": candidate["type"],
                "from": candidate["from"],
                "to": candidate["to"],
                "occurrences": occurrence_count,
                "sessionCount": session_count,
                "states": dict(sorted(candidate["states"].items())),
                "sampleDescriptors": sorted(candidate["descriptors"])[:5],
                "medianLagSeconds": round(median(candidate["lags"])) if candidate["lags"] else None,
                "repeatStrength": "strong" if session_count >= 3 else "promising" if session_count >= 2 else "single_session",
                "score": session_count * 10 + occurrence_count,
            })
        return sorted(ranked, key=lambda item: (-item["score"], item["signature"]))

    @staticmethod
    def _phase_hypotheses(ranked_candidates, phase_states):
        hypotheses = []
        for candidate in ranked_candidates:
            matches = sum(candidate["states"].get(state, 0) for state in phase_states)
            if not matches:
                continue
            hypotheses.append({
                "signature": candidate["signature"],
                "matchingObservations": matches,
                "sessionCount": candidate["sessionCount"],
                "medianLagSeconds": candidate["medianLagSeconds"],
                "evidence": candidate["repeatStrength"],
            })
        return sorted(
            hypotheses,
            key=lambda item: (-item["sessionCount"], -item["matchingObservations"], item["signature"]),
        )[:5]

    @staticmethod
    def _snapshot_has_berth_events(snapshot):
        if not isinstance(snapshot, dict):
            return False
        return any(
            isinstance(event, dict)
            and str(event.get("type", "")).upper() in BERTH_EVENT_TYPES
            and (event.get("from") or event.get("to"))
            for event in snapshot.get("recentEvents") or []
        )

    @staticmethod
    def _is_complete_cycle(states):
        try:
            closed_index = states.index("CLOSED")
            train_index = states.index("TRAIN_PASSED", closed_index + 1)
            open_index = states.index("OPEN", train_index + 1)
            return closed_index < train_index < open_index
        except ValueError:
            return False

    @staticmethod
    def _empty_analysis(crossing_id, status):
        return {
            "status": status,
            "crossing": {"id": crossing_id, "name": CROSSINGS[crossing_id]["name"]},
            "predictionUse": "review_only",
            "sessionCount": 0,
            "completeSessionCount": 0,
            "correctionCount": 0,
            "sessions": [],
            "candidateSignals": [],
            "phaseHypotheses": {phase: [] for phase in PHASE_STATES},
        }


observation_store = LevelCrossingObservationStore()
observation_rate_limiter = ObservationRateLimiter()
