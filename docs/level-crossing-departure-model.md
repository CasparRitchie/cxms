# Sprint: add departure data to the crossing model

## Outcome

Use National Rail Darwin passenger departures from Chichester as an additional,
crossing-specific shadow signal. The departure board never proves that a road
crossing is open and never replaces the Train Describer feed.

## Delivered scope

- Poll the detailed Chichester departure board and retain services whose
  subsequent calling points include Barnham (`BAA`).
- Cache requests for 30 seconds.
- Store the normalised departure-board snapshot alongside every field tap.
- Treat an imminent Barnham-bound departure as low-confidence closing evidence.
- Let recognised TD movements override timetable evidence.
- Let a fresh field observation override both.
- Return `UNKNOWN` when no recent evidence exists; silence is never `OPEN`.
- Expose a read-only `/api/level-crossing/departures` endpoint and a combined
  `/api/level-crossing/predictions` shadow endpoint.

## Configuration

The JSON LDBWS endpoint uses separate HTTP Basic credentials. Add them to
Heroku without pasting them into chat:

```bash
heroku config:set \
  NATIONAL_RAIL_LDBWS_USERNAME='your-ldbws-username' \
  NATIONAL_RAIL_LDBWS_PASSWORD='your-ldbws-password' \
  --app YOUR_CXMS_APP
```

If these variables are absent, the app remains healthy and reports the
departure source as `not_configured`.

## Evidence priority

1. Fresh field report (high confidence).
2. Recognised Chichester TD berth movement (medium confidence).
3. Imminent Darwin passenger departure towards Barnham (low confidence).
4. No recent evidence (`UNKNOWN`).

Passenger departure boards omit freight and empty-stock movements. TD data is
therefore still required before any user-facing model can be considered robust.

## Next evaluation

During new Whyke Road sessions, compare the departure time with:

- `0090 → 0086` (departure from Chichester towards Whyke Road);
- the first observed closing movement;
- `0086 → 0084` (Whyke Road passage candidate);
- observed reopening.

Estimate the distribution of departure-to-closing and departure-to-passage
lags. Do not promote the shadow model until these lags repeat across different
times of day and multi-train closures.
