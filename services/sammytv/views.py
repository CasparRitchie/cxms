"""Isolated, synthetic SammyTV interface. No workspace or provider access."""
from flask import Blueprint, abort, render_template, request

blueprint = Blueprint('sammytv', __name__, url_prefix='/sammytv')
CATEGORIES = ['All', 'Trains', 'Planes', 'Lucas Ivkovic', 'Comedy', 'Live cameras', 'Favourites']
CHANNELS = [
    {'id': 'rail', 'name': 'The Railway Collection', 'initials': 'RC', 'colour': '#357c91'},
    {'id': 'air', 'name': 'Aviation Journal', 'initials': 'AJ', 'colour': '#7766ad'},
    {'id': 'comedy', 'name': 'Comedy collection', 'initials': 'CC', 'colour': '#bd6945'},
    {'id': 'live', 'name': 'Lineside Live', 'initials': 'LL', 'colour': '#50866b'},
]
# Invented editorial examples, not real uploads or parent-approved content.
VIDEO_SPECS = [
    ('coast', 'Along the coast: a railway journey to remember', 'rail', ['Trains'], '24:18', 'COASTAL JOURNEYS', '#377f98'),
    ('flight', 'A window seat above the clouds', 'air', ['Planes'], '18:42', 'ABOVE THE CLOUDS', '#6886b7'),
    ('station', 'An afternoon at the station | Lineside camera', 'live', ['Trains', 'Live cameras'], 'LIVE', 'AT THE STATION', '#698d76'),
    ('express', 'Full speed: the world of high-speed trains', 'rail', ['Trains'], '16:05', 'HIGH SPEED', '#b56849'),
    ('landing', 'On the runway: spectacular aircraft arrivals', 'air', ['Planes'], '21:36', 'CLEARED TO LAND', '#7a729e'),
    ('comedy', 'A little comedy for your afternoon', 'comedy', ['Comedy'], '08:24', 'TAKE A BREAK', '#b68a48'),
    ('mountain', 'Through the mountains by rail', 'rail', ['Trains'], '32:10', 'THE SCENIC ROUTE', '#48796c'),
    ('cockpit', 'How does an aircraft take to the skies?', 'air', ['Planes'], '12:48', 'READY FOR TAKEOFF', '#557f9e'),
    ('evening', 'The last train home: an evening journey', 'rail', ['Trains'], '26:04', 'AFTER HOURS', '#7f668c'),
]
VIDEOS = [dict(id=i, title=t, channel=next(c for c in CHANNELS if c['id'] == ch), categories=cat, duration=d, caption=cap, colour=col, kind='plane' if 'Planes' in cat else 'comedy' if 'Comedy' in cat else 'train') for i,t,ch,cat,d,cap,col in VIDEO_SPECS]


@blueprint.get('')
@blueprint.get('/')
@blueprint.get('/search')
@blueprint.get('/channels')
@blueprint.get('/favourites')
@blueprint.get('/history')
@blueprint.get('/requests')
@blueprint.get('/admin')
@blueprint.get('/channel/<channel_id>')
@blueprint.get('/watch/<video_id>')
def page(channel_id=None, video_id=None):
    video = next((v for v in VIDEOS if v['id'] == video_id), None)
    channel = next((c for c in CHANNELS if c['id'] == channel_id), None)
    if (video_id and not video) or (channel_id and not channel):
        abort(404)
    section = request.path.rstrip('/').split('/')[-1]
    return render_template('sammytv/app.html', videos=VIDEOS, channels=CHANNELS,
                           categories=CATEGORIES, video=video, channel=channel, section=section)


@blueprint.after_request
def privacy_headers(response):
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
    return response
