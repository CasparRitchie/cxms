import unittest

from services.sports_editorial.insights.context import InsightContext, normalise_country, seconds, winning_margin
from services.sports_editorial.stat_insights import build_stat_insights


def result(index, athlete="Racer One", fis_code="100", place=1, *, date=None,
           discipline="GS", venue="Venue A", nation="SUI", status="finished", **extra):
    row = {
        "race_id": str(1000 + index), "date": date or f"2026-01-{index:02d}",
        "season_code": 2026, "venue": venue, "discipline": discipline,
        "gender": "W", "competition": "WC", "athlete": athlete,
        "fis_code": fis_code, "nation": nation, "place": place, "status": status,
    }
    row.update(extra)
    return row


def insights(rows, **kwargs):
    return build_stat_insights(rows, score_threshold=0, **kwargs)


class StatInsightEngineTests(unittest.TestCase):
    def test_stable_ids_prevent_same_name_being_merged(self):
        built = insights([result(1, fis_code="100"), result(2, fis_code="200")])
        self.assertEqual(built["athlete_count"], 2)

    def test_dns_is_not_a_start_but_dnf_is_a_start_and_not_completed(self):
        rows = [
            result(1),
            result(2, place=None, status="DNS"),
            result(3, place=None, status="did_not_finish"),
        ]
        profile = insights(rows)["leaders"][0]
        self.assertEqual(profile["starts"], 2)
        self.assertEqual(profile["completed"], 1)
        self.assertEqual(profile["finish_rate"], .5)

    def test_current_and_longest_podium_and_winning_streak_span_seasons(self):
        rows = [
            result(1, date="2025-12-28", season_code=2026),
            result(2, date="2026-01-03", season_code=2026),
            result(3, date="2026-01-04", place=2, season_code=2026),
        ]
        built = insights(rows)
        row = built["streaks"][0]
        self.assertEqual(row["podium_streak"], 3)
        self.assertEqual(row["current_podium_streak"], 3)
        self.assertEqual(row["winning_streak"], 2)
        self.assertTrue(any(item["insight_type"] == "current_podium_streak" for item in built["structured_insights"]))

    def test_streak_ending_in_latest_entered_race_is_labelled(self):
        built = insights([result(1), result(2, place=2), result(3, place=8)])
        ended = [item for item in built["structured_insights"] if item["insight_type"] == "ended_podium_streak"]
        self.assertTrue(ended)
        self.assertIn("ended last race", ended[0]["title"])

    def test_unrelated_discipline_does_not_interrupt_gs_sl_streak(self):
        rows = [
            result(1, discipline="GS", place=2),
            result(2, discipline="DH", place=15),
            result(3, discipline="SL", place=3),
        ]
        candidates = [item for item in insights(rows)["structured_insights"]
                      if item["insight_type"] == "current_podium_streak"
                      and item["scope"]["disciplines"] == ["GS", "SL"]]
        self.assertEqual(candidates[0]["metric"]["value"], 2)

    def test_start_and_podium_milestone_candidates_and_first_win(self):
        rows = [result(index, place=2 if index < 9 else 1) for index in range(1, 10)]
        types = {item["insight_type"] for item in insights(rows)["structured_insights"]}
        self.assertIn("approaching_start_milestone", types)
        self.assertIn("approaching_podium_milestone", types)
        self.assertIn("first_loaded_win", types)

    def test_tied_venue_win_and_podium_leaders_are_retained(self):
        rows = [
            result(1, athlete="A", fis_code="1", place=1),
            result(2, athlete="B", fis_code="2", place=1),
            result(3, athlete="A", fis_code="1", place=2),
            result(4, athlete="B", fis_code="2", place=2),
        ]
        items = insights(rows)["structured_insights"]
        wins = next(item for item in items if item["insight_type"] == "venue_wins_leader")
        podiums = next(item for item in items if item["insight_type"] == "venue_podiums_leader")
        self.assertTrue(wins["comparison"]["tied"])
        self.assertTrue(podiums["comparison"]["tied"])

    def test_narrowest_and_largest_margins_support_difference_and_total_times(self):
        rows = [
            result(1, athlete="Winner A", fis_code="1", total_time="1:30.00"),
            result(1, athlete="Runner A", fis_code="2", place=2, time="+0.05", diff_time="+0.05"),
            result(2, athlete="Winner B", fis_code="3", total_time="1:20.00"),
            result(2, athlete="Runner B", fis_code="4", place=2, total_time="1:22.50"),
        ]
        items = insights(rows)["structured_insights"]
        smallest = next(item for item in items if item["insight_type"] == "smallest_loaded_winning_margin")
        largest = next(item for item in items if item["insight_type"] == "largest_loaded_winning_margin")
        self.assertEqual(smallest["metric"]["value"], .05)
        self.assertEqual(largest["metric"]["value"], 2.5)
        self.assertEqual(largest["evidence"][1]["athlete_name"], "Runner B")

    def test_malformed_times_and_tied_winners_do_not_create_margin(self):
        self.assertIsNone(seconds("not a time"))
        tied = [result(1, athlete="A", fis_code="1", total_time="1:00"),
                result(1, athlete="B", fis_code="2", total_time="1:00")]
        self.assertIsNone(winning_margin(InsightContext(tied).rows))

    def test_exact_and_approximate_ages_are_distinguished(self):
        rows = [
            result(1, athlete="Exact", fis_code="1", date="2026-01-10", birth_date="2000-01-01"),
            result(2, athlete="Approx", fis_code="2", date="2026-01-11", birth_year="1990"),
        ]
        age_items = [item for item in insights(rows)["structured_insights"] if item["category"] == "age"]
        self.assertTrue(any(item["metric"].get("exact") is True for item in age_items))
        self.assertTrue(any(item["status"] == "approximate" for item in age_items))
        self.assertTrue(any("26 years, 9 days" in item["summary"] for item in age_items))

    def test_national_podium_sweep_and_deliberate_historical_country_mapping(self):
        rows = [result(1, athlete=f"A{place}", fis_code=str(place), place=place, nation="FRG") for place in (1, 2, 3)]
        default = insights(rows)
        sweep = next(item for item in default["structured_insights"] if item["insight_type"] == "national_podium_sweep")
        self.assertEqual(sweep["subject_id"], "FRG")
        mapped = build_stat_insights(rows, score_threshold=0, country_mapping={"FRG": "GER"})
        mapped_sweep = next(item for item in mapped["structured_insights"] if item["insight_type"] == "national_podium_sweep")
        self.assertEqual(mapped_sweep["subject_id"], "GER")
        self.assertEqual(normalise_country("FRG"), "FRG")

    def test_starts_since_last_podium_and_longest_gap(self):
        places = [2, 12, 11, 10, 9, 3, 8, 7, 6]
        items = insights([result(index, place=place) for index, place in enumerate(places, 1)])["structured_insights"]
        current = next(item for item in items if item["insight_type"] == "starts_since_last_podium")
        longest = next(item for item in items if item["insight_type"] == "longest_loaded_gap_between_podiums")
        self.assertEqual(current["metric"]["value"], 3)
        self.assertEqual(longest["metric"]["value"], 4)

    def test_recent_form_window_keeps_non_finish_out_of_average(self):
        rows = [result(index, place=place) for index, place in enumerate((20, 15, 14, 8, 3, 2), 1)]
        rows[-2] = result(5, place=None, status="did_not_finish")
        form = next(item for item in insights(rows)["structured_insights"] if item["insight_type"] == "recent_form_window")
        self.assertEqual(form["metric"]["window"], 5)
        self.assertEqual(form["metric"]["completion_rate"], .8)

    def test_conditional_win_and_podium_are_never_confirmed(self):
        rows = [result(index, fis_code="516562", place=2) for index in range(1, 10)]
        built = insights(rows, scenario_athlete_ids=["516562"])
        scenarios = [item for item in built["structured_insights"] if item["status"] == "conditional"]
        self.assertEqual({item["insight_type"] for item in scenarios}, {"if_win", "if_podium"})
        self.assertTrue(all(item["title"].startswith(("A win for", "A podium for")) for item in scenarios))
        self.assertTrue(all(item["metric"]["current_value"] + 1 == item["metric"]["value"] for item in scenarios))

    def test_coverage_limited_wording_and_evidence_on_every_insight(self):
        built = insights([result(index, place=2) for index in range(1, 5)])
        self.assertFalse(built["coverage"]["is_known_complete"])
        self.assertTrue(all(item["evidence"] for item in built["structured_insights"]))
        self.assertTrue(all(item["coverage_warning"] for item in built["structured_insights"]))
        self.assertTrue(any("loaded" in (item["title"] + item["summary"]).casefold() for item in built["structured_insights"]))

    def test_known_complete_coverage_can_emit_confirmed_status(self):
        built = build_stat_insights([result(index, place=2) for index in range(1, 4)], score_threshold=0,
                                    coverage={"is_known_complete": True, "coverage_type": "verified_manifest"})
        self.assertTrue(any(item["status"] == "confirmed" for item in built["structured_insights"]))
        self.assertTrue(all(item["coverage_warning"] is None for item in built["structured_insights"]))

    def test_score_and_ids_are_deterministic_and_overlaps_are_suppressed(self):
        rows = [result(index, place=2) for index in range(1, 6)]
        first = insights(rows)["structured_insights"]
        second = insights(rows)["structured_insights"]
        self.assertEqual([(item["id"], item["editorial_score"], item["score_breakdown"]) for item in first],
                         [(item["id"], item["editorial_score"], item["score_breakdown"]) for item in second])
        fingerprints = [(item["subject_id"], item["category"], item["metric"]["name"],
                         tuple(item["scope"].get("disciplines") or ())) for item in first]
        self.assertEqual(len(fingerprints), len(set(fingerprints)))

    def test_existing_filters_and_duplicate_classifications_continue_to_work(self):
        duplicate = result(1, athlete="A", fis_code="1", venue="A")
        rows = [duplicate, dict(duplicate), result(2, athlete="B", fis_code="2", venue="B")]
        built = insights(rows, venue="A", athlete="A")
        self.assertEqual(built["race_count"], 1)
        self.assertEqual(built["athlete_count"], 1)
        self.assertEqual(len(built["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
