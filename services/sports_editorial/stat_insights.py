"""Read-only editorial calculations over normalised historical result rows."""

from collections import defaultdict


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
        item["starts"] += 1
        item["wins"] += row["place"] == 1
        item["podiums"] += row["place"] <= 3
        item["best"] = min(item["best"], row["place"])
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
            current = current + 1 if row["place"] <= 3 else 0
            best = max(best, current)
        if best:
            streaks.append({"athlete": name, "nation": nation, "podium_streak": best})
    streaks.sort(key=lambda item: (-item["podium_streak"], item["athlete"]))
    return {"rows": sorted(filtered, key=lambda item: item["date"], reverse=True), "leaders": leaders,
            "streaks": streaks, "race_count": len({(r["date"], r["venue"], r["discipline"]) for r in filtered}),
            "athlete_count": len(totals)}
