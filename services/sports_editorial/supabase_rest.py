import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupabaseError(RuntimeError):
    pass


class SupabaseRestClient:
    """Small server-only PostgREST client; the service key is never sent to the browser."""

    def __init__(self, url=None, key=None, timeout=8):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_SECRET_KEY", "")
        self.timeout = timeout

    @property
    def configured(self):
        return bool(self.url and self.key)

    def request(self, table, method="GET", query=None, payload=None, prefer=None):
        if not self.configured:
            raise SupabaseError("Supabase is not configured.")
        suffix = f"?{urlencode(query or {}, doseq=True, safe='(),.*') }" if query else ""
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(f"{self.url}/rest/v1/{table}{suffix}", data=body, method=method, headers=headers)
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else []
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise SupabaseError(f"Supabase request failed ({exc.code}): {raw[:300]}") from exc
        except (URLError, TimeoutError) as exc:
            raise SupabaseError("Supabase is currently unavailable.") from exc
