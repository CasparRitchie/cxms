"""Catalogue boundary: duplicate key visibility checks before rendering or playback."""
import re
from urllib.parse import urlencode

from .repository import CatalogueUnavailable

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
CHANNEL_ID = re.compile(r'^UC[A-Za-z0-9_-]{22}$')


def is_visible(row, family_id):
    if not isinstance(row, dict):
        return False
    channel = row.get('channel') or {}
    if not isinstance(channel, dict) or not isinstance(row.get('categories'), list):
        return False
    if not all(isinstance(row.get(key), str) for key in ('id', 'title', 'description', 'provider_video_id')):
        return False
    if (type(row.get('duration_seconds')) is not int or row['duration_seconds'] < 0 or
            not isinstance(channel.get('name'), str) or not channel['name'].strip() or
            not isinstance(channel.get('id'), str) or
            any(not isinstance(c, dict) or not isinstance(c.get('name'), str) for c in row['categories'])):
        return False
    camera = row.get('live_camera', False)
    if type(camera) is not bool:
        return False
    approved_type = (row.get('is_live') is False and camera is False) or (
        camera is True and row.get('is_live') is True
        and row.get('camera_video_id') == row.get('provider_video_id')
        and isinstance(row.get('camera_channel_id'), str)
        and bool(CHANNEL_ID.fullmatch(row['camera_channel_id']))
        and row['camera_channel_id'] == channel.get('provider_channel_id'))
    return (row.get('family_id') == family_id and row.get('status') == 'approved'
            and bool(row.get('approved_by')) and bool(row.get('approved_at'))
            and row.get('available') is True and row.get('embeddable') is True
            and row.get('age_restricted') is False and approved_type
            and row.get('provider') == 'youtube'
            and bool(VIDEO_ID.fullmatch(row.get('provider_video_id', '')))
            and channel.get('family_id') == family_id and channel.get('enabled') is True)


def viewer_video(row):
    """Explicit public projection: no approval identities, family IDs or provider IDs."""
    seconds = max(0, int(row['duration_seconds']))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    channel = row['channel']
    categories = [category['name'] for category in row['categories']]
    kind = 'plane' if 'Planes' in categories else 'comedy' if 'Comedy' in categories else 'train'
    return {'id': row['id'], 'title': row['title'], 'description': row['description'],
            'duration': 'LIVE' if row.get('live_camera') else f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes}:{seconds:02d}',
            'channel': {'id': channel['id'], 'name': channel['name'],
                        'initials': ''.join(word[0] for word in channel['name'].split()[:2]).upper()},
            'categories': categories, 'approved_at': row['approved_at'],
            'kind': kind, 'caption': '', 'is_camera': row.get('live_camera') is True}


def checked_videos(repository, family_id, **filters):
    rows = repository.videos(family_id, **filters)
    if any(not is_visible(row, family_id) for row in rows):
        # A bad adapter/RPC result is an incident, not a reason to show partial data.
        raise CatalogueUnavailable('Catalogue visibility check failed.')
    return rows


def embed_url(row):
    # Called only after a fresh approved-catalogue lookup; never from a caller's URL.
    return 'https://www.youtube-nocookie.com/embed/' + row['provider_video_id'] + '?' + urlencode({
        'autoplay': 0, 'rel': 0, 'playsinline': 1, 'fs': 1,
    })
