# Sports Editorial: FIS integration boundary

## Confirmed in this repository

- CXMS stores the editable sheet, stable AMP external ID, FIS calendar IDs,
  entity snapshots, entity references and the last publication response.
- The browser never receives an API credential. FIS access is isolated behind
  `services/sports_editorial/fis_client.py`.
- Live writes require `FIS_API_MODE=live`, a base URL and token, the deliberate
  `FIS_LIVE_PUBLISH_ENABLED=true` switch, and an allow-list of test event IDs.
- Mock mode is visibly reported as a simulation and transmits nothing.
- Publish status changes to Published only after the client returns success.
  Withdraw status changes to In Progress only after the client returns success.
- Public FIS pages and official points-list files currently seed calendar,
  athlete, country and competition reference data. They do not establish a
  supported media stat-sheet API contract.

## Required confirmation from Andrew, AMP and FIS

1. Documented create/read/replace/withdraw endpoints and payload schemas.
2. Authentication method, organisation identifier and credential ownership.
3. Whether FIS permits CXMS to call directly or requires AMP-controlled egress.
4. Test and production base URLs, network allow-listing and rate limits.
5. Conflict/version semantics and recovery procedure after partial failures.
6. Canonical definitions for Client Event ID, FIS Event ID, competition ID and
   event entity references.
7. Approved athlete sponsor/manufacturer source. The official points-list
   import supplies athlete and NOC identity but not ski sponsor.
8. Permitted storage, refresh, attribution and retention of reference data.

## Recommended architecture

```text
CXMS
  -> authenticated AMP-controlled integration/proxy
  -> authorised FIS media API
```

The proxy is a recommendation, not a confirmed dependency. It would keep FIS
credentials and any organisation/network restrictions under AMP control while
leaving CXMS responsible for editorial workflow and an auditable integration
boundary.

## Deliberately deferred

- No undocumented endpoint is implemented.
- No FIS page is scraped for a stat-sheet write operation.
- Event entity-reference behaviour is unchanged pending Andrew's rule.
- Duplicate Stat Sheet and permanent stat-sheet deletion are not implemented.
- Stored `heading` values remain readable and are rendered as `section`.
  A later migration may consolidate the two only after the publication contract
  and production data have been reviewed.
