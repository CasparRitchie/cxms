"""Read-only editorial calculations over normalised historical result rows."""

from collections import defaultdict
from statistics import mean, median, pstdev

from .insights import build_engine_result


DEMO_RESULTS = [
    ("2025-01-21", "Kronplatz", "GS", "Alice Robinson", "NZL", 1),
    ("2025-01-21", "Kronplatz", "GS", "Lara Gut-Behrami", "SUI", 2),
    ("2025-01-21", "Kronplatz", "GS", "Paula Moltzan", "USA", 3),
    ("2024-01-30", "Kronplatz", "GS", "Lara Gut-Behrami", "SUI", 1),
    ("2024-01-30", "Kronplatz", "GS", "Sara Hector", "SWE", 2),
    ("2024-01-30", "Kronplatz", "GS", "Alice Robinson", "NZL", 3),
    ("2024-01-29", "Kronplatz", "GS", "Mikaela Shiffrin", "USA", 1),
    ("2024-01-29", "Kronplatz", "GS", "Lara Gut-Behrami", "SUI", 2),
    ("2024-01-29", "Kronplatz", "GS", "Federica Brignone", "ITA", 3),
    ("2023-01-25", "Kronplatz", "GS", "Mikaela Shiffrin", "USA", 1),
    ("2023-01-25", "Kronplatz", "GS", "Ragnhild Mowinckel", "NOR", 2),
    ("2023-01-25", "Kronplatz", "GS", "Sara Hector", "SWE", 3),
    ("2023-01-24", "Kronplatz", "GS", "Mikaela Shiffrin", "USA", 1),
    ("2023-01-24", "Kronplatz", "GS", "Lara Gut-Behrami", "SUI", 2),
    ("2023-01-24", "Kronplatz", "GS", "Federica Brignone", "ITA", 3),
    ("2026-01-04", "Kranjska Gora", "GS", "Camille Rast", "SUI", 1),
    ("2026-01-04", "Kranjska Gora", "GS", "Julia Scheib", "AUT", 2),
    ("2026-01-04", "Kranjska Gora", "GS", "Paula Moltzan", "USA", 3),
    ("2026-01-04", "Kranjska Gora", "GS", "Alice Robinson", "NZL", 4),
    ("2025-12-28", "Semmering", "GS", "Julia Scheib", "AUT", 1),
    ("2025-12-28", "Semmering", "GS", "Camille Rast", "SUI", 2),
    ("2025-12-28", "Semmering", "GS", "Alice Robinson", "NZL", 3),
    ("2025-12-28", "Semmering", "GS", "Mikaela Shiffrin", "USA", 5),
    ("2025-12-14", "Tremblant", "GS", "Julia Scheib", "AUT", 1),
    ("2025-12-14", "Tremblant", "GS", "Alice Robinson", "NZL", 2),
    ("2025-12-14", "Tremblant", "GS", "Lara Gut-Behrami", "SUI", 3),
    ("2025-12-14", "Tremblant", "GS", "Camille Rast", "SUI", 4),
    ("2025-12-13", "Tremblant", "GS", "Alice Robinson", "NZL", 1),
    ("2025-12-13", "Tremblant", "GS", "Julia Scheib", "AUT", 2),
    ("2025-12-13", "Tremblant", "GS", "Sara Hector", "SWE", 3),
    ("2025-12-13", "Tremblant", "GS", "Camille Rast", "SUI", 5),
]


def demo_result_rows():
    return [{"date": date, "venue": venue, "discipline": discipline, "athlete": athlete,
             "nation": nation, "place": place, "gender": "W", "competition": "World Cup"}
            for date, venue, discipline, athlete, nation, place in DEMO_RESULTS]


def build_stat_insights(rows, venue="", discipline="", athlete="", *, coverage=None,
                        scenario_athlete_ids=None, category="", country_mapping=None,
                        score_threshold=28):
    """Compatibility entry point backed by the structured detector engine."""
    filtered = [row for row in rows if (not venue or row.get("venue") == venue)
                and (not discipline or row.get("discipline") == discipline)
                and (not athlete or athlete.casefold() in str(row.get("athlete") or "").casefold())]
    result = build_engine_result(
        filtered, coverage=coverage, scenario_athlete_ids=scenario_athlete_ids,
        category=category, country_mapping=country_mapping, score_threshold=score_threshold,
    )
    context = result.pop("context")
    result.pop("profiles", None)
    result["rows"] = sorted(context.rows, key=lambda item: (item.get("date") or "", item.get("race_key") or ""), reverse=True)
    result["race_count"] = context.coverage["race_count"]
    result["athlete_count"] = len(context.by_athlete)

    # Transitional fields retained for the existing template and external callers.
    legacy = []
    category_map = {
        "recent_form": ("Emerging trend", "trend"),
        "venue": ("Venue specialist", "group"),
        "career": ("Experience group", "group"),
    }
    for item in result["structured_insights"]:
        if item["status"] == "conditional":
            continue
        label, kind = category_map.get(item["category"], ("Performance outlier", "outlier"))
        legacy.append({"label": label, "kind": kind, "score": item["editorial_score"],
                       "title": item["title"], "summary": item["summary"],
                       "evidence": item.get("coverage_warning") or "Evidence is attached to the structured lead."})
    result["discoveries"] = legacy
    result["discovery_groups"] = group_editorial_discoveries(legacy)
    result["perspective_groups"] = build_perspective_insights(filtered)
    return result


def _seconds(value):
    text = str(value or "").strip().lstrip("+")
    try:
        if ":" in text:
            minutes, seconds = text.split(":", 1)
            return int(minutes) * 60 + float(seconds)
        return float(text)
    except (TypeError, ValueError):
        return None


def _lead(label, title, summary, evidence, score=0):
    return {"label": label, "title": title, "summary": summary, "evidence": evidence,
            "score": score, "kind": "group"}


def build_perspective_insights(rows):
    """Build explainable country, time, gender, age and host-country leads."""
    groups = [
        {"label": "Country patterns", "description": "Podium concentration and complete podium sweeps by athlete nation."},
        {"label": "Time and margins", "description": "Winning margins and podium closeness where difference times are available."},
        {"label": "Women and men", "description": "Discipline-matched comparisons rather than raw comparisons across courses."},
        {"label": "Age milestones", "description": "Approximate ages derived from race year and the stored FIS birth year."},
        {"label": "Host-country effect", "description": "Whether athletes record stronger results when racing in their nation."},
    ]
    candidates = []
    podiums = [row for row in rows if isinstance(row.get("place"), int) and row["place"] <= 3]

    by_discipline = defaultdict(list)
    for row in podiums:
        by_discipline[row.get("discipline") or "Alpine"].append(row)
    for discipline, results in by_discipline.items():
        counts = defaultdict(int)
        for row in results:
            counts[row.get("nation") or ""] += 1
        if counts:
            nation, count = max(counts.items(), key=lambda item: item[1])
            share = count / len(results)
            if nation and count >= 5 and share >= .30:
                candidates.append(_lead("Country patterns", f"{nation} leads {discipline} podium representation",
                    f"{count} of {len(results)} recorded podium places ({share:.0%}) belong to {nation} athletes.",
                    "This describes the currently loaded and filtered races, not all-time dominance.", share))

    races = defaultdict(list)
    for row in podiums:
        key = row.get("race_id") or (row.get("date"), row.get("venue"), row.get("discipline"))
        races[key].append(row)
    sweeps = defaultdict(list)
    for race_rows in races.values():
        top_three = [row for row in race_rows if row.get("place") in (1, 2, 3)]
        nations = {row.get("nation") for row in top_three}
        if len(top_three) == 3 and len(nations) == 1:
            sweeps[next(iter(nations))].append(top_three[0])
    for nation, examples in sorted(sweeps.items(), key=lambda item: -len(item[1]))[:3]:
        latest = max(examples, key=lambda row: row.get("date") or "")
        candidates.append(_lead("Country patterns", f"{nation} recorded a complete podium sweep",
            f"{len(examples)} loaded race{'s' if len(examples) != 1 else ''} finished with {nation} athletes first, second and third.",
            f"Latest example: {latest.get('venue')} on {latest.get('date')} ({latest.get('discipline')}).", len(examples)))

    margins, podium_spans = [], []
    for race_rows in races.values():
        placed = {row.get("place"): row for row in race_rows}
        second, third = placed.get(2), placed.get(3)
        if not placed.get(1):
            continue
        winner_seconds = _seconds(placed[1].get("time"))
        second_seconds = _seconds((second or {}).get("time"))
        third_seconds = _seconds((third or {}).get("time"))
        margin = second_seconds - winner_seconds if winner_seconds is not None and second_seconds is not None else None
        podium_span = third_seconds - winner_seconds if winner_seconds is not None and third_seconds is not None else None
        if margin is not None and margin >= 0:
            margins.append((margin, placed[1], f"{margin:.2f}s"))
        if podium_span is not None and podium_span >= 0:
            podium_spans.append((podium_span, placed[1], f"{podium_span:.2f}s"))
    if margins:
        biggest, closest = max(margins, key=lambda item: item[0]), min(margins, key=lambda item: item[0])
        candidates.extend([
            _lead("Time and margins", "Biggest recorded winning margin", f"{biggest[1]['athlete']} won by {biggest[2]} at {biggest[1]['venue']}.",
                  f"{biggest[1]['date']} · {biggest[1]['discipline']} · {len(margins)} races had readable differences.", biggest[0]),
            _lead("Time and margins", "Closest recorded finish", f"{closest[1]['athlete']} won by {closest[2]} at {closest[1]['venue']}.",
                  f"{closest[1]['date']} · {closest[1]['discipline']} · verify ties and timing precision on FIS.", 1 / max(closest[0], .001)),
        ])
    if podium_spans:
        closest = min(podium_spans, key=lambda item: item[0])
        candidates.append(_lead("Time and margins", "Closest recorded podium", f"Only {closest[2]} separated first from third at {closest[1]['venue']}.",
            f"{closest[1]['date']} · {closest[1]['discipline']} · third-place difference to the winner.", 1 / max(closest[0], .001)))

    gender_margins = defaultdict(list)
    for margin, winner, _ in margins:
        if winner.get("gender") in ("W", "M"):
            gender_margins[(winner.get("discipline"), winner["gender"])].append(margin)
    for discipline in sorted({key[0] for key in gender_margins}):
        women, men = gender_margins[(discipline, "W")], gender_margins[(discipline, "M")]
        if len(women) >= 3 and len(men) >= 3:
            candidates.append(_lead("Women and men", f"Winning-margin comparison for {discipline}",
                f"Median winning margin: women {median(women):.2f}s; men {median(men):.2f}s.",
                f"Based on {len(women)} women’s and {len(men)} men’s races; course conditions still differ.", len(women) + len(men)))

    winners, athlete_wins = [], defaultdict(list)
    for row in rows:
        birth_year, race_year = str(row.get("birth_year") or ""), str(row.get("date") or "")[:4]
        if row.get("place") == 1 and birth_year.isdigit() and race_year.isdigit():
            item = {**row, "approx_age": int(race_year) - int(birth_year)}
            winners.append(item)
            athlete_wins[(row.get("athlete"), row.get("fis_code"))].append(item)
    if winners:
        youngest = min(winners, key=lambda row: row["approx_age"])
        oldest = max(winners, key=lambda row: row["approx_age"])
        first_wins = [min(items, key=lambda row: row.get("date") or "") for items in athlete_wins.values()]
        oldest_first = max(first_wins, key=lambda row: row["approx_age"])
        candidates.extend([
            _lead("Age milestones", "Youngest winner in the loaded races", f"{youngest['athlete']} was approximately {youngest['approx_age']} at {youngest['venue']}.",
                  f"{youngest['date']} · birth year {youngest['birth_year']}; exact age requires a full birth date.", -youngest["approx_age"]),
            _lead("Age milestones", "Oldest winner in the loaded races", f"{oldest['athlete']} was approximately {oldest['approx_age']} at {oldest['venue']}.",
                  f"{oldest['date']} · birth year {oldest['birth_year']}; exact age requires a full birth date.", oldest["approx_age"]),
            _lead("Age milestones", "Oldest first win visible in this dataset", f"{oldest_first['athlete']} was approximately {oldest_first['approx_age']} at their earliest loaded win.",
                  f"{oldest_first['date']} at {oldest_first['venue']}; earlier career wins may be outside current coverage.", oldest_first["approx_age"]),
        ])

    home_away = defaultdict(lambda: {"home_starts": 0, "home_podiums": 0, "away_starts": 0, "away_podiums": 0})
    for row in rows:
        nation, host = row.get("nation"), row.get("host_nation")
        if not nation or not host or row.get("status") == "did_not_start":
            continue
        side = "home" if nation == host else "away"
        home_away[nation][f"{side}_starts"] += 1
        home_away[nation][f"{side}_podiums"] += isinstance(row.get("place"), int) and row["place"] <= 3
    for nation, values in home_away.items():
        if values["home_starts"] >= 5 and values["away_starts"] >= 10:
            home_rate = values["home_podiums"] / values["home_starts"]
            away_rate = values["away_podiums"] / values["away_starts"]
            if abs(home_rate - away_rate) >= .05:
                direction = "higher" if home_rate > away_rate else "lower"
                candidates.append(_lead("Host-country effect", f"{nation} athletes show a {direction} home podium rate",
                    f"Home podium rate {home_rate:.0%}, compared with {away_rate:.0%} elsewhere.",
                    f"Based on {values['home_starts']} home and {values['away_starts']} away starts.", abs(home_rate - away_rate)))

    for group in groups:
        group["items"] = sorted((item for item in candidates if item["label"] == group["label"]),
                                key=lambda item: (-item["score"], item["title"]))[:4]
    return groups


def build_editorial_discoveries(rows):
    """Return explainable research leads, never publication-ready assertions."""
    by_athlete = defaultdict(list)
    for row in rows:
        by_athlete[(row["athlete"], row["nation"])].append(row)

    profiles = []
    for (athlete, nation), results in by_athlete.items():
        starts = sum(row.get("status") != "did_not_start" for row in results)
        finishes = [row["place"] for row in results if isinstance(row.get("place"), int)]
        if not starts:
            continue
        profiles.append({
            "athlete": athlete, "nation": nation, "starts": starts,
            "wins": sum(place == 1 for place in finishes),
            "podiums": sum(place <= 3 for place in finishes),
            "podium_rate": sum(place <= 3 for place in finishes) / starts,
            "average_finish": mean(finishes) if finishes else None,
            "results": results,
        })

    candidates = []
    eligible = [profile for profile in profiles if profile["starts"] >= 3]
    rates = [profile["podium_rate"] for profile in eligible]
    rate_mean = mean(rates) if rates else 0
    rate_sd = pstdev(rates) if len(rates) > 1 else 0
    for profile in eligible:
        z_score = (profile["podium_rate"] - rate_mean) / rate_sd if rate_sd else 0
        if profile["podium_rate"] >= 0.6 and (z_score >= 0.75 or profile["wins"] >= 2):
            candidates.append({
                "kind": "outlier", "label": "Performance outlier", "score": profile["podium_rate"] + max(z_score, 0) / 10,
                "title": f"{profile['athlete']} stands out for podium conversion",
                "summary": f"{profile['podiums']} podiums from {profile['starts']} recorded starts ({profile['podium_rate']:.0%}).",
                "evidence": f"Compared with a {rate_mean:.0%} average among athletes with at least three starts in this view.",
            })

        ordered = sorted((row for row in profile["results"] if isinstance(row.get("place"), int)), key=lambda row: row["date"])
        if len(ordered) >= 4:
            earlier, recent = ordered[:-2], ordered[-2:]
            improvement = mean(row["place"] for row in earlier) - mean(row["place"] for row in recent)
            if improvement >= 1.5:
                candidates.append({
                    "kind": "trend", "label": "Emerging trend", "score": improvement,
                    "title": f"{profile['athlete']} has improved in the latest results",
                    "summary": f"Average finish improved by {improvement:.1f} places across the latest two recorded races.",
                    "evidence": f"Latest two average: {mean(row['place'] for row in recent):.1f}; earlier recorded average: {mean(row['place'] for row in earlier):.1f}.",
                })

    venues = {row["venue"] for row in rows}
    for profile in profiles:
        finished = [row for row in profile["results"] if isinstance(row.get("place"), int)]
        for venue in venues:
            at_venue = [row["place"] for row in finished if row["venue"] == venue]
            elsewhere = [row["place"] for row in finished if row["venue"] != venue]
            if len(at_venue) >= 2 and len(elsewhere) >= 2:
                advantage = mean(elsewhere) - mean(at_venue)
                if advantage >= 1.5:
                    candidates.append({
                        "kind": "group", "label": "Venue specialist", "score": advantage,
                        "title": f"{profile['athlete']} may be especially strong at {venue}",
                        "summary": f"Average finish at {venue}: {mean(at_venue):.1f}, versus {mean(elsewhere):.1f} elsewhere.",
                        "evidence": f"Based on {len(at_venue)} recorded starts at this venue and {len(elsewhere)} elsewhere.",
                    })

    if profiles:
        most_starts = max(profile["starts"] for profile in profiles)
        leaders = [f"{profile['athlete']} ({profile['nation']})" for profile in profiles if profile["starts"] == most_starts]
        candidates.append({
            "kind": "group", "label": "Experience group", "score": most_starts / 10,
            "title": "Most frequently represented athletes in this dataset",
            "summary": f"{', '.join(leaders[:3])} recorded {most_starts} starts.",
            "evidence": "This measures only the races currently loaded, not all-time career starts.",
        })

    candidates.sort(key=lambda item: (-item["score"], item["title"]))
    grouped = group_editorial_discoveries(candidates)
    return [item for group in grouped for item in group["items"]]


def group_editorial_discoveries(candidates, per_group=4):
    groups = [
        {"label": "Performance outlier", "description": "Athletes whose podium conversion is unusually strong within the current comparison."},
        {"label": "Emerging trend", "description": "Recent finishes that differ materially from an athlete’s earlier results in this view."},
        {"label": "Venue specialist", "description": "Athletes performing noticeably better at one venue than across their other loaded races."},
        {"label": "Experience group", "description": "Athletes with the strongest representation in the currently loaded competition history."},
    ]
    for group in groups:
        group["items"] = [item for item in candidates if item["label"] == group["label"]][:per_group]
    return groups
