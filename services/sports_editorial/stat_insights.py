"""Read-only editorial calculations over normalised historical result rows."""

from collections import defaultdict
from statistics import mean, pstdev


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


def build_stat_insights(rows, venue="", discipline="", athlete=""):
    filtered = [row for row in rows if (not venue or row["venue"] == venue)
                and (not discipline or row["discipline"] == discipline)
                and (not athlete or athlete.casefold() in row["athlete"].casefold())]
    totals = defaultdict(lambda: {"starts": 0, "wins": 0, "podiums": 0, "best": 999})
    for row in filtered:
        item = totals[(row["athlete"], row["nation"])]
        item["starts"] += row.get("status") != "did_not_start"
        place = row.get("place")
        item["wins"] += place == 1
        item["podiums"] += isinstance(place, int) and place <= 3
        if isinstance(place, int):
            item["best"] = min(item["best"], place)
    leaders = [{"athlete": name, "nation": nation, **values} for (name, nation), values in totals.items()]
    leaders.sort(key=lambda item: (-item["wins"], -item["podiums"], -item["starts"], item["athlete"]))

    athlete_rows = defaultdict(list)
    for row in rows:
        if (not venue or row["venue"] == venue) and (not discipline or row["discipline"] == discipline) and (not athlete or athlete.casefold() in row["athlete"].casefold()):
            athlete_rows[(row["athlete"], row["nation"])].append(row)
    streaks = []
    for (name, nation), results in athlete_rows.items():
        current = best = 0
        for row in sorted(results, key=lambda item: item["date"]):
            place = row.get("place")
            current = current + 1 if isinstance(place, int) and place <= 3 else 0
            best = max(best, current)
        if best:
            streaks.append({"athlete": name, "nation": nation, "podium_streak": best})
    streaks.sort(key=lambda item: (-item["podium_streak"], item["athlete"]))
    for item in leaders:
        item["best"] = None if item["best"] == 999 else item["best"]
    discoveries = build_editorial_discoveries(filtered)
    discovery_groups = group_editorial_discoveries(discoveries)
    return {"rows": sorted(filtered, key=lambda item: item["date"], reverse=True), "leaders": leaders,
            "streaks": streaks, "race_count": len({(r["date"], r["venue"], r["discipline"]) for r in filtered}),
            "athlete_count": len(totals), "discoveries": discoveries, "discovery_groups": discovery_groups}


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
