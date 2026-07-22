"""Checkpointed Alpine World Cup results backfill for a single CXMS workspace.

Designed for a Heroku one-off dyno or an operator terminal. Every completed race
is committed separately, so rerunning the command resumes from missing races.
"""

import argparse
import os
import sys
from datetime import date
from time import monotonic, sleep

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sports_editorial.fis_calendar import fetch_alpine_world_cup_events
from services.sports_editorial.fis_entities import fetch_alpine_competitions
from services.sports_editorial.fis_results import FisResultError, fetch_alpine_results
from services.sports_editorial.repository import SupabaseSportsEditorialRepository
from services.sports_editorial.supabase_rest import SupabaseRestClient, SupabaseError


MIN_REQUEST_INTERVAL = 1.5


def parse_args():
    parser = argparse.ArgumentParser(description="Import completed FIS Alpine World Cup results once, then resume deltas.")
    parser.add_argument("--workspace-id", required=True, help="Sports Editorial workspace UUID")
    parser.add_argument("--season", type=int, action="append", required=True, help="FIS season code; repeat for more seasons")
    parser.add_argument("--max-races", type=int, default=250, help="Safety ceiling for this run (default 250)")
    parser.add_argument("--request-interval", type=float, default=MIN_REQUEST_INTERVAL, help="Seconds between FIS calls (minimum 1.5)")
    parser.add_argument("--skip-discovery", action="store_true", help="Use the stored competition catalogue without refreshing it")
    return parser.parse_args()


def main():
    args = parse_args()
    interval = max(args.request_interval, MIN_REQUEST_INTERVAL)
    max_races = min(max(args.max_races, 1), 1000)
    client = SupabaseRestClient(timeout=30)
    if not client.configured:
        raise SystemExit("SUPABASE_URL and the server-side Supabase service key are required.")
    repository = SupabaseSportsEditorialRepository(client, workspace_id=args.workspace_id)

    if not args.skip_discovery:
        for season in sorted(set(args.season)):
            print(f"Discovering Alpine World Cup competitions for FIS season {season}...", flush=True)
            events, _ = fetch_alpine_world_cup_events(season)
            repository.upsert_calendar_events(events)
            competitions, failures = fetch_alpine_competitions(events, request_interval=interval)
            repository.upsert_entities(competitions)
            print(f"Stored {len(competitions)} competition references; {failures} event pages failed.", flush=True)

    existing = {str(item["race_id"]) for item in repository.list_result_competitions()}
    seasons = {str(value) for value in args.season}
    today = date.today().isoformat()
    candidates = []
    for race in repository.list_entities(entity_type="competition"):
        metadata = race.get("metadata") or {}
        race_id = str(race.get("canonical_id") or "")
        race_date = str(metadata.get("date") or "")
        if (race_id.isdigit() and race_id not in existing and str(metadata.get("season_code") or "") in seasons
                and race.get("canonical_url") and race_date and race_date <= today):
            candidates.append(race)
    candidates.sort(key=lambda item: ((item.get("metadata") or {}).get("date") or "", item["canonical_id"]))
    candidates = candidates[:max_races]
    print(f"{len(candidates)} completed, missing competitions are eligible for this run.", flush=True)

    imported_races = imported_rows = failed = 0
    previous_request_at = None
    for index, race in enumerate(candidates, 1):
        if previous_request_at is not None:
            remaining = interval - (monotonic() - previous_request_at)
            if remaining > 0:
                sleep(remaining)
        previous_request_at = monotonic()
        race_id = str(race["canonical_id"])
        try:
            rows, _ = fetch_alpine_results([race], request_interval=interval)
            repository.save_result_import(race, rows)
            imported_races += 1
            imported_rows += len(rows)
            print(f"[{index}/{len(candidates)}] {race_id}: stored {len(rows)} rows", flush=True)
        except (FisResultError, SupabaseError) as exc:
            failed += 1
            print(f"[{index}/{len(candidates)}] {race_id}: skipped ({exc})", flush=True)

    print(f"Complete: {imported_races} races, {imported_rows} rows, {failed} failures.", flush=True)


if __name__ == "__main__":
    main()
