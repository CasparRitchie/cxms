"""Editable category names and lightweight metadata suggestions; no paid AI service."""
import re
import unicodedata

RESERVED = {'all', 'favourites'}
TOPICS = (
    ('Trains', r'\b(trains?|railways?|railroads?|locomotives?|eurostar|tgv|sncf|ferroviaire)\b'),
    ('Planes', r'\b(planes?|aeroplanes?|airplanes?|aircraft|aviation|airbus|boeing|airports?|avions?|flights?)\b'),
    ('Model railways', r'\b(model railways?|model trains?|hornby|bachmann|märklin|marklin)\b'),
    ('Flight simulation', r'\b(flight sim(?:ulator)?|msfs|x-plane|infinite flight)\b'),
    ('Train simulation', r'\b(train sim(?:ulator| world)?|trainz)\b'),
    ('Gaming', r'\b(gaming|gameplay|minecraft|roblox|fortnite|grand theft auto|cities:? skylines)\b'),
    ('Roblox', r'\broblox\b'),
    ('Minecraft', r'\bminecraft\b'),
    ('Cities: Skylines', r'\bcities:? skylines\b'),
    ('Food & cooking', r'\b(cooking|recipes?|baking|burgers?|mac and cheese|chefs?|food)\b'),
    ('Animation & memes', r'\b(animation|animated|memes?)\b'),
    ('Comedy', r'\b(comedy|comedian|funny|humou?r|hilarious|skits?|pranks?)\b'),
    ('Music', r'\b(music|concert|orchestra|guitar|piano|drumming|drummer)\b'),
    ('Science & engineering', r'\b(science|engineering|physics|rockets?|spacecraft)\b'),
    ('Nature', r'\b(nature|wildlife|animals?|birds?|ocean|forests?)\b'),
    ('History', r'\b(history|historical|archaeology|ancient)\b'),
)


def category_name(value):
    if not isinstance(value, str) or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Use a category name without control characters.')
    value = ' '.join(unicodedata.normalize('NFC', value).split())
    if not 1 <= len(value) <= 60:
        raise ValueError('Category names must contain 1–60 characters.')
    if value.casefold() in RESERVED:
        raise ValueError('All and Favourites are navigation controls. Choose another category name.')
    return value


def suggest_categories(video, categories=()):
    """Suggestions are labels to review, never approvals or content assessments."""
    creator = video.get('channel_name') or (video.get('channel') or {}).get('name', '')
    prominent = video.get('title', '') + ' ' + creator
    description = video.get('description', '')[:2000]
    existing = {c['name'].casefold(): c for c in categories if c.get('enabled', True)}
    candidates = []
    for category in existing.values():
        pattern = r'(?<!\w)' + re.escape(category['name']) + r'(?!\w)'
        if re.search(pattern, prominent, re.I) or re.search(pattern, description, re.I):
            candidates.append((4, category['name'], 'Matches your video’s title, description or creator'))
    for name, pattern in TOPICS:
        score = 3 if re.search(pattern, prominent, re.I) else 1 if re.search(pattern, description, re.I) else 0
        if score:
            candidates.append((score, name, 'Suggested from the title, description or creator'))
    result, seen = [], set()
    for _, name, reason in sorted(candidates, key=lambda item: -item[0]):
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        current = existing.get(name.casefold())
        result.append(dict(name=current['name'] if current else name,
                           category_id=current['id'] if current else None, reason=reason))
        if len(result) == 4:
            break
    try:
        name = category_name(creator)
    except ValueError:
        return result
    if name.casefold() not in seen:
        current = existing.get(name.casefold())
        result.append(dict(name=current['name'] if current else name,
                           category_id=current['id'] if current else None, reason='Video creator'))
    return result
