#!/usr/bin/env python3
"""Checkpointed FIS equipment-sponsor enrichment for local athlete entities."""

import argparse
import re
import sys
from pathlib import Path
from time import monotonic, sleep

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.sports_editorial.fis_athlete_profiles import (  # noqa: E402
    FisAthleteProfileError,
    fetch_fis_athlete_profile,
)
from services.sports_editorial.repository import SupabaseSportsEditorialRepository  # noqa: E402
from services.sports_editorial.supabase_rest import SupabaseError, SupabaseRestClient  # noqa: E402


MIN_REQUEST_INTERVAL = 1.5
MAX_ATHLETES_PER_RUN = 500


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--max-athletes", type=int, default=250)
    parser.add_argument("--request-interval", type=float, default=MIN_REQUEST_INTERVAL)
    parser.add_argument("--fis-codes", default="", help="Optional comma-separated FIS athlete codes.")
    parser.add_argument("--refresh", action="store_true", help="Recheck athletes previously checked.")
    parser.add_argument("--audit-only", action="store_true", help="Report sponsor coverage without requesting FIS.")
    return parser.parse_args()


def sponsor_audit(athletes):
    numeric_athletes = [item for item in athletes if re.fullmatch(r"-?\d+", str(item.get("canonical_id") or ""))]
    eligible = [item for item in athletes if str((item.get("metadata") or {}).get("competitor_id") or "").isdigit()
                and item.get("canonical_url")]
    checked = [item for item in eligible if (item.get("metadata") or {}).get("sponsor_checked_at")]
    sponsored = [item for item in checked if (item.get("metadata") or {}).get("ski_sponsor")]
    return {"athletes": len(numeric_athletes),
            "countries_known": sum(bool(item.get("country_code")) for item in numeric_athletes),
            "countries_missing": sum(not item.get("country_code") for item in numeric_athletes),
            "eligible": len(eligible), "checked": len(checked), "sponsored": len(sponsored),
            "unpublished": len(checked) - len(sponsored), "unchecked": len(eligible) - len(checked)}


def main():
    args = parse_args()
    interval = max(args.request_interval, MIN_REQUEST_INTERVAL)
    limit = min(max(args.max_athletes, 1), MAX_ATHLETES_PER_RUN)
    repository = SupabaseSportsEditorialRepository(SupabaseRestClient(timeout=30), workspace_id=args.workspace_id)
    athletes = repository.list_entities(entity_type="athlete")
    audit = sponsor_audit(athletes)
    print(f"Athlete coverage: {audit['athletes']} FIS athletes; {audit['countries_known']} countries known, "
          f"{audit['countries_missing']} missing. Sponsor coverage: {audit['checked']}/{audit['eligible']} eligible profiles checked; "
          f"{audit['sponsored']} sponsors published, {audit['unpublished']} unpublished, "
          f"{audit['unchecked']} unchecked.", flush=True)
    if args.audit_only:
        return

    wanted = {value for value in re.findall(r"-?\d+", args.fis_codes)}
    candidates = []
    for athlete in athletes:
        metadata = athlete.get("metadata") or {}
        fis_code = str(athlete.get("canonical_id") or "")
        if (wanted and fis_code not in wanted) or (not args.refresh and metadata.get("sponsor_checked_at")):
            continue
        if str(metadata.get("competitor_id") or "").isdigit() and athlete.get("canonical_url"):
            candidates.append(athlete)
    candidates.sort(key=lambda item: (item.get("name") or "").casefold())
    candidates = candidates[:limit]
    print(f"{len(candidates)} athlete profiles are eligible for this incremental run.", flush=True)

    checked = sponsored = unpublished = failed = 0
    previous_request_at = None
    for index, athlete in enumerate(candidates, 1):
        if previous_request_at is not None:
            remaining = interval - (monotonic() - previous_request_at)
            if remaining > 0:
                sleep(remaining)
        previous_request_at = monotonic()
        try:
            enrichment = fetch_fis_athlete_profile(athlete["canonical_url"])
            updated = {**athlete, "metadata": {**(athlete.get("metadata") or {}), **enrichment}}
            repository.upsert_athletes([updated])
            checked += 1
            if enrichment["ski_sponsor"]:
                sponsored += 1
                outcome = enrichment["ski_sponsor"]
            else:
                unpublished += 1
                outcome = "no manufacturer published"
            print(f"[{index}/{len(candidates)}] {athlete['canonical_id']} {athlete['name']}: {outcome}", flush=True)
        except (FisAthleteProfileError, SupabaseError) as exc:
            failed += 1
            print(f"[{index}/{len(candidates)}] {athlete.get('canonical_id')} {athlete.get('name')}: failed ({exc})", flush=True)
    print(f"Complete: {checked} checked, {sponsored} sponsors, {unpublished} unpublished, {failed} failures.", flush=True)


if __name__ == "__main__":
    main()
