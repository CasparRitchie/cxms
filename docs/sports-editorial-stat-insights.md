# Sports Editorial Stat Insights: implementation note

## Current request and persistence flow

`GET /workspace/sports-editorial/stat-insights` in `services/sports_editorial/views.py` reads the stored competition catalogue through `repository.list_result_competitions()`, then reads classifications through `repository.list_results()`. Season, gender and nation are applied in the route; venue, discipline and athlete text are applied by the compatible `build_stat_insights(rows, venue="", discipline="", athlete="")` service entry point. If no official rows are available, the route uses the isolated `demo_result_rows()` fixture and labels the page as demonstration data. The existing template renders filters, coverage, insight groups, totals, streaks and evidence.

`POST /workspace/sports-editorial/stat-insights/import` is restricted to workspace owners/admins in workspace-auth mode and supervisors in demo mode. It selects completed, missing competition entities, caps a run at five, calls the FIS importer sequentially, and persists an import record plus classifications through `repository.save_result_import()`.

Supabase uses `sports_editorial_result_imports` for race metadata/provenance and `sports_editorial_results` for athlete classifications. The unique keys are `(workspace_id, race_id)` and `(workspace_id, race_id, fis_code)`. The server service role is the only database role granted access; repository queries also apply workspace scoping.

## Normalised result row

The engine accepts a dictionary containing, where available:

- race: `race_id`, `date`, `season_code`, `venue`, optional `course`, `discipline`, `gender`, `competition`, `host_nation`, `source_url`, `imported_at`;
- athlete: `fis_code`, `competitor_id`, `athlete`, `nation`, `bib`, `birth_year`, optional `birth_date`;
- classification: `place`, `status`, `time` (legacy compatibility), `total_time`, `diff_time`, `fis_points`, `cup_points`.

FIS code is the primary athlete identity, with competitor ID second. Rows lacking both use an explicitly lower-confidence name-and-nation fallback; display name alone is never a stable key. Race ID is primary race identity. A fallback of date, venue, course, discipline, gender and competition is used only when necessary and is reported in coverage warnings.

## Reliability and coverage

Reliable within the supplied rows: filtered counts; starts under the documented status policy; completed races; wins, podiums, top-five and top-ten finishes; rates; stable-ID grouping; race/athlete de-duplication; chronological streaks; national podium sweeps; and margins when either a runner-up difference or compatible elapsed totals exist.

Coverage-limited: career totals, venue records, first wins/podiums, milestones, droughts, historical rankings and defending-winner findings. An individually complete race import does not prove a complete athlete career, venue history or World Cup archive. These findings must say “loaded” or “stored” unless `is_known_complete` is supplied by a future coverage authority.

Approximate: age derived from birth year. When `birth_date` is supplied, age is calculated in days on the race date; otherwise the UI and status explicitly say approximate. Host-country comparisons also depend on the stored competition nation representing the actual host.

## Calculation rules and known limitations

- DNS/non-entry is not a start and does not interrupt a streak. DNF, DNQ and DSQ count as starts and break result streaks, but are excluded from average and median finishing position. They reduce completion rate.
- A discipline streak sees only entered races inside that discipline scope. Thus an unrelated discipline cannot interrupt GS/SL scope. Streaks sort by full ISO date across season boundaries. Same-day ordering falls back to race identity and cannot infer run order without better metadata.
- Historical nationality is taken from each classification row, not from the athlete’s current profile. Country codes remain historically distinct by default. Any mapping (for example FRG to GER) must be passed deliberately and documented for that analysis; successor states are never silently merged.
- Tied places are retained. A race with multiple winners does not yield a winning-margin claim. Cancelled races should not supply classification rows; there is not yet a stored race-status field to assert this independently.
- `total_time` and `diff_time` are separate engine concepts. The legacy `time` field remains accepted; a leading `+` is treated as a difference. Malformed and negative values are ignored. Event format/course compatibility still depends on imported metadata; cross-format margin comparisons should be narrowed by competition, gender and discipline.
- Duplicate classifications are removed by race identity plus athlete identity. Conflicting duplicate rows currently keep the first supplied row; a future import audit should flag conflicts rather than silently choose one.
- Exact “all-time,” active-athlete, course-specific and upcoming-race claims are not supported by the current schema alone.

## Incremental architecture

`services/sports_editorial/stat_insights.py` remains the public compatibility façade and continues to provide `rows`, `leaders`, `streaks`, counts and legacy discovery groups. The structured implementation lives in `services/sports_editorial/insights/`:

- `models.py`: consistent serialisable insight representation and stable IDs;
- `context.py`: identity, de-duplication, status, date, age, time, evidence and coverage normalisation;
- `scoring.py`: deterministic editorial-interest score and breakdown;
- `detectors.py`: isolated career, streak, milestone, venue, margin, drought, form, nation, age and conditional detector functions;
- `engine.py`: detector orchestration, overlap suppression, category quotas and compatibility-ready results.

Detectors are pure over an `InsightContext` where practical. Structured facts are scored and de-duplicated before template wording is selected. Every visible insight includes detector/version, scope, confidence, coverage warning and reconstructable evidence.

## Fields still required

The next data iteration should add or source: exact date of birth; race cancellation/status; named course and course variant; event format and run count; complete total/difference/run times with timing precision; start lists and athlete active status; points completeness semantics; historical country-entity IDs and an explicit mapping policy; race sequence/time for same-day events; and a coverage manifest proving which seasons/competitions/venues are complete. These fields enable defensible all-time records, active previous winners, exact age scenarios, start-list scenarios and robust cross-format margin percentiles.
