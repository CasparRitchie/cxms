"""Parent-only family management; all writes are atomic, family-scoped RPCs."""
import secrets
import time

import jwt
from flask import abort, g, make_response, redirect, render_template, request, url_for

from .auth import AccessDenied, require_parent
from .credentials import digest_code, nickname, password_hash, username
from .repository import ModerationConflict, ModerationDenied, ModerationInvalid
from .sessions import CSRF_COOKIE, check_csrf, csrf, secret


def render_family(*, message='', error='', code='', invitation='', status=200):
    viewer, repo = g.sammytv_viewer, g.sammytv_repository
    children = repo.family_children(viewer)
    for child in children:
        child['review_token'] = jwt.encode(dict(aud='sammytv:child-review',
            family_id=viewer['family_id'], parent_id=viewer['member_id'],
            child_id=child['child_id'], version=child['updated_at'], exp=int(time.time())+3600),
            secret(), algorithm='HS256')
    token = csrf()
    response = make_response(render_template('sammytv/family.html', brand_name=viewer['brand_name'],
        children=children, parents=repo.family_parents(viewer), viewer=viewer,
        csrf_token=token, message=message, error=error, code=code, invitation=invitation), status)
    response.set_cookie(CSRF_COOKIE,token,secure=True,httponly=True,samesite='Strict',path='/sammytv',max_age=3600)
    return response


def check_child_review():
    try:
        data = jwt.decode(request.form.get('review_token',''),secret(),algorithms=['HS256'],
            audience='sammytv:child-review',options={'require':['exp','family_id','parent_id','child_id','version']})
        viewer = g.sammytv_viewer
        if data['family_id'] != viewer['family_id'] or data['parent_id'] != viewer['member_id']:
            raise ModerationConflict()
        return data['child_id'],data['version']
    except jwt.PyJWTError:
        raise ModerationConflict() from None


def register(blueprint):
    @blueprint.route('/admin/family',methods=['GET','POST'])
    def family_accounts():
        require_parent(g.sammytv_viewer)
        if request.method == 'GET':
            return render_family(message='Family account updated.' if request.args.get('saved')=='1' else '')
        check_csrf()
        viewer,repo = g.sammytv_viewer,g.sammytv_repository
        action = request.form.get('action','')
        try:
            if action == 'create':
                login = username(request.form.get('username',''))
                display = nickname(request.form.get('nickname',''))
                if request.form.get('password') != request.form.get('password_confirm'):
                    raise ValueError('The passwords do not match.')
                hashed = password_hash(request.form.get('password',''))
                repo.manage_child(viewer,'create',username=login,nickname=display,password_hash=hashed)
            elif action == 'registration_code':
                code = secrets.token_urlsafe(24)
                repo.create_registration_code(viewer,digest_code(code))
                return render_family(code=code,message='Family code created. Share it privately with your children. It expires in seven days; a new code replaces the old one.')
            elif action == 'invite_parent':
                email = request.form.get('email','').strip().casefold()
                if (not 3 <= len(email) <= 254 or '@' not in email or any(c.isspace() for c in email)
                        or request.form.get('parent_confirmed') != 'yes'):
                    raise ValueError('Enter the parent’s email and confirm that they can manage this family’s collection and accounts.')
                invitation = secrets.token_urlsafe(24)
                repo.create_parent_invite(viewer,digest_code(invitation),email)
                return render_family(invitation=invitation,message='Invitation created. Share this code privately with that parent. It expires in 48 hours and can be used once.')
            elif action in ('approve','decline','disable','enable','reset_password'):
                child_id,version = check_child_review()
                if action=='approve' and request.form.get('child_confirmed') != 'yes':
                    raise ValueError('Confirm that you recognise this child and approve their account.')
                hashed = ''
                if action=='reset_password':
                    if request.form.get('password') != request.form.get('password_confirm'):
                        raise ValueError('The passwords do not match.')
                    hashed = password_hash(request.form.get('password',''))
                repo.manage_child(viewer,action,child_id=child_id,expected_updated_at=version,password_hash=hashed)
            else:
                abort(400)
        except ValueError as exc:
            return render_family(error=str(exc),status=400)
        except ModerationConflict:
            return render_family(error='This account changed or the form expired. Review its current details and try again.',status=409)
        except ModerationInvalid:
            return render_family(error='That change could not be saved. The username may already be taken, or the account’s status has changed.',status=400)
        except ModerationDenied:
            raise AccessDenied('Your parent access has changed. Sign in again.') from None
        return redirect(url_for('sammytv.family_accounts',saved='1'),code=303)
