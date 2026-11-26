"""Fixed-host YouTube metadata lookups. Never fetch a parent-supplied URL."""
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')
CHANNEL_ID = re.compile(r'UC[A-Za-z0-9_-]{22}')
DURATION = re.compile(r'P(?:(\d+)D)?(?:T(?=\d)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?')


class VideoInputError(ValueError):
    """Messages are fixed, parent-safe strings."""


class MetadataUnavailable(VideoInputError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_video_url(value):
    value = value.strip()
    if not value or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise VideoInputError('Paste a link to one YouTube video.')
    try:
        parts = urlsplit(value)
        if (parts.scheme != 'https' or parts.username or parts.password or parts.port is not None
                or parts.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be')):
            raise ValueError
        query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=30)
        if 'list' in query:
            raise VideoInputError('Use an individual video link without a playlist.')
        if parts.hostname == 'youtu.be':
            video_id = parts.path.removeprefix('/')
        elif parts.path == '/watch' and len(query.get('v', [])) == 1:
            video_id = query['v'][0]
        elif re.fullmatch(r'/(?:shorts|embed|live)/[A-Za-z0-9_-]{11}', parts.path):
            video_id = parts.path.split('/')[-1]
        else:
            raise ValueError
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError
        return video_id
    except (ValueError, TypeError) as exc:
        if isinstance(exc, VideoInputError):
            raise
        raise VideoInputError('Use an https://www.youtube.com/watch?v=… or https://youtu.be/… video link.') from None


def duration_seconds(value):
    match = DURATION.fullmatch(value) if isinstance(value, str) else None
    if not match or not any(v is not None for v in match.groups()):
        raise MetadataUnavailable('YouTube did not provide a valid video duration. Try another video.')
    days, hours, minutes, seconds = (int(v or 0) for v in match.groups())
    result = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if result > 2147483647:
        raise MetadataUnavailable('This video is too long to add.')
    return result


def live_or_unconfirmed(item):
    """An ended broadcast is a recording; an unconfirmed end stays blocked."""
    if item['snippet']['liveBroadcastContent'] != 'none':
        return True
    if 'liveStreamingDetails' not in item:
        return False
    broadcast = item['liveStreamingDetails']
    if not isinstance(broadcast, dict):
        return True
    try:
        end = datetime.fromisoformat(broadcast['actualEndTime'].replace('Z', '+00:00'))
        if end.tzinfo is None or end > datetime.now(timezone.utc):
            return True
        if 'actualStartTime' in broadcast:
            start = datetime.fromisoformat(broadcast['actualStartTime'].replace('Z', '+00:00'))
            if start.tzinfo is None or start >= end:
                return True
        return False
    except (KeyError, TypeError, ValueError, AttributeError):
        return True


def broadcast_state(item):
    state = item['snippet']['liveBroadcastContent']
    broadcast = item.get('liveStreamingDetails', {})
    if state == 'live' and (not isinstance(broadcast, dict) or 'actualEndTime' in broadcast):
        return 'unconfirmed'
    if state in ('live', 'upcoming'):
        return state
    if 'liveStreamingDetails' not in item:
        return 'recording'
    return 'unconfirmed' if live_or_unconfirmed(item) else 'ended'


def fetch_metadata(video_id):
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        raise VideoInputError('The video identifier is invalid.')
    key = os.getenv('SAMMYTV_YOUTUBE_API_KEY', '').strip()
    if not key:
        raise MetadataUnavailable('Video lookup needs setup. Add SAMMYTV_YOUTUBE_API_KEY in Heroku to continue.')
    # Only the validated ID is sent. No pasted URL, family identity or search text.
    url = 'https://www.googleapis.com/youtube/v3/videos?' + urlencode({
        'part': 'snippet,contentDetails,status,liveStreamingDetails', 'id': video_id})
    req = Request(url, headers={'X-Goog-Api-Key': key, 'Accept': 'application/json'})
    try:
        with build_opener(NoRedirects()).open(req, timeout=8) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ValueError
        if not data['items']:
            raise VideoInputError('YouTube could not find this video. It may be private, deleted or unavailable.')
        if len(data['items']) != 1:
            raise ValueError
        item = data['items'][0]
        snippet, details, status = item['snippet'], item['contentDetails'], item['status']
        if item['id'] != video_id or snippet['liveBroadcastContent'] not in ('none', 'live', 'upcoming'):
            raise ValueError
        values = {key: snippet[key] for key in ('title', 'description', 'channelId', 'channelTitle')}
        if (not all(isinstance(v, str) for v in values.values())
                or not 1 <= len(values['title'].strip()) <= 300
                or len(values['description']) > 10000
                or not 1 <= len(values['channelTitle'].strip()) <= 200
                or not CHANNEL_ID.fullmatch(values['channelId'])
                or type(status['embeddable']) is not bool
                or not isinstance(status['privacyStatus'], str)
                or not isinstance(status['uploadStatus'], str)
                or not isinstance(details.get('contentRating', {}), dict)):
            raise ValueError
        state = broadcast_state(item)
        # Ongoing streams can remain "uploaded" until their recording is processed.
        # Only YouTube's explicit live state permits that status. Recordings still
        # need "processed"; failed/rejected/deleted/unknown statuses stay blocked.
        ready = status['uploadStatus'] == 'processed' or (state == 'live' and status['uploadStatus'] == 'uploaded')
        return dict(provider_video_id=video_id, provider_channel_id=values['channelId'],
            title=values['title'], description=values['description'], channel_name=values['channelTitle'],
            duration_seconds=duration_seconds(details['duration']),
            available=status['privacyStatus'] == 'public' and ready
                      and not details.get('regionRestriction'),
            embeddable=status['embeddable'],
            age_restricted=bool(details.get('contentRating', {}).get('ytRating')),
            is_live=live_or_unconfirmed(item), broadcast_state=state)
    except VideoInputError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, AttributeError):
        # Never surface provider bodies, request headers, URLs or the API key.
        raise MetadataUnavailable('YouTube could not check this video just now. Check the API key and quota, then try again.') from None


def blocked_reasons(video, *, allow_live_camera=False):
    reasons = []
    if video.get('available') is not True:
        reasons.append('The video is not publicly available without regional restrictions.')
    if video.get('embeddable') is not True:
        reasons.append('YouTube does not allow this video to play on other websites. It cannot play inside SammyTV.')
    if video.get('age_restricted') is not False:
        reasons.append('YouTube reports an age restriction.')
    if video.get('is_live') is not False and not allow_live_camera:
        reasons.append('This broadcast is live, upcoming, or has not been confirmed as ended. Recheck its details once it has finished.')
    if video.get('channel', {}).get('enabled') is False:
        reasons.append('This channel is disabled in your collection.')
    return reasons
