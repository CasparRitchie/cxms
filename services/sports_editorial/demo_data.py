from copy import deepcopy


ENTITIES = [
    {"id": "entity-athlete-rast", "entity_type": "athlete", "name": "Camille Rast", "canonical_id": "516562", "canonical_url": "", "country_code": "SUI"},
    {"id": "entity-athlete-scheib", "entity_type": "athlete", "name": "Julia Scheib", "canonical_id": "56388", "canonical_url": "", "country_code": "AUT"},
    {"id": "entity-athlete-robinson", "entity_type": "athlete", "name": "Alice Robinson", "canonical_id": "415232", "canonical_url": "", "country_code": "NZL"},
    {"id": "entity-country-ch", "entity_type": "country", "name": "Switzerland", "canonical_id": "SUI", "canonical_url": "", "country_code": "SUI"},
    {"id": "entity-country-at", "entity_type": "country", "name": "Austria", "canonical_id": "AUT", "canonical_url": "", "country_code": "AUT"},
    {"id": "entity-country-it", "entity_type": "country", "name": "Italy", "canonical_id": "ITA", "canonical_url": "", "country_code": "ITA"},
    {"id": "entity-country-us", "entity_type": "country", "name": "United States", "canonical_id": "USA", "canonical_url": "", "country_code": "USA"},
    {"id": "entity-competition-world-cup", "entity_type": "competition", "name": "FIS World Cup", "canonical_id": "124321", "canonical_url": "", "country_code": ""},
    {"id": "entity-event-kronplatz", "entity_type": "event", "name": "Women's Giant Slalom — Kronplatz", "canonical_id": "55596", "canonical_url": "", "country_code": "ITA", "metadata": {"season_code": 2026, "discipline_code": "AL"}},
    {"id": "entity-event-kranjska", "entity_type": "event", "name": "Women's Giant Slalom — Kranjska Gora", "canonical_id": "55595", "canonical_url": "", "country_code": "SLO", "metadata": {"season_code": 2026, "discipline_code": "AL"}},
]


def _block(block_id, order, text, content_type="stat", entity_ids=None, tags=None):
    return {"id": block_id, "sort_order": order, "content_type": content_type, "stat_text": text, "edited_text": "", "editor_comment": "", "accepted_at": None, "accepted_by_user_id": None, "entity_ids": entity_ids or [], "entity_mentions": {}, "entity_ranges": {}, "tags": tags or []}


KRONPLATZ_CONTENT = [
    _block("kronplatz-section-1", 0, "Previous GS race (Kranjska Gora) stats", "section"),
    _block("kronplatz-stat-1", 1, "<strong>Camille Rast (SUI/Head)</strong> won the last Giant Slalom race, in Kranjska Gora, by 0.20s ahead of Julia Scheib (AUT/Rossignol), with Paula Moltzan (USA/Rossignol) in third. This was Rast’s first win in 58 GS starts, and made her the 20th Swiss woman to reach double figure podiums across all disciplines. It was also the slimmest winning margin of the 15 women’s GS races held in Kranjska Gora to date.", entity_ids=["entity-athlete-rast", "entity-event-kranjska"], tags=["previous-competition", "record"]),
    _block("kronplatz-stat-2", 2, "Camille Rast’s (SUI/Head) win completed her first back-to-back Giant Slalom podiums (after her 2nd in Semmering). The win was also Rast’s fourth in a run of five consecutive podiums she made across GS and Slalom races this season. In the 13 GS and SL races held since the start of the season, Rast is the only skier to have made five consecutive podiums (3 SL and 2 GS), but the streak ended with her 4th in SL in Flachau. The last Swiss woman before Rast to make the podium in at least five consecutive GS and SL races was Vreni Schneider (SUI) when she made 11 consecutive podiums (7 SL, 4 GS) across 1993/94 and 1994/95.", entity_ids=["entity-athlete-rast", "entity-country-ch"]),
    _block("kronplatz-stat-3", 3, "Camille Rast (SUI/Head) won both the Slalom and Giant Slalom races in Kranjska Gora. The last woman to win consecutive SL and GS races at the same venue was Mikaela Shiffrin (USA/Atomic), who won both races in Lienz in 2023/24. The last Swiss woman before Rast to do this was Sonja Nef (SUI) in 2000/01 in Are.", entity_ids=["entity-athlete-rast", "entity-event-kranjska"]),
    _block("kronplatz-stat-4", 4, "Julia Scheib’s (AUT/Rossignol) 2nd in Kranjska Gora was her third consecutive Giant Slalom podium this season — a first for Scheib — following wins in Semmering and Tremblant. Scheib is the only skier to have made the podium in five out of six GS races so far this season, with Alice Robinson (NZL/Salomon) the next best on three. The last Austrian woman to make three consecutive GS podiums was Eva-Maria Brem (AUT) in 2015/16.", entity_ids=["entity-athlete-scheib", "entity-country-at"]),
    _block("kronplatz-stat-5", 5, "Paula Moltzan’s (USA/Rossignol) 3rd in Kranjska Gora was her third Giant Slalom podium in 51 GS starts, having picked up her first GS podium (3rd) in Kronplatz in 2024/25, followed by 2nd in Soelden this season. Moltzan is the only USA athlete besides Mikaela Shiffrin (USA/Atomic) to have made more than one GS podium since 2013/14.", entity_ids=["entity-country-us"]),
    _block("kronplatz-section-2", 6, "Kronplatz stats", "section", ["entity-event-kronplatz"]),
    _block("kronplatz-stat-6", 7, "Federica Brignone (ITA/Rossignol) won the first of the nine World Cup women’s Giant Slalom races held in Kronplatz since 2016/17, and is the only Italian among the seven women’s GS winners there. Only Mikaela Shiffrin (USA/Atomic) has more than one GS win in Kronplatz, with three victories — 2018/19, 2022/23 and 2023/24. Shiffrin’s 1.21s win ahead of Tessa Worley (FRA) in 2018/19 is the biggest GS winning margin in Kronplatz to date.", entity_ids=["entity-event-kronplatz", "entity-country-it"]),
    _block("kronplatz-stat-7", 8, "In addition to Federica Brignone (ITA/Rossignol), other active skiers with a Giant Slalom win in Kronplatz are Sara Hector (SWE/Head) in 2021/22, Lara Gut-Behrami (SUI/Head) in 2023/24 and Alice Robinson (NZL/Salomon) in the most recent GS race there in 2024/25.", entity_ids=["entity-athlete-robinson", "entity-event-kronplatz"]),
    _block("kronplatz-stat-8", 9, "Lara Gut-Behrami (SUI/Head) is the oldest women’s Giant Slalom winner in Kronplatz at 32 years and 278 days in 2023/24. Skiers who are older than Gut-Behrami this weekend include Sara Hector (SWE/Head), Sofia Goggia (ITA/Atomic) and Lena Duerr (GER/Head), among others."),
    _block("kronplatz-stat-9", 10, "Alice Robinson (NZL/Salomon) is the youngest women’s GS winner in Kronplatz at age 23 years and 51 days in 2024/25, as well as the youngest women’s GS winner anywhere of the past two seasons. Skiers who could beat both milestones in Kronplatz include Lara Colturi (ALB/Blizzard), Zrinka Ljutic (CRO/Atomic) and Britt Richardson (CAN/Dynastar), among others.", entity_ids=["entity-athlete-robinson"]),
    _block("kronplatz-stat-10", 11, "Tessa Worley (FRA) and Lara Gut-Behrami (SUI/Head) have the most podiums in Kronplatz with four each, followed by four skiers on three each: Mikaela Shiffrin (USA/Atomic), Sara Hector (SWE/Head), Marta Bassino (ITA/Head) and Federica Brignone (ITA/Rossignol). On two each are Alice Robinson (NZL/Salomon) and Ragnhild Mowinckel (NOR). Paula Moltzan (USA/Rossignol) has one."),
    _block("kronplatz-stat-11", 12, "A win for a skier from Austria would be a first in women’s GS in Kronplatz. Austria is ranked first for all-time women’s GS wins (96) but is the only nation in the top seven not to have won the women’s GS in Kronplatz. Nations ranked second to seventh have all won a women’s GS in Kronplatz: Switzerland (84), France (53), Italy (50), United States of America (43) and Sweden (22).", entity_ids=["entity-country-at"]),
    _block("kronplatz-stat-12", 13, "A win for Camille Rast (SUI/Head) would see her become the 63rd skier to win more than one women’s Giant Slalom race. A win or podium for Rast would also see her equal her longest single-discipline podium streak (three in Slalom, set this season).", entity_ids=["entity-athlete-rast"]),
    _block("kronplatz-stat-13", 14, "If Alice Robinson (NZL/Salomon) wins she will move from six Giant Slalom wins, which is equal-24th for women alongside 11 other skiers, of which only one other is active — Marta Bassino (ITA/Head) — to equal-22nd alongside Sara Hector (SWE/Head) and Kathrin Zettel (AUT). Robinson and Bassino are also equal for women’s GS podiums (20) alongside three non-active skiers, which is equal-19th among women.", entity_ids=["entity-athlete-robinson"]),
    _block("kronplatz-stat-14", 15, "A win for New Zealand will see the nation move from equal-13th for women’s Giant Slalom wins (6) alongside Jugoslavia and Slovakia, to equal-12th alongside Spain (7)."),
    _block("kronplatz-stat-15", 16, "If Sara Hector (SWE/Head) wins, she will move from seven Giant Slalom wins, which is equal-22nd for women alongside Kathrin Zettel (AUT), to equal-19th alongside Michaela Dorfmeister (AUT), Monika Kaserer (AUT) and Nancy Greene (CAN). This would see Hector become just the fourth active skier in the current top 20 for women’s GS wins, alongside Mikaela Shiffrin (USA/Atomic) on 22 in first, Federica Brignone (ITA/Rossignol) on 17 in third, and Lara Gut-Behrami (SUI/Head) on 10, in equal-15th."),
    _block("kronplatz-stat-16", 17, "Mikaela Shiffrin (USA/Atomic) has now gone 11 Giant Slalom races without a podium, which is her second-longest streak without a podium within a single discipline. Her longest streak without a podium within a single discipline was her first 15 GS races from 2010/11 to 2013/14."),
    _block("kronplatz-stat-17", 18, "Italy is on 99 women’s and men’s Giant Slalom wins. The next win will see Italy become the third nation after Austria (210) and Switzerland (190) to reach 100 GS wins.", entity_ids=["entity-country-it"]),
    _block("kronplatz-stat-18", 19, "A win for Sweden will see the nation move from equal-seventh for women’s Giant Slalom podiums (72) alongside Federal Republic of Germany, to outright seventh behind Germany (85)."),
    _block("kronplatz-stat-19", 20, "France is on 299 women’s and men’s Giant Slalom podiums. The next French podium will see France become the fourth nation to reach 300, after Austria (635), Switzerland (502) and Italy (310)."),
    _block("kronplatz-stat-20", 21, "Maryna Gasienica-Daniel (POL/Atomic) will make her 90th Giant Slalom start in Kronplatz. Estelle Alphand (SWE/Head) and Ricarda Haaser (AUT/Salomon) will both make their 80th GS start, while AJ Hurt (USA/Head) will make her 50th GS start."),
    _block("kronplatz-stat-21", 22, "For World Cup starts across all disciplines, Stephanie Brunner (AUT/Head) will make her 150th World Cup start in Kronplatz, while Zrinka Ljutic (CRO/Atomic) will make her 90th (40th in GS, with 50 in SL) and Doriane Escane (FRA/Head) her 80th."),
]


SUBMISSIONS = [
    {"id": "demo-submission-kronplatz", "fis_external_id": "wc-alp-w-gs-kronplatz-2026", "fis_event_ids": [55596], "title": "Audi FIS Alpine Ski World Cup 2025/26 – Women’s Giant Slalom Kronplatz Stat Sheet", "sport": "alpine_skiing", "competition": "FIS World Cup", "event_name": "Giant Slalom", "gender": "W", "location": "Kronplatz", "event_date": "2026-10-27", "author_name": "Andrew Demo", "author_email": "", "status": "in_review", "editor_notes": "Complete demonstration sheet supplied for pilot review.", "created_at": "2026-07-19T09:30:00+00:00", "updated_at": "2026-07-19T14:20:00+00:00", "submitted_at": "2026-07-19T14:00:00+00:00", "approved_at": None, "stats": KRONPLATZ_CONTENT},
    {"id": "demo-submission-submitted", "fis_external_id": "wc-alp-w-sl-flachau-2026", "fis_event_ids": [55596], "title": "Slalom preview notes", "sport": "alpine_skiing", "competition": "FIS World Cup", "event_name": "Slalom", "gender": "W", "location": "Flachau", "event_date": "2026-12-13", "author_name": "Morgan Lee", "author_email": "", "status": "in_review", "editor_notes": "", "created_at": "2026-07-18T08:00:00+00:00", "updated_at": "2026-07-18T08:30:00+00:00", "submitted_at": "2026-07-18T08:30:00+00:00", "approved_at": None, "stats": [_block("stat-submitted-1", 0, "A third consecutive top-five finish would be a personal best run.", tags=["preview"])]},
    {"id": "demo-submission-approved", "fis_external_id": "wc-alp-m-dh-val-disere-2026", "fis_event_ids": [55596], "title": "Alpine weekend recap", "sport": "alpine_skiing", "competition": "FIS World Cup", "event_name": "Downhill", "gender": "M", "location": "Val d’Isère", "event_date": "2026-12-12", "author_name": "Alex Dupont", "author_email": "", "status": "approved", "editor_notes": "Demo pack approved.", "created_at": "2026-07-16T10:00:00+00:00", "updated_at": "2026-07-17T16:00:00+00:00", "submitted_at": "2026-07-16T11:00:00+00:00", "approved_at": "2026-07-17T16:00:00+00:00", "stats": [_block("stat-approved-1", 0, "Noa Martin earned a first World Cup win in this fictional demonstration.", tags=["milestone"])]},
]


def fresh_demo_data():
    submissions = deepcopy(SUBMISSIONS)
    for submission in submissions:
        submission.setdefault("amp_id", {"demo-submission-kronplatz": "560001", "demo-submission-submitted": "560002", "demo-submission-approved": "560003"}.get(submission["id"], ""))
        submission.setdefault("client_name", "FIS")
        submission.setdefault("season_code", 2026)
        submission.setdefault("researcher_user_id", "demo-user")
        submission.setdefault("researcher_name", "Jamie Laurent")
        submission.setdefault("sub_editor_user_id", "demo-sub-editor")
        submission.setdefault("sub_editor_name", "Nick L.")
        submission.setdefault("publication_deadline", "2026-10-25")
        submission.setdefault("researcher_deadline", "2026-10-24")
        submission.setdefault("working_notes", "")
        submission.setdefault("unused_stats", "")
        submission.setdefault("last_modified_by", submission.get("author_name", ""))
        if submission.get("status") in ("approved", "exported"):
            for block in submission.get("stats", []):
                block["accepted_at"] = submission.get("approved_at") or submission.get("updated_at")
                block["accepted_by_user_id"] = submission.get("sub_editor_user_id")
        if submission.get("fis_external_id", "").startswith("wc-alp-"):
            submission["fis_external_id"] = submission["fis_external_id"].replace("wc-alp-", "amp-alp-", 1)
    return submissions, deepcopy(ENTITIES)
