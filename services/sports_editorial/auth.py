import os
from functools import wraps

from flask import abort, redirect, request, session, url_for

from .supabase_rest import SupabaseError, SupabaseRestClient


COOKIE_NAME = "cxms_sports_workspace_access"


def auth_configuration():
    mode = os.getenv("SPORTS_EDITORIAL_AUTH_MODE", "demo").strip().lower()
    return {"mode": "workspace" if mode == "workspace" else "demo", "configured": bool(os.getenv("SPORTS_EDITORIAL_JWT_SECRET"))}


def current_user():
    if auth_configuration()["mode"] == "demo":
        return {"id": "demo-user", "email": "", "full_name": session.get("sports_editorial_user", "Jamie Laurent"), "workspace_id": "demo-workspace", "role": session.get("sports_editorial_role", "journalist")}
    token = request.cookies.get(COOKIE_NAME)
    import jwt
    try:
        data = jwt.decode(token, os.environ["SPORTS_EDITORIAL_JWT_SECRET"], algorithms=["HS256"])
    except (KeyError, jwt.PyJWTError):
        return None
    if not data.get("sub") or not data.get("workspace_id"):
        return None
    return {"id": data["sub"], "email": data.get("email", ""), "full_name": data.get("full_name", ""), "workspace_id": data["workspace_id"], "role": data.get("role", "journalist")}


def require_workspace(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user():
            return view(*args, **kwargs)
        return redirect(url_for("sports_editorial_workspace.login", next=request.path))
    return wrapped


def require_role(role):
    user = current_user()
    if not user or user.get("role") != role:
        abort(403, description=f"{role.replace('_', ' ').title()} access is required.")


def authenticate(email, password):
    import bcrypt
    client = SupabaseRestClient()
    users = client.request("app_users", query={"select": "id,email,password_hash,full_name,is_active", "email": f"eq.{email.strip().lower()}", "limit": "1"})
    user = users[0] if users else None
    if not user or not user.get("is_active") or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return None
    memberships = client.request("workspace_members", query={"select": "workspace_id,role", "user_id": f"eq.{user['id']}", "limit": "1"})
    if not memberships:
        return None
    membership = memberships[0]
    editorial = client.request("sports_editorial_memberships", query={"select": "editorial_role,is_active", "workspace_id": f"eq.{membership['workspace_id']}", "user_id": f"eq.{user['id']}", "limit": "1"})
    if not editorial or not editorial[0].get("is_active"):
        return None
    return {"id": user["id"], "email": user["email"], "full_name": user.get("full_name", ""), "workspace_id": membership["workspace_id"], "role": editorial[0]["editorial_role"]}


def make_token(user):
    import jwt
    return jwt.encode({"sub": user["id"], "email": user["email"], "full_name": user["full_name"], "workspace_id": user["workspace_id"], "role": user["role"]}, os.environ["SPORTS_EDITORIAL_JWT_SECRET"], algorithm="HS256")
