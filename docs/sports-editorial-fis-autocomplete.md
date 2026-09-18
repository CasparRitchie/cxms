# FIS entity autocomplete design

## Confirmed Public API integration

FIS provides a documented Public and Member API at `https://api.fis-ski.com`.
CXMS uses a personal API key generated in the FIS Member Section and sends it
server-side in the `X-Api-Key` header. The credential is never sent to the
browser.

The normal refresh downloads two official ZIP feeds:

- `/data-feeds/competitors` for athletes in AL, JP, CC, NK, FS and SB;
- `/data-feeds/calendar` for WC/WSC events and competitions in those sports.

The documented default rate limit is 10 requests per minute. CXMS therefore
imports local snapshots for autocomplete instead of calling FIS on every
keystroke. Consecutive event and competition refreshes share a short-lived
calendar-feed cache.

## Proposed request flow

1. The editor types two or more characters and selects an entity type.
2. The browser waits 250ms, then calls `GET /workspace/sports-editorial/entities/search`.
3. Flask checks the role, validates the query and checks a short-lived cache.
4. Flask searches the locally cached official FIS feed records.
5. The provider normalises the response into `EntityCandidate` records.
6. The UI shows name, nation, discipline/status and FIS code so editors can disambiguate.
7. Supervisor refreshes upsert local entity snapshots keyed by entity type and canonical ID.
8. The statistic stores the local entity UUID; JSON export emits the canonical FIS identifier and URL.

The current pilot endpoint uses local seeded entities and already exercises steps 1, 2, 6 and 8.

## Normalised candidate

```json
{
  "provider": "fis",
  "entity_type": "athlete",
  "canonical_id": "FIS_CODE",
  "provider_record_id": "COMPETITOR_ID",
  "name": "Camille Rast",
  "country_code": "SUI",
  "discipline": "AL",
  "gender": "W",
  "active": true,
  "canonical_url": "https://www.fis-ski.com/...",
  "metadata": {}
}
```

## Reliability and safety

- Keep API credentials in server-side environment variables only.
- Use a 250–350ms debounce and require at least two characters.
- Cache searches for 5–15 minutes and canonical records for 24 hours.
- Apply short connection/read timeouts; never block saving editorial work.
- Fall back to local entities and manual creation when FIS is unavailable.
- Escape result labels and never inject provider HTML into the page.
- Log request health and latency, not journalists' statistic text.
- Add database uniqueness on provider plus canonical ID.
- Refresh canonical metadata without overwriting editor-owned labels or historical exports.

## Environment variables

```text
FIS_PUBLIC_API_KEY=
FIS_PUBLIC_API_BASE_URL=https://api.fis-ski.com
```

These are separate from the Media Stat Sheets bearer-token settings. Equipment
sponsor is not present in the Public API athlete response or competitor feed;
the existing supervisor-controlled official-profile enrichment remains the
temporary source for the athlete's `Skis` manufacturer.
