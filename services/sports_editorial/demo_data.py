from copy import deepcopy


ENTITIES = [
    {"id": "entity-athlete-lena", "entity_type": "athlete", "name": "Lena Berg (Demo)", "canonical_id": "demo-athlete-101", "canonical_url": "https://example.com/athletes/lena-berg", "country_code": "SWE"},
    {"id": "entity-athlete-mateo", "entity_type": "athlete", "name": "Mateo Rossi (Demo)", "canonical_id": "demo-athlete-102", "canonical_url": "https://example.com/athletes/mateo-rossi", "country_code": "ITA"},
    {"id": "entity-athlete-noa", "entity_type": "athlete", "name": "Noa Martin (Demo)", "canonical_id": "demo-athlete-103", "canonical_url": "https://example.com/athletes/noa-martin", "country_code": "FRA"},
    {"id": "entity-country-fr", "entity_type": "country", "name": "France", "canonical_id": "FRA", "canonical_url": "", "country_code": "FRA"},
    {"id": "entity-country-it", "entity_type": "country", "name": "Italy", "canonical_id": "ITA", "canonical_url": "", "country_code": "ITA"},
    {"id": "entity-country-se", "entity_type": "country", "name": "Sweden", "canonical_id": "SWE", "canonical_url": "", "country_code": "SWE"},
    {"id": "entity-country-ch", "entity_type": "country", "name": "Switzerland", "canonical_id": "SUI", "canonical_url": "", "country_code": "SUI"},
    {"id": "entity-competition-world-cup", "entity_type": "competition", "name": "FIS World Cup (Demo)", "canonical_id": "demo-competition-01", "canonical_url": "https://example.com/competitions/world-cup", "country_code": ""},
    {"id": "entity-event-downhill", "entity_type": "event", "name": "Men's Downhill (Demo)", "canonical_id": "demo-event-01", "canonical_url": "https://example.com/events/downhill", "country_code": "FRA"},
    {"id": "entity-event-slalom", "entity_type": "event", "name": "Women's Slalom (Demo)", "canonical_id": "demo-event-02", "canonical_url": "https://example.com/events/slalom", "country_code": "SUI"},
]


SUBMISSIONS = [
    {
        "id": "demo-submission-review", "title": "Race notes: Val d'Isere", "sport": "alpine_skiing",
        "competition": "FIS World Cup (Demo)", "event_name": "Men's Downhill (Demo)", "event_date": "2026-12-12",
        "author_name": "Jamie Laurent", "author_email": "jamie@example.com", "status": "in_review",
        "editor_notes": "Check return-from-injury wording before approval.", "created_at": "2026-07-17T09:30:00+00:00",
        "updated_at": "2026-07-18T14:20:00+00:00", "submitted_at": "2026-07-18T14:00:00+00:00", "approved_at": None,
        "stats": [
            {"id": "stat-review-1", "sort_order": 0, "stat_text": "First podium since returning from injury.", "edited_text": "", "editor_comment": "Confirm the return date.", "entity_ids": ["entity-athlete-mateo", "entity-country-it"]},
            {"id": "stat-review-2", "sort_order": 1, "stat_text": "Fastest final sector of the field.", "edited_text": "Recorded the fastest final sector in the field.", "editor_comment": "", "entity_ids": ["entity-event-downhill"]},
        ],
    },
    {
        "id": "demo-submission-submitted", "title": "Slalom preview notes", "sport": "alpine_skiing",
        "competition": "FIS World Cup (Demo)", "event_name": "Women's Slalom (Demo)", "event_date": "2026-12-13",
        "author_name": "Morgan Lee", "author_email": "morgan@example.com", "status": "submitted", "editor_notes": "",
        "created_at": "2026-07-18T08:00:00+00:00", "updated_at": "2026-07-18T08:30:00+00:00", "submitted_at": "2026-07-18T08:30:00+00:00", "approved_at": None,
        "stats": [{"id": "stat-submitted-1", "sort_order": 0, "stat_text": "A third consecutive top-five finish would be a personal best run.", "edited_text": "", "editor_comment": "", "entity_ids": ["entity-athlete-lena", "entity-event-slalom"]}],
    },
    {
        "id": "demo-submission-approved", "title": "Alpine weekend recap", "sport": "alpine_skiing",
        "competition": "FIS World Cup (Demo)", "event_name": "Men's Downhill (Demo)", "event_date": "2026-12-12",
        "author_name": "Alex Dupont", "author_email": "alex@example.com", "status": "approved", "editor_notes": "Demo pack approved.",
        "created_at": "2026-07-16T10:00:00+00:00", "updated_at": "2026-07-17T16:00:00+00:00", "submitted_at": "2026-07-16T11:00:00+00:00", "approved_at": "2026-07-17T16:00:00+00:00",
        "stats": [{"id": "stat-approved-1", "sort_order": 0, "stat_text": "Noa Martin earned a first demo World Cup win.", "edited_text": "Noa Martin earned a first World Cup win in this fictional demonstration.", "editor_comment": "Clarified demo context.", "entity_ids": ["entity-athlete-noa", "entity-country-fr", "entity-competition-world-cup"]}],
    },
]


def fresh_demo_data():
    return deepcopy(SUBMISSIONS), deepcopy(ENTITIES)
