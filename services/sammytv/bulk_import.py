"""Resumable, pending-only imports using the same adapter as parent forms."""
from .auth import uuid_string
from .categories import suggest_categories
from .repository import CatalogueUnavailable, ModerationConflict, ModerationDenied, ModerationInvalid
from .youtube import VideoInputError, blocked_reasons, fetch_metadata, parse_video_url

MAX_LINKS = 250


def normalize_links(lines):
    entries, errors, seen, duplicates = [], [], set(), 0
    for line_number, line in enumerate(lines, 1):
        value = line.strip()
        if not value or value.startswith('#'):
            continue
        if len(entries) + len(errors) + duplicates >= MAX_LINKS:
            raise ValueError('Import at most 250 links per run. Split larger lists into files.')
        try:
            video_id = parse_video_url(value)
        except VideoInputError as exc:
            errors.append(dict(line=line_number, error=str(exc)))
            continue
        if video_id in seen:
            duplicates += 1
            continue
        seen.add(video_id)
        entries.append(dict(video_id=video_id, line=line_number))
    if not entries and not errors:
        raise ValueError('The file contains no video links.')
    return entries, errors, duplicates


def import_links(repository, parent, entries, *, dry_run=False, on_result=None):
    """Each RPC commits independently. Re-running cannot reset an approval."""
    results = []
    categories = repository.categories(parent['family_id'])
    for entry in entries:
        result = dict(entry)
        try:
            metadata = fetch_metadata(entry['video_id'])
            result.update(title=metadata['title'],
                suggestions=[s['name'] for s in suggest_categories(metadata, categories)],
                blocked=blocked_reasons(metadata))
            if dry_run:
                result['outcome'] = 'checked'
            else:
                record = repository.import_video(parent, metadata)
                result.update(outcome='added' if record['added'] else 'exists',
                              catalogue_id=record['video_id'])
        except ModerationDenied:
            # Stop immediately if the parent is revoked while a batch is running.
            raise
        except VideoInputError as exc:
            result.update(outcome='failed', error=str(exc))
        except (CatalogueUnavailable, ModerationConflict, ModerationInvalid):
            result.update(outcome='failed', error='The database could not add this video. It is safe to retry.')
        results.append(result)
        if on_result:
            on_result(result)
    return results


def select_parent(repository, member_id=None):
    if member_id:
        member_id = uuid_string(member_id)
    rows = repository.import_parents(member_id)
    if len(rows) != 1:
        raise ValueError('Choose an active SammyTV parent using --parent-member-id; automatic selection needs exactly one parent.')
    member = rows[0]
    if (member.get('role') != 'parent' or member.get('active') is not True
            or type(member.get('session_version')) is not int
            or (member_id and member.get('id') != member_id)):
        raise ValueError('An active SammyTV parent is required.')
    family = repository.family(member['family_id'])
    if not family or family.get('id') != member['family_id'] or family.get('enabled') is not True:
        raise ValueError('The parent’s family is unavailable.')
    return dict(member_id=member['id'], family_id=member['family_id'], role='parent',
                session_version=member['session_version'])
