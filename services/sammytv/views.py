"""SammyTV pages and read-only approved-catalogue API."""
import os
from urllib.parse import urlencode

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request

from . import demo
from .auth import AccessDenied, current_viewer, require_parent, uuid_string
from .catalogue import checked_videos, embed_url, viewer_video
from .repository import CatalogueRepository, CatalogueUnavailable

blueprint = Blueprint('sammytv', __name__, url_prefix='/sammytv')


def is_api():
    return request.path.startswith('/sammytv/api/')


@blueprint.before_request
def catalogue_access():
    mode = os.getenv('SAMMYTV_MODE', 'preview')
    if mode not in ('preview', 'catalogue'):
        raise CatalogueUnavailable('Invalid SammyTV mode.')
    g.sammytv_preview = mode == 'preview'
    if g.sammytv_preview:
        if (is_api() or request.endpoint in ('sammytv.signin', 'sammytv.pair', 'sammytv.devices', 'sammytv.logout')
                or (request.endpoint or '').startswith('sammytv.admin_')):
            raise CatalogueUnavailable('The private catalogue is not enabled.')
        return
    g.sammytv_repository = CatalogueRepository()
    if request.endpoint not in ('sammytv.signin', 'sammytv.pair'):
        g.sammytv_viewer = current_viewer(g.sammytv_repository)


@blueprint.errorhandler(AccessDenied)
def access_error(error):
    if is_api():
        return jsonify(error='access_denied', message=str(error)), error.status_code
    return render_template('sammytv/unavailable.html', title='Your collection is private',
        message='Open /sammytv/signin for parent sign-in or /sammytv/pair to connect a viewer device.'), error.status_code


@blueprint.errorhandler(CatalogueUnavailable)
def catalogue_error(error):
    # Deliberately omit exception text, upstream bodies, search text and viewer IDs.
    current_app.logger.warning('SammyTV catalogue unavailable (%s)', type(error).__name__)
    if is_api():
        return jsonify(error='catalogue_unavailable', message='Your collection is temporarily unavailable.'), 503
    return render_template('sammytv/unavailable.html', title='We could not load your collection',
        message='Please try again shortly. No unreviewed videos will be shown.'), 503


def route_id(value):
    try:
        return uuid_string(value)
    except AccessDenied:
        abort(404)


def integer_arg(name, default, minimum, maximum):
    try:
        result = int(request.args.get(name, default))
    except (ValueError, TypeError):
        abort(400)
    if not minimum <= result <= maximum:
        abort(400)
    return result


def catalogue_filters(categories):
    # Identity always comes from a verified session, never from request selectors.
    if any(key in request.args for key in ('family_id', 'profile_id', 'member_id', 'url', 'provider_video_id')):
        abort(400)
    query = request.args.get('q', '').strip()
    if len(query) > 120:
        abort(400)
    category_name = request.args.get('category', 'All')
    category_id = None
    if category_name not in ('All', 'Favourites'):
        category = next((item for item in categories if item['name'] == category_name), None)
        if not category:
            abort(400)
        category_id = category['id']
    return {'query': query, 'category_id': category_id}


def context_for_page():
    if g.sammytv_preview:
        return dict(videos=demo.VIDEOS, channels=demo.CHANNELS, categories=demo.CATEGORIES,
            preview=True, brand_name='SammyTV', profile_initial='S', storage_scope='preview',
            previous_url=None, next_url=None, is_parent=False)
    repository, viewer = g.sammytv_repository, g.sammytv_viewer
    categories = repository.categories(viewer['family_id'])
    return dict(videos=[], channels=[], categories=['All'] + [c['name'] for c in categories] + ['Favourites'],
        category_records=categories, preview=False, brand_name=viewer['brand_name'],
        profile_initial=viewer['nickname'][:1].upper(), storage_scope=viewer['profile_id'],
        previous_url=None, next_url=None, is_parent=viewer['role'] == 'parent')


@blueprint.get('')
@blueprint.get('/')
@blueprint.get('/search')
@blueprint.get('/channels')
@blueprint.get('/favourites')
@blueprint.get('/history')
@blueprint.get('/requests')
@blueprint.get('/channel/<channel_id>')
@blueprint.get('/watch/<video_id>')
def page(channel_id=None, video_id=None):
    section = request.path.rstrip('/').split('/')[-1]
    if not g.sammytv_preview and section == 'admin':
        require_parent(g.sammytv_viewer)
    context = context_for_page()
    video = channel = None
    if g.sammytv_preview:
        video = next((v for v in demo.VIDEOS if v['id'] == video_id), None)
        channel = next((c for c in demo.CHANNELS if c['id'] == channel_id), None)
    else:
        repository, viewer = g.sammytv_repository, g.sammytv_viewer
        family_id = viewer['family_id']
        if section not in ('admin', 'requests', 'history'):
            context['channels'] = repository.channels(family_id)
            filters = catalogue_filters(context['category_records'])
            offset = (integer_arg('page', 1, 1, 209) - 1) * 48
            if channel_id:
                channel_id = route_id(channel_id)
                channel = next((c for c in context['channels'] if c['id'] == channel_id), None)
                filters['channel_id'] = channel_id
            if video_id:
                video_id = route_id(video_id)
                rows = checked_videos(repository, family_id, video_id=video_id, limit=1)
                video = viewer_video(rows[0]) if rows else None
            rows = checked_videos(repository, family_id, **filters, limit=49, offset=offset)
            context['videos'] = [viewer_video(row) for row in rows[:48]]
            if not video_id:
                args = {key: value for key, value in request.args.items() if key in ('q', 'category')}
                if offset:
                    context['previous_url'] = request.path + '?' + urlencode({**args, 'page': offset // 48})
                if len(rows) > 48 and offset < 9984:
                    context['next_url'] = request.path + '?' + urlencode({**args, 'page': offset // 48 + 2})
    if (video_id and not video) or (channel_id and not channel):
        abort(404)
    return render_template('sammytv/app.html', **context, video=video, channel=channel, section=section,
        playback_enabled=not g.sammytv_preview and os.getenv('SAMMYTV_YOUTUBE_PLAYBACK_ENABLED') == '1')


@blueprint.get('/api/catalogue')
def api_catalogue():
    repository, viewer = g.sammytv_repository, g.sammytv_viewer
    categories = repository.categories(viewer['family_id'])
    filters = catalogue_filters(categories)
    if request.args.get('channel_id'):
        filters['channel_id'] = route_id(request.args['channel_id'])
    limit = integer_arg('limit', 48, 1, 48)
    offset = integer_arg('offset', 0, 0, 10000)
    rows = checked_videos(repository, viewer['family_id'], **filters, limit=limit + 1, offset=offset)
    return jsonify(videos=[viewer_video(row) for row in rows[:limit]],
        categories=categories, has_more=len(rows) > limit, offset=offset, limit=limit)


@blueprint.get('/api/categories')
def api_categories():
    return jsonify(categories=g.sammytv_repository.categories(g.sammytv_viewer['family_id']))


@blueprint.get('/api/channels')
def api_channels():
    return jsonify(channels=g.sammytv_repository.channels(g.sammytv_viewer['family_id']))


def approved_video(video_id):
    rows = checked_videos(g.sammytv_repository, g.sammytv_viewer['family_id'],
                          video_id=route_id(video_id), limit=1)
    if not rows:
        abort(404)
    return rows[0]


@blueprint.get('/api/videos/<video_id>')
def api_video(video_id):
    return jsonify(video=viewer_video(approved_video(video_id)))


@blueprint.get('/api/videos/<video_id>/playback')
def api_playback(video_id):
    # Recheck approval at the moment the viewer clicks, not just at page load.
    row = approved_video(video_id)
    if os.getenv('SAMMYTV_YOUTUBE_PLAYBACK_ENABLED') != '1':
        return jsonify(error='playback_disabled', message='A parent needs to enable playback first.'), 403
    return jsonify(embed_url=embed_url(row))


@blueprint.after_request
def privacy_headers(response):
    playback = (not getattr(g, 'sammytv_preview', True)
                and os.getenv('SAMMYTV_YOUTUBE_PLAYBACK_ENABLED') == '1')
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin' if playback else 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; frame-src " + ('https://www.youtube-nocookie.com' if playback else "'none'") +
        "; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Cookie'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), autoplay=()'
    return response


from .sessions import register
register(blueprint)

from .moderation import register as register_moderation
register_moderation(blueprint)
