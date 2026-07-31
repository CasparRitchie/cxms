"""Independent detector families for structured Alpine skiing insights."""

from collections import Counter, defaultdict
from datetime import date
from statistics import mean, median, pstdev

from .context import NON_START_STATUSES, age_at, evidence_row, seconds, winning_margin
from .models import Insight


START_MILESTONES = (10, 25, 50, 75, 100, 150, 200)
WIN_MILESTONES = (5, 10, 20, 25, 50, 100)
PODIUM_MILESTONES = (10, 20, 25, 50, 100)
WINDOWS = (3, 5, 10)
DETECTOR_VERSION = "1.0"


def _subject(rows, athlete_id=None):
    row = rows[-1] if rows else {}
    return athlete_id or row.get("athlete_id") or "dataset", row.get("athlete") or "Loaded field"


def _insight(ctx, insight_type, category, title, summary, metric, rows, *,
             status=None, subject_type="athlete", subject_id=None,
             subject_name=None, comparison=None, condition=None, confidence=1.0,
             detector="", scope=None, calculated=None):
    evidence = [evidence_row(row, **(calculated or {})) for row in rows]
    resolved_id, resolved_name = _subject(rows, subject_id)
    return Insight(
        insight_type=insight_type, category=category,
        status=status or ("confirmed" if ctx.coverage["is_known_complete"] else "coverage_limited"),
        subject_type=subject_type, subject_id=resolved_id,
        subject_name=subject_name or resolved_name, title=title, summary=summary,
        scope=scope or ctx.scope(rows), metric=metric, comparison=comparison,
        condition=condition, confidence=confidence,
        coverage_warning=ctx.coverage_warning(), evidence=evidence,
        data_as_of=ctx.data_as_of, detector=detector,
        detector_version=DETECTOR_VERSION,
    )


def career_totals(ctx):
    """Return extended athlete profiles plus a small number of notable facts."""
    profiles, insights = [], []
    for athlete_id, rows in ctx.by_athlete.items():
        starts_rows = [row for row in rows if ctx.is_start(row)]
        finishes = [row for row in rows if ctx.is_finish(row)]
        places = [row["place"] for row in finishes]
        wins = [row for row in finishes if row["place"] == 1]
        podiums = [row for row in finishes if row["place"] <= 3]
        points = [row for row in rows if row.get("cup_points") is not None or row.get("fis_points") is not None]
        by_discipline, by_venue = defaultdict(Counter), defaultdict(Counter)
        for row in starts_rows:
            for bucket, key in ((by_discipline, row.get("discipline") or "AL"), (by_venue, row.get("venue") or "Unknown")):
                bucket[key]["starts"] += 1
                bucket[key]["completed"] += ctx.is_finish(row)
                bucket[key]["wins"] += row.get("place") == 1
                bucket[key]["podiums"] += isinstance(row.get("place"), int) and row["place"] <= 3
        profile = {
            "athlete_id": athlete_id, "fis_code": str(rows[-1].get("fis_code") or ""),
            "athlete": rows[-1].get("athlete"), "nation": rows[-1].get("nation"),
            "starts": len(starts_rows), "completed": len(finishes), "wins": len(wins),
            "podiums": len(podiums), "top_fives": sum(place <= 5 for place in places),
            "top_tens": sum(place <= 10 for place in places), "points_finishes": len(points),
            "finish_rate": len(finishes) / len(starts_rows) if starts_rows else 0,
            "win_rate": len(wins) / len(starts_rows) if starts_rows else 0,
            "podium_rate": len(podiums) / len(starts_rows) if starts_rows else 0,
            "best": min(places) if places else None,
            "disciplines": {key: dict(value) for key, value in by_discipline.items()},
            "venues": {key: dict(value) for key, value in by_venue.items()},
            "rows": rows,
        }
        profiles.append(profile)
    profiles.sort(key=lambda item: (-item["wins"], -item["podiums"], -item["starts"], item["athlete"] or ""))
    if profiles:
        leader = profiles[0]
        insights.append(_insight(
            ctx, "loaded_career_leader", "career",
            f"{leader['athlete']} leads the loaded career totals",
            f"{leader['wins']} wins and {leader['podiums']} podiums from {leader['starts']} starts in the current data.",
            {"name": "wins", "value": leader["wins"], "unit": "wins"}, leader["rows"],
            subject_id=leader["athlete_id"], detector="career.totals",
            comparison={"type": "loaded_field_ranking", "rank": 1},
            confidence=.8 if leader["athlete_id"].startswith("legacy:") else 1.0,
        ))
    return profiles, insights


def _streak_summary(rows, predicate):
    best = current = previous = 0
    best_rows, running = [], []
    entered = [row for row in rows if row.get("status") not in NON_START_STATUSES]
    for row in entered:
        if predicate(row):
            current += 1
            running.append(row)
            if current > best:
                best, best_rows = current, list(running)
        else:
            previous = current
            current, running = 0, []
    ended_last = bool(entered and not predicate(entered[-1]) and previous)
    current_rows = running if current else []
    return {"current": current, "longest": best, "best_rows": best_rows,
            "current_rows": current_rows, "ended_last_race": ended_last,
            "ended_length": previous if ended_last else 0}


def streaks(ctx):
    insights, table = [], []
    definitions = (
        ("podium", lambda row: isinstance(row.get("place"), int) and row["place"] <= 3, 2),
        ("win", lambda row: row.get("place") == 1, 2),
        ("top_five", lambda row: isinstance(row.get("place"), int) and row["place"] <= 5, 3),
        ("top_ten", lambda row: isinstance(row.get("place"), int) and row["place"] <= 10, 3),
    )
    available_disciplines = sorted({row.get("discipline") for row in ctx.rows if row.get("discipline")})
    scopes = [("selected scope", None)]
    scopes.extend((discipline, {discipline}) for discipline in available_disciplines if len(available_disciplines) > 1)
    if {"GS", "SL"}.issubset(available_disciplines):
        scopes.append(("GS and SL", {"GS", "SL"}))
    for athlete_id, all_rows in ctx.by_athlete.items():
        for scope_label, allowed_disciplines in scopes:
            rows = [row for row in all_rows if not allowed_disciplines or row.get("discipline") in allowed_disciplines]
            if not rows:
                continue
            athlete, nation = rows[-1].get("athlete"), rows[-1].get("nation")
            summaries = {}
            for label, predicate, minimum in definitions:
                result = _streak_summary(rows, predicate)
                summaries[label] = result
                notable = result["current"] or result["ended_length"]
                if notable < minimum:
                    continue
                current = result["current"] > 0
                value = result["current"] if current else result["ended_length"]
                tied = current and value == result["longest"] and value > 0
                wording = label.replace("_", "-")
                if current:
                    detail = " and ties the athlete’s longest loaded sequence" if tied else ""
                    title = f"{athlete} has a current {value}-race {wording} streak"
                    summary = f"The sequence reaches the most recent entered race in {scope_label}{detail}. Races outside this discipline scope do not interrupt it."
                    insight_type = f"current_{label}_streak"
                    evidence = result["current_rows"]
                else:
                    title = f"{athlete}’s {value}-race {wording} streak ended last race"
                    summary = f"The preceding entered races in {scope_label} met the {wording} condition before the latest result ended the sequence."
                    insight_type = f"ended_{label}_streak"
                    evidence = result["best_rows"][-value:]
                insights.append(_insight(
                    ctx, insight_type, "streak", title, summary,
                    {"name": f"consecutive_{label}s", "value": value, "unit": "entered races"}, evidence,
                    subject_id=athlete_id, detector="streaks.sequence",
                    comparison={"type": "athlete_loaded_best", "previous_value": result["longest"], "tied_best": tied},
                    confidence=.8 if athlete_id.startswith("legacy:") else 1.0,
                    scope=ctx.scope(rows),
                ))
                if result["longest"] >= minimum and result["longest"] != value:
                    insights.append(_insight(
                        ctx, f"longest_loaded_{label}_streak", "streak",
                        f"{athlete}’s longest loaded {wording} streak is {result['longest']} races",
                        f"The historical loaded best is longer than the current sequence in {scope_label}.",
                        {"name": f"longest_consecutive_{label}s", "value": result["longest"], "unit": "entered races"},
                        result["best_rows"], subject_id=athlete_id, detector="streaks.longest",
                        comparison={"type": "athlete_loaded_best", "current_value": result["current"]},
                        confidence=.8 if athlete_id.startswith("legacy:") else 1.0,
                        scope=ctx.scope(rows),
                    ))
            if allowed_disciplines is None and summaries["podium"]["longest"]:
                table.append({"athlete_id": athlete_id, "athlete": athlete, "nation": nation,
                              "podium_streak": summaries["podium"]["longest"],
                              "current_podium_streak": summaries["podium"]["current"],
                              "winning_streak": summaries["win"]["longest"]})
    table.sort(key=lambda item: (-item["podium_streak"], item["athlete"] or ""))
    return table, insights


def milestones(ctx, profiles):
    insights = []
    definitions = (
        ("start", "starts", START_MILESTONES),
        ("win", "wins", WIN_MILESTONES),
        ("podium", "podiums", PODIUM_MILESTONES),
    )
    for profile in profiles:
        for singular, field, thresholds in definitions:
            value = profile[field]
            next_threshold = next((threshold for threshold in thresholds if threshold >= value), None)
            if value in thresholds:
                insights.append(_insight(
                    ctx, f"loaded_{singular}_milestone", "milestone",
                    f"{profile['athlete']} reached {value} loaded {field}",
                    f"The total is reconstructed from the current classifications and may not represent the full career.",
                    {"name": field, "value": value, "unit": field}, profile["rows"],
                    subject_id=profile["athlete_id"], detector="milestones.loaded",
                    comparison={"type": "threshold", "threshold": value},
                ))
            elif next_threshold and value == next_threshold - 1:
                insights.append(_insight(
                    ctx, f"approaching_{singular}_milestone", "milestone",
                    f"{profile['athlete']} is one {singular} from {next_threshold} in loaded history",
                    f"The current loaded total is {value}; the next qualifying result would make {next_threshold}.",
                    {"name": field, "value": value, "unit": field}, profile["rows"],
                    status="approaching_milestone", subject_id=profile["athlete_id"], detector="milestones.loaded",
                    comparison={"type": "threshold", "threshold": next_threshold, "remaining": 1},
                ))
        if profile["wins"] == 1:
            win = next(row for row in profile["rows"] if row.get("place") == 1)
            insights.append(_insight(ctx, "first_loaded_win", "milestone",
                f"{profile['athlete']}’s first win visible in the loaded data",
                f"The win came at {win.get('venue')} on {win.get('date')}; earlier wins may sit outside coverage.",
                {"name": "wins", "value": 1, "unit": "win"}, [win], subject_id=profile["athlete_id"],
                detector="milestones.firsts"))
        if profile["podiums"] == 1:
            podium = next(row for row in profile["rows"] if isinstance(row.get("place"), int) and row["place"] <= 3)
            insights.append(_insight(ctx, "first_loaded_podium", "milestone",
                f"{profile['athlete']}’s first podium visible in the loaded data",
                f"The podium came at {podium.get('venue')} on {podium.get('date')}; earlier podiums may sit outside coverage.",
                {"name": "podiums", "value": 1, "unit": "podium"}, [podium], subject_id=profile["athlete_id"],
                detector="milestones.firsts"))
        for discipline, totals in profile["disciplines"].items():
            discipline_rows = [row for row in profile["rows"] if row.get("discipline") == discipline]
            if totals["wins"] == 1:
                win = next(row for row in discipline_rows if row.get("place") == 1)
                insights.append(_insight(ctx, "first_loaded_discipline_win", "milestone",
                    f"{profile['athlete']}’s first {discipline} win visible in loaded data",
                    f"The discipline-specific loaded total is one; full career coverage is not established.",
                    {"name": "discipline_wins", "value": 1, "unit": "win", "discipline": discipline},
                    [win], subject_id=profile["athlete_id"], detector="milestones.discipline",
                    scope=ctx.scope(discipline_rows)))
            next_start = next((value for value in START_MILESTONES if value > totals["starts"]), None)
            if next_start and totals["starts"] == next_start - 1:
                insights.append(_insight(ctx, "approaching_discipline_start_milestone", "milestone",
                    f"{profile['athlete']} is one {discipline} start from {next_start} in loaded history",
                    f"The current discipline total is {totals['starts']} loaded starts.",
                    {"name": "discipline_starts", "value": totals["starts"], "unit": "starts", "discipline": discipline},
                    discipline_rows, status="approaching_milestone", subject_id=profile["athlete_id"],
                    detector="milestones.discipline", scope=ctx.scope(discipline_rows),
                    comparison={"type": "threshold", "threshold": next_start, "remaining": 1}))
        for venue, totals in profile["venues"].items():
            if totals["wins"] == 1:
                win = next(row for row in profile["rows"] if row.get("venue") == venue and row.get("place") == 1)
                insights.append(_insight(ctx, "first_loaded_venue_win", "milestone",
                    f"{profile['athlete']}’s first win at {venue} visible in loaded data",
                    "Earlier venue races may sit outside the current classifications.",
                    {"name": "venue_wins", "value": 1, "unit": "win"}, [win],
                    subject_id=profile["athlete_id"], detector="milestones.venue",
                    scope=ctx.scope([win], venue=venue)))
    return insights


def venue_records(ctx, profiles, minimum_rate_starts=3):
    insights = []
    venues = sorted({row.get("venue") for row in ctx.rows if row.get("venue")})
    for venue in venues:
        venue_rows = [row for row in ctx.rows if row.get("venue") == venue]
        athlete_counts = defaultdict(Counter)
        for row in venue_rows:
            if ctx.is_start(row):
                counts = athlete_counts[row["athlete_id"]]
                counts["starts"] += 1
                counts["wins"] += row.get("place") == 1
                counts["podiums"] += isinstance(row.get("place"), int) and row["place"] <= 3
        for metric in ("wins", "podiums", "starts"):
            if not athlete_counts:
                continue
            record = max(values[metric] for values in athlete_counts.values())
            if not record:
                continue
            leaders = sorted(key for key, values in athlete_counts.items() if values[metric] == record)
            leader_rows = [next(row for row in venue_rows if row["athlete_id"] == key) for key in leaders]
            names = ", ".join(row["athlete"] for row in leader_rows[:3])
            tied = len(leaders) > 1
            insights.append(_insight(
                ctx, f"venue_{metric}_leader", "venue",
                f"{names} {'share' if tied else 'has'} the most {metric} at {venue} in loaded races",
                f"The loaded {venue} record is {record}; this is not presented as an all-time venue record.",
                {"name": f"venue_{metric}", "value": record, "unit": metric},
                [row for row in venue_rows if row["athlete_id"] in leaders],
                subject_type="athlete_group" if tied else "athlete", subject_id="|".join(leaders),
                subject_name=names, detector="venues.leaders", scope=ctx.scope(venue_rows, venue=venue),
                comparison={"type": "loaded_venue_ranking", "rank": 1, "tied": tied},
            ))
            if metric in {"wins", "podiums"} and record > 1:
                chasers = [key for key, values in athlete_counts.items() if values[metric] == record - 1]
                for key in chasers[:3]:
                    athlete_rows = [row for row in venue_rows if row["athlete_id"] == key]
                    insights.append(_insight(ctx, f"one_from_venue_{metric}_record", "venue",
                        f"{athlete_rows[-1]['athlete']} is one {metric[:-1]} from the loaded {venue} lead",
                        f"The athlete has {record - 1}; the loaded leaders have {record}.",
                        {"name": f"venue_{metric}", "value": record - 1, "unit": metric}, athlete_rows,
                        subject_id=key, detector="venues.chasers", scope=ctx.scope(venue_rows, venue=venue),
                        comparison={"type": "loaded_venue_record", "record": record, "remaining": 1}))
        eligible = [(key, values["podiums"] / values["starts"], values) for key, values in athlete_counts.items()
                    if values["starts"] >= minimum_rate_starts]
        if eligible:
            key, rate, values = max(eligible, key=lambda item: (item[1], item[2]["podiums"], item[0]))
            row = next(row for row in venue_rows if row["athlete_id"] == key)
            insights.append(_insight(ctx, "venue_best_podium_rate", "venue",
                f"{row['athlete']} has the best qualifying podium rate at {venue} in loaded races",
                f"{values['podiums']} podiums from {values['starts']} starts ({rate:.0%}); minimum {minimum_rate_starts} starts.",
                {"name": "podium_rate", "value": round(rate, 4), "unit": "proportion"},
                [item for item in venue_rows if item["athlete_id"] == key], subject_id=key,
                detector="venues.rates", scope=ctx.scope(venue_rows, venue=venue)))
        dated_races = sorted(ctx.by_race.values(), key=lambda rows: rows[0].get("parsed_date") or date.min)
        venue_races = [rows for rows in dated_races if rows and rows[0].get("venue") == venue]
        if venue_races:
            winners = [row for row in venue_races[-1] if row.get("place") == 1]
            if len(winners) == 1:
                winner = winners[0]
                insights.append(_insight(ctx, "defending_loaded_venue_winner", "venue",
                    f"{winner['athlete']} is the latest loaded winner at {venue}",
                    f"The most recent stored race at the venue was {winner.get('date')} ({winner.get('discipline')}).",
                    {"name": "latest_venue_win", "value": 1, "unit": "race"}, [winner],
                    subject_id=winner["athlete_id"], detector="venues.defending",
                    scope=ctx.scope(venue_races[-1], venue=venue)))
    return insights


def margin_insights(ctx):
    records_by_format = defaultdict(list)
    for race_key, rows in ctx.by_race.items():
        margin = winning_margin(rows)
        if margin:
            margin["race_key"] = race_key
            margin["rows"] = rows
            first = rows[0]
            format_key = (first.get("competition"), first.get("gender"), first.get("discipline"),
                          first.get("event_format"), first.get("run_count"))
            records_by_format[format_key].append(margin)
    if not records_by_format:
        return []
    insights = []
    for format_key, records in records_by_format.items():
        for label, record in (("smallest", min(records, key=lambda item: item["seconds"])),
                              ("largest", max(records, key=lambda item: item["seconds"]))):
            winner, runner = record["winner"], record["runner_up"]
            ordered = sorted(item["seconds"] for item in records)
            percentile = ordered.index(record["seconds"]) / max(1, len(ordered) - 1)
            insights.append(_insight(ctx, f"{label}_loaded_winning_margin", "margin",
                f"{label.title()} winning margin in comparable loaded {winner.get('discipline')} races",
                f"{winner['athlete']} beat {runner['athlete']} by {record['seconds']:.2f}s at {winner.get('venue')}.",
                {"name": "winning_margin", "value": record["seconds"], "unit": "seconds"},
                [winner, runner], subject_id=winner["athlete_id"], detector="margins.extremes",
                comparison={"type": "loaded_margin_percentile", "race_count": len(records),
                            "percentile": round(percentile, 3), "format_key": format_key},
                calculated={"calculated_margin_seconds": record["seconds"]},
                scope=ctx.scope(record["rows"], venue=winner.get("venue"))))
        podium_spans = []
        for record in records:
            third_rows = [row for row in record["rows"] if row.get("place") == 3]
            if not third_rows:
                continue
            winner, third = record["winner"], third_rows[0]
            span = seconds(third.get("diff_time"))
            if span is None and str(third.get("time") or "").startswith("+"):
                span = seconds(third.get("time"))
            if span is None:
                winner_total = seconds(winner.get("total_time") or winner.get("time"))
                third_total = seconds(third.get("total_time") or third.get("time"))
                if winner_total is not None and third_total is not None and third_total >= winner_total:
                    span = third_total - winner_total
            if span is not None and span >= 0:
                podium_spans.append((span, winner, third, record["rows"]))
        if podium_spans:
            span, winner, third, race_rows = min(podium_spans, key=lambda item: item[0])
            insights.append(_insight(ctx, "closest_loaded_podium", "margin",
                f"Closest first-to-third spread in comparable loaded {winner.get('discipline')} races",
                f"{span:.2f}s separated {winner['athlete']} from third-placed {third['athlete']} at {winner.get('venue')}.",
                {"name": "podium_span", "value": round(span, 3), "unit": "seconds"},
                [winner, third], subject_id=winner["athlete_id"], detector="margins.podium",
                comparison={"type": "loaded_podium_span", "race_count": len(podium_spans), "format_key": format_key},
                calculated={"calculated_podium_span_seconds": round(span, 3)},
                scope=ctx.scope(race_rows, venue=winner.get("venue"))))
    return insights


def droughts(ctx):
    insights = []
    for athlete_id, all_rows in ctx.by_athlete.items():
        disciplines = sorted({row.get("discipline") for row in all_rows if row.get("discipline")})
        scopes = [(None, all_rows)] + [
            (discipline, [row for row in all_rows if row.get("discipline") == discipline])
            for discipline in disciplines if len(disciplines) > 1
        ]
        for discipline, rows in scopes:
            starts = [row for row in rows if ctx.is_start(row)]
            for label, predicate in (("win", lambda row: row.get("place") == 1),
                                     ("podium", lambda row: isinstance(row.get("place"), int) and row["place"] <= 3)):
                success_indexes = [index for index, row in enumerate(starts) if predicate(row)]
                if not success_indexes:
                    continue
                qualifier = f" {discipline}" if discipline else ""
                between = [(success_indexes[index + 1] - success_indexes[index] - 1,
                            success_indexes[index], success_indexes[index + 1])
                           for index in range(len(success_indexes) - 1)]
                if between:
                    longest, start_index, end_index = max(between)
                    if longest >= 3:
                        evidence = starts[start_index:end_index + 1]
                        insights.append(_insight(ctx, f"longest_loaded_gap_between_{label}s", "drought",
                            f"{rows[-1]['athlete']}’s longest loaded{qualifier} gap between {label}s was {longest} starts",
                            "The gap is reconstructed only from classifications currently loaded.",
                            {"name": f"longest_gap_between_{label}s", "value": longest, "unit": "starts"},
                            evidence, subject_id=athlete_id, detector="droughts.longest", scope=ctx.scope(rows)))
                last_index = success_indexes[-1]
                gap_rows = starts[last_index + 1:]
                if len(gap_rows) < 3:
                    continue
                last = starts[last_index]
                days = ((gap_rows[-1].get("parsed_date") - last.get("parsed_date")).days
                        if gap_rows[-1].get("parsed_date") and last.get("parsed_date") else None)
                summary = f"{len(gap_rows)} subsequent starts without a {label} in loaded history"
                if days is not None:
                    summary += f", spanning {days} days"
                insights.append(_insight(ctx, f"{discipline.lower() + '_' if discipline else ''}starts_since_last_{label}", "drought",
                    f"{rows[-1]['athlete']} has {len(gap_rows)} loaded{qualifier} starts since the last {label}",
                    summary + ". Earlier or missing races can change this calculation.",
                    {"name": f"starts_since_last_{label}", "value": len(gap_rows), "unit": "starts"},
                    [last, *gap_rows], subject_id=athlete_id, detector="droughts.gaps",
                    comparison={"type": "elapsed_since_result", "days": days}, scope=ctx.scope(rows)))
    return insights


def recent_form(ctx):
    insights = []
    for athlete_id, rows in ctx.by_athlete.items():
        starts = [row for row in rows if ctx.is_start(row)]
        if len(starts) < 3:
            continue
        window = min((value for value in WINDOWS if value <= len(starts)), default=3, key=lambda value: abs(5 - value))
        recent = starts[-window:]
        finishes = [row["place"] for row in recent if ctx.is_finish(row)]
        earlier_finishes = [row["place"] for row in starts[:-window] if ctx.is_finish(row)]
        metrics = {
            "window": window, "wins": sum(row.get("place") == 1 for row in recent),
            "podiums": sum(isinstance(row.get("place"), int) and row["place"] <= 3 for row in recent),
            "top_tens": sum(isinstance(row.get("place"), int) and row["place"] <= 10 for row in recent),
            "average_finish": round(mean(finishes), 2) if finishes else None,
            "median_finish": median(finishes) if finishes else None,
            "completion_rate": len(finishes) / window,
            "consistency": round(pstdev(finishes), 2) if len(finishes) > 1 else 0 if finishes else None,
        }
        if earlier_finishes and finishes:
            metrics["improvement"] = round(mean(earlier_finishes) - mean(finishes), 2)
        if metrics["podiums"] >= 2 or abs(metrics.get("improvement", 0)) >= 1.5:
            direction = "improved" if metrics.get("improvement", 0) > 0 else "declined" if metrics.get("improvement", 0) < 0 else "held steady"
            insights.append(_insight(ctx, "recent_form_window", "recent_form",
                f"{rows[-1]['athlete']} has {metrics['podiums']} podiums in the last {window} loaded starts",
                f"The completed-result average is {metrics['average_finish'] or 'unavailable'}; form has {direction} versus earlier loaded starts. Non-finishes affect completion rate, not average placing.",
                {"name": "recent_form", "value": metrics["podiums"], "unit": "podiums", **metrics},
                recent, subject_id=athlete_id, detector="recent_form.windows"))
    return insights


def nation_insights(ctx):
    insights, totals = [], defaultdict(Counter)
    for row in ctx.rows:
        nation = row.get("nation")
        if not nation:
            continue
        if ctx.is_start(row):
            totals[nation]["starts"] += 1
        totals[nation]["wins"] += row.get("place") == 1
        totals[nation]["podiums"] += isinstance(row.get("place"), int) and row["place"] <= 3
    for metric in ("wins", "podiums"):
        if totals:
            record = max(values[metric] for values in totals.values())
            leaders = sorted(nation for nation, values in totals.items() if values[metric] == record)
            if record:
                evidence = [row for row in ctx.rows if row.get("nation") in leaders and
                            (row.get("place") == 1 if metric == "wins" else isinstance(row.get("place"), int) and row["place"] <= 3)]
                insights.append(_insight(ctx, f"national_{metric}_leader", "nation",
                    f"{' and '.join(leaders)} lead loaded national {metric}",
                    f"The leading total is {record} within the current classifications.",
                    {"name": f"national_{metric}", "value": record, "unit": metric}, evidence,
                    subject_type="nation", subject_id="|".join(leaders), subject_name=" / ".join(leaders),
                    detector="nations.totals", comparison={"type": "loaded_national_ranking", "rank": 1, "tied": len(leaders) > 1}))
    for race_rows in ctx.by_race.values():
        podium = [row for row in race_rows if row.get("place") in (1, 2, 3)]
        top_two = [row for row in race_rows if row.get("place") in (1, 2)]
        if len(top_two) == 2 and len({row.get("nation") for row in top_two}) == 1:
            nation = top_two[0].get("nation")
            insights.append(_insight(ctx, "national_one_two", "nation",
                f"{nation} recorded a one-two finish in a loaded race",
                f"{top_two[0]['athlete']} and {top_two[1]['athlete']} finished first and second at {top_two[0].get('venue')}.",
                {"name": "top_two_places", "value": 2, "unit": "places"}, top_two,
                subject_type="nation", subject_id=nation, subject_name=nation, detector="nations.one_two"))
        if len(podium) == 3 and len({row.get("nation") for row in podium}) == 1:
            nation = podium[0].get("nation")
            insights.append(_insight(ctx, "national_podium_sweep", "nation",
                f"{nation} swept the podium in a loaded race",
                f"Athletes from {nation} finished first, second and third at {podium[0].get('venue')} on {podium[0].get('date')}.",
                {"name": "podium_places", "value": 3, "unit": "places"}, podium,
                subject_type="nation", subject_id=nation, subject_name=nation, detector="nations.sweeps"))
    venue_nation_wins = defaultdict(list)
    for row in ctx.rows:
        if row.get("place") == 1 and row.get("venue") and row.get("nation"):
            venue_nation_wins[(row["venue"], row["nation"])].append(row)
    for (venue, nation), wins in venue_nation_wins.items():
        if len(wins) == 1:
            insights.append(_insight(ctx, "first_loaded_national_venue_win", "nation",
                f"First {nation} win at {venue} visible in loaded data",
                f"{wins[0]['athlete']} supplied the only stored {nation} win at this venue.",
                {"name": "national_venue_wins", "value": 1, "unit": "win"}, wins,
                subject_type="nation", subject_id=nation, subject_name=nation,
                detector="nations.venue", scope=ctx.scope(wins, venue=venue)))
    for nation, values in totals.items():
        for metric, thresholds in (("wins", WIN_MILESTONES), ("podiums", PODIUM_MILESTONES)):
            next_threshold = next((value for value in thresholds if value > values[metric]), None)
            if next_threshold and values[metric] == next_threshold - 1:
                evidence = [row for row in ctx.rows if row.get("nation") == nation]
                insights.append(_insight(ctx, f"approaching_national_{metric}_milestone", "nation",
                    f"{nation} is one {metric[:-1]} from {next_threshold} in loaded history",
                    f"The current reconstructed national total is {values[metric]}.",
                    {"name": f"national_{metric}", "value": values[metric], "unit": metric}, evidence,
                    status="approaching_milestone", subject_type="nation", subject_id=nation, subject_name=nation,
                    detector="nations.milestones", comparison={"type": "threshold", "threshold": next_threshold, "remaining": 1}))
    ordered_races = sorted(ctx.by_race.values(), key=lambda rows: rows[0].get("parsed_date") or date.min)
    for nation in totals:
        entered = [rows for rows in ordered_races if any(row.get("nation") == nation and ctx.is_start(row) for row in rows)]
        winning_indexes = [index for index, rows in enumerate(entered)
                           if any(row.get("nation") == nation and row.get("place") == 1 for row in rows)]
        if not winning_indexes:
            continue
        drought_races = entered[winning_indexes[-1] + 1:]
        if len(drought_races) >= 3:
            evidence = [row for rows in drought_races for row in rows if row.get("nation") == nation]
            insights.append(_insight(ctx, "national_winning_drought", "nation",
                f"{nation} has gone {len(drought_races)} loaded races without a win",
                "Only races with at least one entered athlete from the nation are counted; missing history can alter the gap.",
                {"name": "national_races_since_win", "value": len(drought_races), "unit": "races"}, evidence,
                subject_type="nation", subject_id=nation, subject_name=nation, detector="nations.drought"))
    return insights


def age_insights(ctx):
    insights = []
    for label, predicate in (("winner", lambda row: row.get("place") == 1),
                             ("podium finisher", lambda row: isinstance(row.get("place"), int) and row["place"] <= 3)):
        candidates = [(row, age_at(row)) for row in ctx.rows if predicate(row)]
        candidates = [(row, age) for row, age in candidates if age]
        if not candidates:
            continue
        for edge, chooser in (("youngest", min), ("oldest", max)):
            row, age = chooser(candidates, key=lambda item: item[1]["days"] if item[1]["days"] is not None else item[1]["years"] * 365)
            status = "coverage_limited" if age["exact"] else "approximate"
            insights.append(_insight(ctx, f"{edge}_loaded_{label.replace(' ', '_')}", "age",
                f"{edge.title()} {label} in the currently loaded races",
                f"{row['athlete']} was {age['display']} at {row.get('venue')} on {row.get('date')}.",
                {"name": "age", "value": age["days"] if age["exact"] else age["years"],
                 "unit": "days" if age["exact"] else "approximate years", "exact": age["exact"]},
                [row], status=status, subject_id=row["athlete_id"], detector="ages.extremes",
                confidence=1.0 if age["exact"] else .65,
                comparison={"type": "loaded_age_ranking", "edge": edge}))
    first_wins = []
    for rows in ctx.by_athlete.values():
        wins = [row for row in rows if row.get("place") == 1 and age_at(row)]
        if wins:
            first_wins.append((wins[0], age_at(wins[0])))
    if first_wins:
        row, age = max(first_wins, key=lambda item: item[1]["days"] if item[1]["days"] is not None else item[1]["years"] * 365)
        insights.append(_insight(ctx, "oldest_first_loaded_winner", "age",
            "Oldest first-time winner visible in the loaded data",
            f"{row['athlete']} was {age['display']} at their earliest stored win; earlier wins may be missing.",
            {"name": "age_at_first_loaded_win", "value": age["days"] if age["exact"] else age["years"],
             "unit": "days" if age["exact"] else "approximate years", "exact": age["exact"]},
            [row], status="coverage_limited" if age["exact"] else "approximate",
            subject_id=row["athlete_id"], detector="ages.first_win",
            confidence=1.0 if age["exact"] else .65))
    return insights


def conditional_scenarios(ctx, profiles, athlete_ids):
    requested = set(str(value) for value in (athlete_ids or []) if str(value))
    if not requested:
        return []
    by_id = {profile["athlete_id"]: profile for profile in profiles}
    by_fis = {profile["fis_code"]: profile for profile in profiles if profile["fis_code"]}
    insights = []
    for requested_id in requested:
        profile = by_id.get(requested_id) or by_fis.get(requested_id)
        if not profile:
            continue
        scope = ctx.scope(profile["rows"])
        selected_venue = scope.get("venue")
        selected_disciplines = scope.get("disciplines") or []
        for result, field, milestones_set in (("win", "wins", WIN_MILESTONES), ("podium", "podiums", PODIUM_MILESTONES)):
            current, projected = profile[field], profile[field] + 1
            threshold = projected if projected in milestones_set else None
            consequences = []
            if threshold:
                consequences.append(f"reach the {projected}-{field} milestone")
            if len(selected_disciplines) == 1:
                discipline = selected_disciplines[0]
                current_discipline = profile["disciplines"].get(discipline, {}).get(field, 0)
                consequences.append(f"move the loaded {discipline} total from {current_discipline} to {current_discipline + 1}")
            comparison = {"type": "threshold" if threshold else "current_loaded_total", "threshold": threshold}
            if selected_venue:
                venue_total = profile["venues"].get(selected_venue, {}).get(field, 0)
                venue_record = max((item["venues"].get(selected_venue, {}).get(field, 0) for item in profiles), default=0)
                projected_venue = venue_total + 1
                if projected_venue >= venue_record and venue_record:
                    action = "break" if projected_venue > venue_record else "equal"
                    consequences.append(f"{action} the loaded {selected_venue} {field} record of {venue_record}")
                    comparison.update({"type": "loaded_venue_record", "record": venue_record,
                                       "projected_value": projected_venue, "outcome": action})
            nation_total = sum(item[field] for item in profiles if item["nation"] == profile["nation"])
            national_projected = nation_total + 1
            if national_projected in milestones_set:
                consequences.append(f"take {profile['nation']} to {national_projected} loaded {field}")
            consequence = "; ".join(consequences) if consequences else f"move the reconstructed total from {current} to {projected}"
            insights.append(_insight(ctx, f"if_{result}", "milestone",
                f"A {result} for {profile['athlete']} would make {projected} loaded {field}",
                f"The current reconstructed total is {current}; the scenario would {consequence}. This is not a confirmed result.",
                {"name": field, "value": projected, "current_value": current, "unit": field},
                profile["rows"], status="conditional", subject_id=profile["athlete_id"],
                condition={"type": f"if_{result}", "increment": 1}, detector="conditional.result",
                comparison=comparison, scope=scope))
    return insights


DETECTORS = (venue_records, margin_insights, droughts, recent_form, nation_insights, age_insights)
