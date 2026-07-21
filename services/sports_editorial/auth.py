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
    return {"id": data["sub"], "email": data.get("email", ""), "full_name": data.get("full_name", ""), "workspace_id": data["workspace_id"], "role": data.get("role", "journalist"), "workspace_role": data.get("workspace_role", "member")}


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
    return {"id": user["id"], "email": user["email"], "full_name": user.get("full_name", ""), "workspace_id": membership["workspace_id"], "role": editorial[0]["editorial_role"], "workspace_role": membership.get("role", "member")}


def make_token(user):
    import jwt
    return jwt.encode({"sub": user["id"], "email": user["email"], "full_name": user["full_name"], "workspace_id": user["workspace_id"], "role": user["role"], "workspace_role": user.get("workspace_role", "member")}, os.environ["SPORTS_EDITORIAL_JWT_SECRET"], algorithm="HS256")


def require_workspace_admin():
    user = current_user()
    if not user or user.get("workspace_role") not in ("owner", "admin"):
        abort(403, description="Workspace owner or admin access is required.")
    return user


def list_workspace_users(workspace_id):
    client = SupabaseRestClient()
    memberships = client.request("sports_editorial_memberships", query={"select": "user_id,editorial_role,is_active,created_at", "workspace_id": f"eq.{workspace_id}", "order": "created_at.asc"})
    if not memberships:
        return []
    ids = ",".join(item["user_id"] for item in memberships)
    users = client.request("app_users", query={"select": "id,email,full_name,is_active", "id": f"in.({ids})"})
    users_by_id = {item["id"]: item for item in users}
    return [{**item, **users_by_id.get(item["user_id"], {})} for item in memberships]


def provision_workspace_user(workspace_id, email, full_name, temporary_password, editorial_role):
    import bcrypt
    if editorial_role not in ("journalist", "sub_editor"):
        raise ValueError("Choose Journalist or Sub-editor access.")
    normalised_email = str(email or "").strip().lower()
    if "@" not in normalised_email:
        raise ValueError("Enter a valid email address.")
    if len(str(temporary_password or "")) < 12:
        raise ValueError("Use a temporary password with at least 12 characters.")
    password_hash = bcrypt.hashpw(temporary_password.encode(), bcrypt.gensalt(rounds=12)).decode()
    result = SupabaseRestClient().request("rpc/sports_editorial_provision_user", "POST", payload={"p_workspace_id": workspace_id, "p_email": normalised_email, "p_full_name": str(full_name or "").strip(), "p_password_hash": password_hash, "p_editorial_role": editorial_role})
    return result[0] if isinstance(result, list) and result else result
