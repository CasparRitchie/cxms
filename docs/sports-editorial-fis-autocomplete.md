# FIS entity autocomplete design

## Confirm before live integration

The public FIS website provides athlete search and athlete biography pages, and FIS publishes formal XML data-exchange specifications. No documented public JSON autocomplete API, authentication scheme, rate limit, or reuse licence has yet been identified. Before connecting production traffic, obtain from FIS or Andrew:

- the supported API base URL and documentation;
- authentication method and credentials;
- permitted data use, storage and attribution;
- rate limits and availability expectations;
- athlete, event and competition identifier definitions;
- rules for inactive athletes, name changes and merged records.

Do not build production autocomplete by scraping FIS HTML pages.

## Proposed request flow

1. The editor types two or more characters and selects an entity type.
2. The browser waits 250ms, then calls `GET /workspace/sports-editorial/entities/search`.
3. Flask checks the role, validates the query and checks a short-lived cache.
4. A `FisEntityProvider` searches the confirmed FIS endpoint server-side.
5. The provider normalises the response into `EntityCandidate` records.
6. The UI shows name, nation, discipline/status and FIS code so editors can disambiguate.
7. On selection, Flask upserts a local entity snapshot keyed by `(entity_type, provider, canonical_id)`.
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

## Suggested environment variables

```text
FIS_API_BASE_URL=
FIS_API_TOKEN=
FIS_API_TIMEOUT_SECONDS=3
FIS_ENTITY_CACHE_SECONDS=600
```

These variables should not be enabled until the official contract is confirmed.
