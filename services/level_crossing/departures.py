"""Cached National Rail departure evidence for Chichester crossing research."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LDBWS_URL = "https://realtime.nationalrail.co.uk/LDBWS/api/20220120/GetDepBoardWithDetails/CCH"


class ChichesterDepartureBoard:
    """Return passenger departures whose next route includes Barnham.

    Darwin is supporting evidence only: it excludes freight and empty-stock
    workings, so callers must never infer that a crossing is open from silence.
    """

    def __init__(self, environ=None, opener=None, cache_seconds=30):
        self.environ = environ if environ is not None else os.environ
        self.opener = opener or urlopen
        self.cache_seconds = cache_seconds
        self._cache = None
        self._cache_at = 0.0
        self._lock = threading.Lock()

    @property
    def configured(self):
        return bool(
            self.environ.get("NATIONAL_RAIL_LDBWS_USERNAME")
            and self.environ.get("NATIONAL_RAIL_LDBWS_PASSWORD")
        )

    def snapshot(self):
        if not self.configured:
            return {
                "status": "not_configured",
                "station": {"name": "Chichester", "crs": "CCH"},
                "direction": "towards Barnham",
                "modelUse": "shadow_only",
                "departures": [],
                "message": "Add separate National Rail LDBWS credentials to enable departure evidence.",
            }
        now = time.monotonic()
        with self._lock:
            if self._cache is not None and now - self._cache_at < self.cache_seconds:
                return self._cache
            try:
                result = self._request()
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
                result = {
                    "status": "unavailable",
                    "station": {"name": "Chichester", "crs": "CCH"},
                    "direction": "towards Barnham",
                    "modelUse": "shadow_only",
                    "departures": [],
                    "message": f"Departure board unavailable ({type(error).__name__}).",
                }
            self._cache = result
            self._cache_at = now
            return result

    def _request(self):
        query = urlencode({"numRows": 40, "timeOffset": -5, "timeWindow": 120})
        token = base64.b64encode(
            f'{self.environ["NATIONAL_RAIL_LDBWS_USERNAME"]}:{self.environ["NATIONAL_RAIL_LDBWS_PASSWORD"]}'.encode()
        ).decode()
        request = Request(
            f"{LDBWS_URL}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
        )
        with self.opener(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        services = payload.get("trainServices") or []
        departures = [self._normalise(service) for service in services if self._calls_at_barnham(service)]
        return {
            "status": "ready",
            "station": {"name": payload.get("locationName") or "Chichester", "crs": "CCH"},
            "direction": "towards Barnham",
            "generatedAt": payload.get("generatedAt") or datetime.now(timezone.utc).isoformat(),
            "modelUse": "shadow_only",
            "coverageWarning": "Passenger departures only; freight and empty-stock trains remain visible only in TD data.",
            "departures": departures[:12],
        }

    @staticmethod
    def _calling_points(service):
        for group in service.get("subsequentCallingPoints") or []:
            for point in group.get("callingPoint") or []:
                yield point

    @classmethod
    def _calls_at_barnham(cls, service):
        return any(str(point.get("crs") or "").upper() == "BAA" for point in cls._calling_points(service))

    @classmethod
    def _normalise(cls, service):
        destinations = [item.get("locationName") for item in service.get("destination") or [] if item.get("locationName")]
        barnham = next((point for point in cls._calling_points(service) if str(point.get("crs") or "").upper() == "BAA"), {})
        return {
            "scheduledDeparture": service.get("std"),
            "expectedDeparture": service.get("etd"),
            "actualDeparture": service.get("atd"),
            "platform": service.get("platform"),
            "destination": " / ".join(destinations) or "Eastbound service",
            "operator": service.get("operator"),
            "cancelled": bool(service.get("isCancelled")),
            "barnhamScheduled": barnham.get("st"),
            "barnhamExpected": barnham.get("et"),
        }


departure_board = ChichesterDepartureBoard()
