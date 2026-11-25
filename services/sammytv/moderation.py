"""Parent-only moderation forms. No caller-selected family or provider metadata."""
import os
import time

import jwt
from flask import abort, g, make_response, redirect, render_template, request, url_for

from .auth import AccessDenied, require_parent, uuid_string
from .categories import category_name, suggest_categories
from .repository import CatalogueUnavailable, ModerationConflict, ModerationDenied, ModerationInvalid
from .sessions import CSRF_COOKIE, check_csrf, csrf, secret
from .youtube import VideoInputError, blocked_reasons, fetch_metadata, parse_video_url

STATUSES = ('pending', 'approved', 'hidden', 'rejected')
MESSAGES = {
    'added': 'Video added for review. It is not visible in the collection yet.',
    'exists': 'This video is already in your collection. Its approval has not changed.',
    'approved': 'Video approved. It is now in your reviewed collection.',
    'hidden': 'Video removed from the collection. You can review and approve it again later.',
    'changed': 'YouTube’s video details have changed. Review the updated details before approving.',
}
METADATA_FIELDS = ('provider_video_id', 'title', 'description', 'duration_seconds',
                   'available', 'embeddable', 'age_restricted', 'is_live')


def render_admin(*, item=None, message='', error='', status_code=200, form=None, managing_categories=False):
    viewer, repo = g.sammytv_viewer, g.sammytv_repository
    token = csrf()
    category_records = repo.categories(viewer['family_id'])
    context = dict(brand_name=viewer['brand_name'], item=item, csrf_token=token,
        message=message, error=error, category_records=category_records, statuses=STATUSES,
        lookup_configured=bool(os.getenv('SAMMYTV_YOUTUBE_API_KEY', '').strip()), form=form or {},
        managing_categories=managing_categories)
    if managing_categories:
        all_categories = repo.admin_categories(viewer['family_id'])
        if any(c.get('family_id') != viewer['family_id'] for c in all_categories):
            raise CatalogueUnavailable('Invalid parent category response.')
        context['all_categories'] = all_categories
    elif item:
        context['blocked'] = blocked_reasons(item)
        context['selected_categories'] = set((form or {}).get('category_ids',
            [link['category_id'] for link in item.get('category_links', [])]))
        context['review_token'] = jwt.encode(dict(video_id=item['id'], family_id=viewer['family_id'],
            member_id=viewer['member_id'], version=item['updated_at'], aud='sammytv:review',
            exp=int(time.time()) + 3600), secret(), algorithm='HS256')
        context['suggestions'] = suggest_categories(item, category_records)
    else:
        status = request.args.get('status', 'pending')
        if status not in (*STATUSES, 'all'):
            abort(400)
        try:
            page = int(request.args.get('page', '1'))
        except ValueError:
            abort(400)
        if not 1 <= page <= 417:
            abort(400)
        items = repo.admin_videos(viewer['family_id'], status=None if status == 'all' else status,
                                 offset=(page - 1) * 24)
        if any(row.get('family_id') != viewer['family_id'] for row in items):
            raise CatalogueUnavailable('Invalid parent catalogue response.')
        context.update(items=items[:24], has_more=len(items) > 24, page=page, status=status)
    response = make_response(render_template('sammytv/admin.html', **context), status_code)
    response.set_cookie(CSRF_COOKIE, token, secure=True, httponly=True,
                        samesite='Strict', path='/sammytv', max_age=3600)
    return response


def get_video(video_id):
    try:
        video_id = uuid_string(video_id)
    except AccessDenied:
        abort(404)
    viewer = g.sammytv_viewer
    rows = g.sammytv_repository.admin_videos(viewer['family_id'], video_id=video_id)
    if not rows or rows[0].get('family_id') != viewer['family_id'] or rows[0].get('id') != video_id:
        abort(404)
    return rows[0]


def check_review(item):
    try:
        claims = jwt.decode(request.form.get('review_token', ''), secret(), algorithms=['HS256'],
            audience='sammytv:review', options={'require': ['exp', 'family_id', 'member_id', 'video_id', 'version']})
    except jwt.PyJWTError:
        raise ModerationConflict() from None
    viewer = g.sammytv_viewer
    if (claims['family_id'], claims['member_id'], claims['video_id'], claims['version']) != (
            viewer['family_id'], viewer['member_id'], item['id'], item['updated_at']):
        raise ModerationConflict()


def register(blueprint):
    @blueprint.get('/admin')
    def admin():
        if g.sammytv_preview:
            from .views import page
            return page()
        require_parent(g.sammytv_viewer)
        return render_admin()

    @blueprint.route('/admin/categories', methods=['GET', 'POST'])
    def admin_categories():
        require_parent(g.sammytv_viewer)
        if request.method == 'GET':
            messages = {'created': 'Category added.', 'saved': 'Category updated.',
                        'archived': 'Category archived. Videos stay in your collection.',
                        'restored': 'Category restored.'}
            return render_admin(managing_categories=True, message=messages.get(request.args.get('result'), ''))
        check_csrf()
        action = request.form.get('action')
        if action not in ('create', 'save', 'archive', 'restore'):
            abort(400)
        try:
            name = category_name(request.form.get('name', '')) if action in ('create', 'save') else ''
            position = request.form.get('position', '')
            try:
                position = int(position) if position else None
            except ValueError:
                raise ValueError('Enter a whole number for the order.') from None
            if position is not None and not 0 <= position <= 9999:
                raise ValueError('Order must be between 0 and 9999.')
            try:
                category_id = None if action == 'create' else uuid_string(request.form.get('category_id'))
            except AccessDenied:
                abort(404)
            g.sammytv_repository.manage_category(g.sammytv_viewer, action,
                category_id=category_id, name=name, position=position)
        except ValueError as exc:
            return render_admin(managing_categories=True, error=str(exc), status_code=400)
        except ModerationInvalid:
            return render_admin(managing_categories=True, error='That name may already be in use. Check archived categories too, and restore one if needed.', status_code=400)
        except ModerationDenied:
            raise AccessDenied('This category or your parent access is unavailable.') from None
        result = {'create': 'created', 'save': 'saved', 'archive': 'archived', 'restore': 'restored'}[action]
        return redirect(url_for('sammytv.admin_categories', result=result), code=303)

    @blueprint.post('/admin/videos')
    def admin_import():
        require_parent(g.sammytv_viewer)
        check_csrf()
        try:
            metadata = fetch_metadata(parse_video_url(request.form.get('video_url', '')))
            result = g.sammytv_repository.import_video(g.sammytv_viewer, metadata)
        except VideoInputError as exc:
            return render_admin(error=str(exc), status_code=400,
                                form={'video_url': request.form.get('video_url', '')[:2048]})
        except ModerationDenied:
            raise AccessDenied('Your parent access has changed. Sign in again.') from None
        except ModerationInvalid:
            return render_admin(error='This video could not be added. Check the link and try again.', status_code=400)
        return redirect(url_for('sammytv.admin_review', video_id=result['video_id'],
                                result='added' if result['added'] else 'exists'), code=303)

    @blueprint.route('/admin/videos/<video_id>', methods=['GET', 'POST'])
    def admin_review(video_id):
        require_parent(g.sammytv_viewer)
        if request.method == 'POST':
            check_csrf()
        item = get_video(video_id)
        if request.method == 'GET':
            return render_admin(item=item, message=MESSAGES.get(request.args.get('result'), ''))
        category_ids = request.form.getlist('category_ids')
        notes = request.form.get('notes', '')
        form = dict(category_ids=category_ids, notes=notes)
        try:
            check_review(item)
            action = request.form.get('action') or ('add_category' if 'suggested_category' in request.form else None)
            if action not in ('approve', 'hide', 'add_category', 'refresh'):
                abort(400)
            viewer, repo = g.sammytv_viewer, g.sammytv_repository
            if action == 'hide':
                repo.moderate_video(viewer, item, 'hide')
                return redirect(url_for('sammytv.admin_review', video_id=video_id, result='hidden'), code=303)
            if action == 'refresh':
                if len(notes) > 10000 or len(category_ids) > 50:
                    return render_admin(item=item, error='Check the selected categories and keep notes under 10,000 characters.', status_code=400)
                metadata = fetch_metadata(item['provider_video_id'])
                if metadata['provider_channel_id'] != item['channel']['provider_channel_id']:
                    raise VideoInputError('The video’s channel has changed. Remove it and check the original link.')
                changed = any(metadata[key] != item[key] for key in METADATA_FIELDS)
                if changed:
                    repo.moderate_video(viewer, item, 'refresh', metadata=metadata)
                return render_admin(item=get_video(video_id), form=form,
                    message='Video details updated. Review the current details and restrictions before approving.' if changed
                            else 'Video details checked. Any current playback restrictions are shown below.')
            valid = {c['id'] for c in repo.categories(viewer['family_id'])}
            if action == 'add_category':
                try:
                    name = category_name(request.form.get('suggested_category') or request.form.get('new_category_name', ''))
                except ValueError as exc:
                    return render_admin(item=item, error=str(exc), status_code=400, form=form)
                if len(notes) > 10000 or len(category_ids) > 50 or not set(category_ids) <= valid:
                    return render_admin(item=item, error='Check the selected categories and keep notes under 10,000 characters.', status_code=400, form=form)
                result = repo.manage_category(viewer, 'create', name=name)
                form['category_ids'] = list(dict.fromkeys(category_ids + [result['category_id']]))
                return render_admin(item=item, message='Category added and selected. Save approval to assign your selected categories to this video.', form=form)
            if (request.form.get('reviewed') != 'yes' or not 1 <= len(category_ids) <= 50
                    or not set(category_ids) <= valid or len(notes) > 10000):
                return render_admin(item=item, error='Choose a category and confirm you have watched and reviewed this video. Notes can be up to 10,000 characters.',
                                    status_code=400, form=form)
            metadata = fetch_metadata(item['provider_video_id'])
            if metadata['provider_channel_id'] != item['channel']['provider_channel_id']:
                raise VideoInputError('The video’s channel has changed. Remove it and check the original link.')
            if any(metadata[key] != item[key] for key in METADATA_FIELDS):
                repo.moderate_video(viewer, item, 'refresh', metadata=metadata)
                return redirect(url_for('sammytv.admin_review', video_id=video_id, result='changed'), code=303)
            reasons = blocked_reasons(dict(metadata, channel=item['channel']))
            if reasons:
                return render_admin(item=item, error=' '.join(reasons), status_code=400, form=form)
            repo.moderate_video(viewer, item, 'approve', metadata=metadata,
                                category_ids=category_ids, notes=notes)
        except VideoInputError as exc:
            return render_admin(item=item, error=str(exc), status_code=400, form=form)
        except ModerationConflict:
            # Reload for a fresh token; a stale action can never undo another action.
            return render_admin(item=get_video(video_id), error='This review has expired or the video changed in another tab. Check the current details and try again.', status_code=409)
        except ModerationDenied:
            raise AccessDenied('Your parent access has changed. Sign in again.') from None
        except ModerationInvalid:
            if action == 'add_category':
                return render_admin(item=get_video(video_id), error='That name may already be used by an archived category. Open Manage all categories to restore it, or choose another name.', status_code=400, form=form)
            return render_admin(item=get_video(video_id), error='This video or category is no longer available for approval. Review the current details.', status_code=400)
        return redirect(url_for('sammytv.admin_review', video_id=video_id, result='approved'), code=303)
