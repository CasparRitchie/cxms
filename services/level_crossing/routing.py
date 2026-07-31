"""Traffic-aware journeys for the Chichester crossing helper.

The destination catalogue is useful without external services. Live journey
times are only returned when both Mapbox and what3words are configured; this
keeps the interface from presenting hard-coded road times as live information.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from copy import deepcopy
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.level_crossing.observations import CROSSINGS


DESTINATIONS = (
    {
        "id": "bulls-head-fishbourne",
        "name": "The Bull's Head",
        "area": "Fishbourne",
        "purpose": "Pub",
        "what3words": "sage.agreement.bristle",
        "driveWhat3Words": "sage.agreement.bristle",
        "parkingWalkSeconds": 60,
        "arrivalNote": "Road leading to the car park; about a one-minute walk to the bar.",
        "wazeQuery": "The Bull's Head, Fishbourne, Chichester",
    },
    {
        "id": "waitrose-chichester",
        "name": "Waitrose",
        "area": "Chichester",
        "purpose": "Shopping",
        "what3words": "gosh.alone.milky",
        "driveWhat3Words": "gosh.alone.milky",
        "parkingWalkSeconds": 60,
        "arrivalNote": "Car-park approach; about a one-minute walk to the shop.",
        "wazeQuery": "Waitrose, Chichester",
    },
    {
        "id": "station-south",
        "name": "Chichester Station · south",
        "area": "Chichester",
        "purpose": "Station",
        "what3words": "hulk.purely.lies",
        "driveWhat3Words": "hulk.purely.lies",
        "parkingWalkSeconds": 60,
        "arrivalNote": "South car park, useful for trains arriving from Brighton and London.",
        "wazeQuery": "Chichester Station South Car Park",
    },
    {
        "id": "station-north",
        "name": "Chichester Station · north",
        "area": "Chichester",
        "purpose": "Station",
        "what3words": "decreased.newest.spicy",
        "driveWhat3Words": "decreased.newest.spicy",
        "parkingWalkSeconds": 60,
        "arrivalNote": "North car park, useful for trains arriving from the west.",
        "wazeQuery": "Chichester Station North Car Park",
    },
    {
        "id": "chichester-library",
        "name": "Chichester Library",
        "area": "Chichester",
        "purpose": "Library",
        "what3words": "gangs.hidden.veal",
        "driveWhat3Words": "gangs.hidden.veal",
        "parkingWalkSeconds": 60,
        "arrivalNote": "Nearby on-road parking; about a one-minute walk to the library.",
        "wazeQuery": "Chichester Library, Tower Street",
    },
    {
        "id": "st-anthonys-school",
        "name": "St Anthony's School",
        "area": "Chichester",
        "purpose": "School",
        "what3words": "certified.equal.club",
        "driveWhat3Words": "certified.equal.club",
        "parkingWalkSeconds": 120,
        "arrivalNote": "On-road parking; allow about two minutes to walk to the school.",
        "wazeQuery": "St Anthony's School, Chichester",
    },
    {
        "id": "the-seal-selsey",
        "name": "The Seal",
        "area": "Selsey",
        "purpose": "Pub",
        "what3words": "compliant.balance.form",
        "driveWhat3Words": "compliant.balance.form",
        "parkingWalkSeconds": 30,
        "arrivalNote": "Nearby road parking; roughly a 30-second walk to the pub.",
        "wazeQuery": "The Seal, Selsey",
    },
    {
        "id": "portland-retail-park",
        "name": "M&S Food · Portland Retail Park",
        "area": "Chichester",
        "purpose": "Shopping",
        "what3words": "tins.ally.loans",
        "driveWhat3Words": "tins.ally.loans",
        "parkingWalkSeconds": 120,
        "arrivalNote": "Retail-park car park; about a two-minute walk to M&S Food.",
        "wazeQuery": "Portland Retail Park, Chichester",
    },
    {
        "id": "sainsburys-chichester",
        "name": "Sainsbury's",
        "area": "Chichester",
        "purpose": "Shopping",
        "what3words": "hails.heap.parade",
        "driveWhat3Words": "hails.heap.parade",
        "parkingWalkSeconds": 60,
        "arrivalNote": "Car-park entrance; about a one-minute walk to Sainsbury's.",
        "wazeQuery": "Sainsbury's, Westhampnett Road, Chichester",
    },
    {
        "id": "the-range-chichester",
        "name": "The Range",
        "area": "Chichester",
        "purpose": "Shopping",
        "what3words": "hails.heap.parade",
        "driveWhat3Words": "hails.heap.parade",
        "parkingWalkSeconds": 120,
        "arrivalNote": "Shares the Sainsbury's car-park entrance; about a two-minute walk.",
        "wazeQuery": "The Range, Chichester",
    },
    {
        "id": "goodwood-motor-circuit",
        "name": "Goodwood Motor Circuit",
        "area": "Goodwood",
        "purpose": "Leisure",
        "what3words": "gain.rams.rope",
        "driveWhat3Words": "gain.rams.rope",
        "parkingWalkSeconds": 120,
        "arrivalNote": "Circuit entrance; allow about two minutes from the car park.",
        "wazeQuery": "Goodwood Motor Circuit",
    },
    {
        "id": "chichester-city-fc",
        "name": "Chichester City FC",
        "area": "Chichester",
        "purpose": "Football",
        "what3words": "supply.chimp.heat",
        "driveWhat3Words": "repair.united.handed",
        "parkingWalkSeconds": 120,
        "arrivalNote": "Routes to the nearer car park; about a two-minute walk to the ground.",
        "wazeQuery": "Chichester City Football Club",
    },
)

# Public street centroid, not a house or device location. Source: OS-derived
# open postcode/street data for Willowbed Drive (PO19 8), rounded to six places.
DEFAULT_ORIGIN = [-0.764442, 50.827568]


class RoutingUnavailable(RuntimeError):
    """A safe, user-facing routing failure."""


class RoutePlanner:
    def __init__(self, environ=None, opener=None, clock=None):
        self.environ = environ if environ is not None else os.environ
        self.opener = opener or urlopen
        self.clock = clock or time.monotonic
        self._cache = {}
        self._coordinate_cache = {}
        self._lock = threading.Lock()

    def catalogue(self):
        return {
            "originLabel": "Willowbed Drive area",
            "destinations": deepcopy(list(DESTINATIONS)),
            "routing": self.configuration(),
        }

    def configuration(self):
        missing = []
        if not self.environ.get("MAPBOX_ACCESS_TOKEN"):
            missing.append("MAPBOX_ACCESS_TOKEN")
        if not self.environ.get("WHAT3WORDS_API_KEY"):
            missing.append("WHAT3WORDS_API_KEY")
        return {
            "configured": not missing,
            "status": "ready" if not missing else "not_configured",
            "missing": missing,
        }

    def journey(self, destination_id):
        destination = next((item for item in DESTINATIONS if item["id"] == destination_id), None)
        if destination is None:
            raise KeyError(destination_id)

        config = self.configuration()
        base = {"destination": deepcopy(destination), "routing": config, "routes": [], "walking": None}
        if not config["configured"]:
            return {**base, "status": "not_configured"}

        cache_key = f"journey:{destination_id}"
        cached = self._cached(cache_key, max_age=75)
        if cached is not None:
            return cached

        try:
            result = self._build_journey(destination)
        except RoutingUnavailable as error:
            return {**base, "status": "unavailable", "message": str(error)}
        self._store(cache_key, result)
        return deepcopy(result)

    def _build_journey(self, destination):
        origin = self._origin_coordinates()
        drive_destination = self._what3words(destination["driveWhat3Words"])
        walk_destination = self._what3words(destination["what3words"])
        crossing_coordinates = {
            crossing_id: self._what3words(crossing["what3words"])
            for crossing_id, crossing in CROSSINGS.items()
        }
        driving = self._directions("mapbox/driving-traffic", origin, drive_destination, alternatives=True)
        walking = self._directions("mapbox/walking", origin, walk_destination, alternatives=False)

        routes = []
        for index, route in enumerate(driving):
            coordinates = route.get("geometry", {}).get("coordinates", [])
            steps = [step for leg in route.get("legs", []) for step in leg.get("steps", [])]
            uses_a27 = any("A27" in f"{step.get('ref', '')} {step.get('name', '')}".upper() for step in steps)
            crossed = [
                crossing_id
                for crossing_id, point in crossing_coordinates.items()
                if self._route_near_point(coordinates, point, threshold_metres=75)
            ]
            routes.append(
                {
                    "id": f"drive-{index + 1}",
                    "durationSeconds": round(float(route.get("duration", 0))),
                    "typicalDurationSeconds": round(float(route.get("duration_typical", route.get("duration", 0)))),
                    "distanceMetres": round(float(route.get("distance", 0))),
                    "crossedCrossings": crossed,
                    "usesA27": uses_a27,
                }
            )

        walking_route = walking[0] if walking else None
        return {
            "status": "ready",
            "destination": deepcopy(destination),
            "routing": self.configuration(),
            "routes": routes,
            "walking": {
                "durationSeconds": round(float(walking_route.get("duration", 0))),
                "distanceMetres": round(float(walking_route.get("distance", 0))),
            } if walking_route else None,
            "updatedAt": int(time.time()),
        }

    def _origin_coordinates(self):
        override = self.environ.get("LEVEL_CROSSING_ORIGIN_COORDINATES", "").strip()
        if override:
            try:
                longitude, latitude = (float(value.strip()) for value in override.split(",", 1))
                return [longitude, latitude]
            except (TypeError, ValueError):
                raise RoutingUnavailable("The configured journey origin is invalid.")
        return list(DEFAULT_ORIGIN)

    def _what3words(self, words):
        with self._lock:
            cached = self._coordinate_cache.get(words)
        if cached:
            return list(cached)
        data = self._request_json(
            "https://api.what3words.com/v3/convert-to-coordinates",
            {"words": words},
            headers={"X-Api-Key": self.environ["WHAT3WORDS_API_KEY"]},
        )
        coordinates = data.get("coordinates") or {}
        if "lng" not in coordinates or "lat" not in coordinates:
            raise RoutingUnavailable("One of the saved three-word locations could not be resolved.")
        result = [float(coordinates["lng"]), float(coordinates["lat"])]
        with self._lock:
            self._coordinate_cache[words] = result
        return list(result)

    def _directions(self, profile, origin, destination, alternatives):
        coordinate_text = ";".join(",".join(str(value) for value in point) for point in (origin, destination))
        data = self._request_json(
            f"https://api.mapbox.com/directions/v5/{profile}/{coordinate_text}",
            {
                "access_token": self.environ["MAPBOX_ACCESS_TOKEN"],
                "alternatives": "true" if alternatives else "false",
                "geometries": "geojson",
                "overview": "full",
                "steps": "true",
            },
        )
        routes = data.get("routes") or []
        if not routes:
            raise RoutingUnavailable("No route is currently available for this destination.")
        return routes

    def _request_json(self, url, parameters, headers=None):
        request_headers = {"User-Agent": "CXMS-Crossing/1.0", **(headers or {})}
        request = Request(f"{url}?{urlencode(parameters)}", headers=request_headers)
        try:
            response = self.opener(request, timeout=6)
            try:
                raw = response.read()
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
            return json.loads(raw.decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
            raise RoutingUnavailable("Live road information is temporarily unavailable.")

    def _cached(self, key, max_age):
        with self._lock:
            cached = self._cache.get(key)
            if not cached or self.clock() - cached[0] > max_age:
                return None
            return deepcopy(cached[1])

    def _store(self, key, value):
        with self._lock:
            self._cache[key] = (self.clock(), deepcopy(value))

    @staticmethod
    def _route_near_point(route, point, threshold_metres):
        if len(route) < 2:
            return False
        return any(
            RoutePlanner._point_segment_distance(point, route[index - 1], route[index]) <= threshold_metres
            for index in range(1, len(route))
        )

    @staticmethod
    def _point_segment_distance(point, start, end):
        latitude = math.radians(point[1])

        def project(coordinate):
            return (
                math.radians(coordinate[0] - point[0]) * math.cos(latitude) * 6_371_000,
                math.radians(coordinate[1] - point[1]) * 6_371_000,
            )

        start_x, start_y = project(start)
        end_x, end_y = project(end)
        dx, dy = end_x - start_x, end_y - start_y
        if dx == 0 and dy == 0:
            return math.hypot(start_x, start_y)
        fraction = max(0.0, min(1.0, -(start_x * dx + start_y * dy) / (dx * dx + dy * dy)))
        return math.hypot(start_x + fraction * dx, start_y + fraction * dy)


route_planner = RoutePlanner()
