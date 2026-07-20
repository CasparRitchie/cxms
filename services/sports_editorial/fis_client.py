import json
import os
from hashlib import sha256
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class FisApiError(RuntimeError):
    def __init__(self, message, status_code=502, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def fis_configuration():
    mode = os.getenv("FIS_API_MODE", "mock").strip().lower()
    base_url = os.getenv("FIS_API_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("FIS_API_TOKEN", "").strip()
    return {
        "mode": mode if mode in ("mock", "live") else "mock",
        "base_url": base_url,
        "token": token,
        "organisation_uuid": os.getenv("FIS_ORGANISATION_UUID", "").strip() or None,
        "live_ready": bool(base_url and token),
    }


class MockFisClient:
    mode = "mock"

    def publish(self, external_id, payload, previous=None, submission=None):
        previous = previous or {}
        event_date = (submission or {}).get("event_date") or "2026-01-13"
        location = (submission or {}).get("location") or "Demo location"
        stored_payload = {key: value for key, value in payload.items() if key not in ("expectedVersion", "organisationUuid")}
        content_hash = sha256(json.dumps(stored_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if previous.get("status") == "published" and previous.get("_contentHash") == content_hash:
            return {**previous, "unchanged": True}
        version = int(previous.get("version") or 0) + 1
        return {
            **stored_payload, "externalId": external_id, "organisationUuid": "mock-organisation",
            "seasonCode": int(event_date[:4]) if event_date[:4].isdigit() else 2026,
            "events": [{"eventId": event_id, "place": location, "nationCode": "TBC", "startDate": event_date, "endDate": event_date} for event_id in payload["eventIds"]],
            "status": "published", "version": version, "unchanged": False,
            "submittedAt": datetime.now(timezone.utc).isoformat(), "createdBy": "pilot.mock@cxms.local",
            "warnings": [{"code": "MOCK_MODE", "message": "Simulated FIS response; no data was transmitted.", "path": None}],
            "_contentHash": content_hash,
        }

    def withdraw(self, external_id, previous=None):
        return {**(previous or {}), "externalId": external_id, "status": "withdrawn", "withdrawnAt": datetime.now(timezone.utc).isoformat()}


class LiveFisClient:
    mode = "live"

    def __init__(self, base_url, token, organisation_uuid=None, timeout=5):
        if not base_url or not token:
            raise FisApiError("Live FIS mode is not configured. Add the API base URL and token.", 503)
        self.base_url = base_url
        self.token = token
        self.organisation_uuid = organisation_uuid
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(f"{self.base_url}{path}", data=data, method=method, headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as exc:
            try:
                details = json.loads(exc.read())
            except (json.JSONDecodeError, UnicodeDecodeError):
                details = {}
            raise FisApiError(details.get("message", "FIS rejected the request."), exc.code, details) from exc
        except (URLError, TimeoutError) as exc:
            raise FisApiError("The FIS API is currently unavailable.", 502) from exc

    def publish(self, external_id, payload, previous=None, submission=None):
        return self._request("PUT", f"/media/stat-sheets/{quote(external_id, safe='')}", payload)

    def withdraw(self, external_id, previous=None):
        suffix = f"?organisationUuid={quote(self.organisation_uuid, safe='')}" if self.organisation_uuid else ""
        return self._request("DELETE", f"/media/stat-sheets/{quote(external_id, safe='')}{suffix}")


def get_fis_client():
    config = fis_configuration()
    if config["mode"] == "live":
        return LiveFisClient(config["base_url"], config["token"], config["organisation_uuid"])
    return MockFisClient()
