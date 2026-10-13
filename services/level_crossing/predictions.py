"""Conservative, crossing-specific shadow status hypotheses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services.level_crossing.observations import CROSSINGS


CROSSING_LOCATIONS = {
    "stockbridge-road": {"coordinates": [-0.7938, 50.8325], "mapPosition": [18, 55]},
    "basin-road": {"coordinates": [-0.780614, 50.830726], "mapPosition": [48, 58]},
    "whyke-road": {"coordinates": [-0.7659, 50.8321], "mapPosition": [81, 52]},
}

STATE_LABELS = {
    "OPEN": "Open · observed",
    "CLOSING": "Closing · observed",
    "CLOSED": "Closed · observed",
    "OPENING": "Opening · observed",
    "CLOSING_SOON": "Closing soon",
    "LIKELY_CLOSED": "Likely closed",
    "REOPENING": "May be reopening",
    "UNKNOWN": "Uncertain",
}


def _parse_timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _departure_time(service, now):
    value = service.get("actualDeparture") or service.get("expectedDeparture") or service.get("scheduledDeparture")
    if not value or str(value).lower() in {"on time", "delayed", "cancelled", "no report"}:
        value = service.get("scheduledDeparture")
    try:
        hour, minute = (int(part) for part in str(value).split(":", 1))
    except (TypeError, ValueError):
        return None
    local_now = now.astimezone(ZoneInfo("Europe/London"))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate < local_now - timedelta(hours=12):
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


class CrossingPredictor:
    def predict(self, td_snapshot=None, departure_snapshot=None, latest_reports=None, now=None):
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        predictions = {
            crossing_id: self._unknown(crossing_id, now)
            for crossing_id in CROSSINGS
        }
        self._apply_departures(predictions, departure_snapshot or {}, now)
        self._apply_td(predictions, td_snapshot or {}, now)
        self._apply_reports(predictions, latest_reports or [], now)
        return {
            "status": "ready",
            "generatedAt": now.isoformat(),
            "predictionUse": "shadow_only",
            "safety": "Never use this status to decide whether it is safe to cross.",
            "crossings": list(predictions.values()),
        }

    @staticmethod
    def _unknown(crossing_id, now):
        return {
            "id": crossing_id,
            "name": CROSSINGS[crossing_id]["name"],
            **CROSSING_LOCATIONS[crossing_id],
            "state": "UNKNOWN",
            "label": STATE_LABELS["UNKNOWN"],
            "confidence": "none",
            "source": "no_recent_evidence",
            "reason": "No sufficiently recent observation or recognised signalling event.",
            "evidenceAt": None,
            "generatedAt": now.isoformat(),
        }

    @staticmethod
    def _set(predictions, crossing_id, state, confidence, source, reason, evidence_at=None):
        prediction = predictions[crossing_id]
        confidence_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
        if confidence_rank[confidence] < confidence_rank[prediction["confidence"]]:
            return
        prediction.update({
            "state": state,
            "label": STATE_LABELS[state],
            "confidence": confidence,
            "source": source,
            "reason": reason,
            "evidenceAt": evidence_at,
        })

    def _apply_departures(self, predictions, snapshot, now):
        if snapshot.get("status") != "ready":
            return
        candidates = []
        for service in snapshot.get("departures") or []:
            if service.get("cancelled"):
                continue
            departure_at = _departure_time(service, now)
            if departure_at is None:
                continue
            seconds = (departure_at - now).total_seconds()
            if -60 <= seconds <= 180:
                candidates.append((abs(seconds), seconds, departure_at, service))
        if not candidates:
            return
        _, seconds, departure_at, service = min(candidates, key=lambda item: item[0])
        train = service.get("destination") or "Barnham-bound passenger service"
        for crossing_id in ("basin-road", "stockbridge-road"):
            state = "LIKELY_CLOSED" if seconds <= 30 else "CLOSING_SOON"
            self._set(
                predictions, crossing_id, state, "low", "chichester_departure",
                f"A passenger service towards Barnham ({train}) is due from Chichester; this is timetable evidence, not barrier telemetry.",
                departure_at.isoformat(),
            )
        self._set(
            predictions, "whyke-road", "CLOSING_SOON", "low", "chichester_departure",
            f"A passenger service towards Barnham ({train}) is due to leave Chichester and would reach Whyke Road shortly afterward.",
            departure_at.isoformat(),
        )

    def _apply_td(self, predictions, snapshot, now):
        if snapshot.get("status") != "connected":
            return
        events = list(snapshot.get("whykeShadowEvents") or snapshot.get("recentEvents") or [])
        for event in reversed(events):
            event_at = _parse_timestamp(event.get("receivedAt"))
            if event_at is None:
                continue
            age = (now - event_at).total_seconds()
            if age < 0 or age > 180:
                continue
            movement = f'{event.get("from")}>{event.get("to")}'
            timestamp = event_at.isoformat()
            if movement == "0090>0086":
                for crossing_id in CROSSINGS:
                    self._set(predictions, crossing_id, "LIKELY_CLOSED", "medium", "td_departure",
                              "TD shows a train leaving Chichester towards Barnham; the crossing sequence is in progress.", timestamp)
            elif movement == "0086>0084":
                self._set(predictions, "whyke-road", "LIKELY_CLOSED", "medium", "td_passage",
                          "A repeated TD movement indicates a train has just passed Whyke Road; reopening is not yet confirmed.", timestamp)
            elif movement == "0085>0087":
                for crossing_id in CROSSINGS:
                    self._set(predictions, crossing_id, "LIKELY_CLOSED", "medium", "td_passage",
                              "TD shows a Barnham-side train passing Whyke Road towards Chichester.", timestamp)
            elif movement == "0087>0091":
                self._set(predictions, "whyke-road", "REOPENING", "medium", "td_clearance",
                          "The train has entered Chichester; observations often show Whyke Road reopening near this movement.", timestamp)
                for crossing_id in ("basin-road", "stockbridge-road"):
                    self._set(predictions, crossing_id, "LIKELY_CLOSED", "medium", "td_arrival",
                              "A train from Barnham is arriving at Chichester, so the central crossing sequence may still be active.", timestamp)

    def _apply_reports(self, predictions, reports, now):
        for report in reports:
            crossing_id = report.get("crossingId")
            state = str(report.get("state") or "").upper()
            observed_at = _parse_timestamp(report.get("observedAt"))
            if crossing_id not in predictions or state not in {"OPEN", "CLOSING", "CLOSED", "OPENING"} or observed_at is None:
                continue
            age = (now - observed_at).total_seconds()
            if not 0 <= age <= 600:
                continue
            self._set(predictions, crossing_id, state, "high", "field_report",
                      "A recent field observation overrides the shadow model.", observed_at.isoformat())


crossing_predictor = CrossingPredictor()
