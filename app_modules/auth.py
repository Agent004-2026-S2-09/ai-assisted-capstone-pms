"""Password hashing and revocable database sessions, without extra dependencies."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
import time

from app_modules import database

SESSION_SECONDS = 8 * 60 * 60
RESET_SECONDS = 30 * 60
PUBLIC_USER_COLUMNS = "id, name, username, first_name, last_name, email, role, permissions, active, status, registered_at, must_change_password, updated_at"


def normalise_permissions(role=None, permissions=None):
    """Return a canonical permission tuple and enforce student exclusivity."""
    if permissions is None:
        values = [role] if role else []
    elif isinstance(permissions, str):
        try:
            decoded = json.loads(permissions)
            values = decoded if isinstance(decoded, list) else [permissions]
        except (TypeError, ValueError):
            values = [part.strip() for part in permissions.split(",")]
    else:
        values = list(permissions) if isinstance(permissions, (list, tuple, set)) else [permissions]
    values = {str(value).strip() for value in values if str(value).strip()}
    if role:
        values.add(str(role).strip())
    if not values or not values.issubset(set(database.ROLES)):
        raise ValueError("Select at least one supported permission.")
    if "Student" in values and len(values) != 1:
        raise ValueError("Students can only have the Student permission.")
    return tuple(permission for permission in database.ROLES if permission in values)


def permission_list(value):
    """Decode stored permissions, tolerating pre-migration/legacy records."""
    role = value.get("role") if isinstance(value, dict) else None
    permissions = value.get("permissions") if isinstance(value, dict) else value
    return list(normalise_permissions(role, permissions))


def has_permission(user, permission):
    return str(permission) in permission_list(user)


def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError("Use a password between 12 and 1024 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=5)
    return f"scrypt$16384$8$5${salt.hex()}${digest.hex()}"


def verify_password(password, encoded):
    if not isinstance(password, str) or len(password) > 1024:
        return False
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", "16384", "8", "5"):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError, AttributeError):
        return False


# Unknown users still take the password derivation path.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def create_user(name, username, password, role, active=True, *, first_name="", last_name="", email="", must_change_password=False, permissions=None):
    name, username = str(name or "").strip(), str(username or "").strip().casefold()
    first_name = str(first_name or "").strip()
    last_name = str(last_name or "").strip()
    email = str(email or "").strip().casefold()
    if not first_name and not last_name:
        parts = name.split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:])
    if not name:
        name = " ".join(part for part in (first_name, last_name) if part).strip()
    if not name or not username or role not in database.ROLES:
        raise ValueError("Name, username/email and a supported role are required.")
    permissions = normalise_permissions(role, permissions)
    encoded = hash_password(password)
    if email and ("@" not in email or len(email) > 320):
        raise ValueError("Enter a valid email address.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database.connect() as db:
        cursor = db.execute("""INSERT INTO users(name, username, first_name, last_name, email,
            password_hash, role, permissions, active, status, registered_at, must_change_password, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (name, username, first_name, last_name, email,
                encoded, role, json.dumps(permissions), int(active), "active" if active else "disabled", now,
                int(bool(must_change_password)), now))
        return cursor.lastrowid


def create_users_batch(rows):
    """Create validated imported accounts atomically with temporary-password enforcement."""
    prepared = []
    seen_usernames, seen_emails = set(), set()
    for row in rows:
        first_name = str(row.get("first_name") or "").strip()
        last_name = str(row.get("last_name") or "").strip()
        username = str(row.get("username") or "").strip().casefold()
        email = str(row.get("email") or "").strip().casefold()
        role = str(row.get("role") or "").strip()
        permissions = normalise_permissions(role, row.get("permissions"))
        status = str(row.get("status") or "").strip().casefold()
        password = str(row.get("password") or "")
        if not first_name or not last_name or not username:
            raise ValueError(f"Row {row.get('source_row', '?')}: first name, last name and username are required.")
        if not email or "@" not in email or len(email) > 320:
            raise ValueError(f"Row {row.get('source_row', '?')}: enter a valid email address.")
        if role not in database.ROLES:
            raise ValueError(f"Row {row.get('source_row', '?')}: unsupported role.")
        if status not in {"pending", "active", "disabled", "rejected"}:
            raise ValueError(f"Row {row.get('source_row', '?')}: unsupported account status.")
        if not 12 <= len(password) <= 1024:
            raise ValueError(f"Row {row.get('source_row', '?')}: temporary password must contain 12 to 1024 characters.")
        if username in seen_usernames or email in seen_emails:
            raise ValueError(f"Row {row.get('source_row', '?')}: duplicate username or email in the import.")
        seen_usernames.add(username)
        seen_emails.add(email)
        prepared.append({
            "name": f"{first_name} {last_name}".strip(),
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password_hash": hash_password(password),
            "role": role,
            "permissions": json.dumps(permissions),
            "active": int(status == "active"),
            "status": status,
        })
    if not prepared:
        raise ValueError("The user import contains no accounts.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    created_ids = []
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for item in prepared:
            if db.execute("SELECT 1 FROM users WHERE username = ? OR email = ?", (item["username"], item["email"])).fetchone():
                raise ValueError(f"Username or email already exists: {item['username']}.")
            cursor = db.execute("""INSERT INTO users(name, username, first_name, last_name, email,
                password_hash, role, permissions, active, status, registered_at, must_change_password, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (item["name"], item["username"], item["first_name"], item["last_name"], item["email"],
                 item["password_hash"], item["role"], item["permissions"], item["active"], item["status"], now, now))
            created_ids.append(cursor.lastrowid)
    return created_ids


def _authenticate(db, username, password):
    row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip().casefold(),)).fetchone()
    valid = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not valid or not row["active"]:
        return None
    result = {key: row[key] for key in ("id", "name", "username", "first_name", "last_name", "email", "role", "active", "status", "must_change_password", "updated_at")}
    result["permissions"] = permission_list({"role": row["role"], "permissions": row["permissions"]})
    return result


def authenticate(username, password):
    with database.connect() as db:
        return _authenticate(db, username, password)


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def login(state, username, password):
    logout(state)
    token = secrets.token_urlsafe(32)
    with database.connect() as db:
        # Serialize verification/session creation with approval, disabling and resets.
        db.execute("BEGIN IMMEDIATE")
        user = _authenticate(db, username, password)
        if user is None:
            return False
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                   (_token_hash(token), user["id"], time.time() + SESSION_SECONDS))
    state["auth_token"] = token
    return True


def restore_session(state, token):
    """Restore a browser-persisted token only when its server session is valid."""
    if not isinstance(token, str) or not token or len(token) > 256:
        return False
    state["auth_token"] = token
    if current_user(state) is None:
        state.pop("auth_token", None)
        return False
    return True


def current_user(state):
    token = state.get("auth_token")
    if not isinstance(token, str) or not token:
        return None
    with database.connect() as db:
        row = db.execute("""SELECT u.id, u.name, u.username, u.first_name, u.last_name, u.email,
            u.role, u.permissions, u.active, u.status, u.must_change_password, u.updated_at
            FROM users u JOIN sessions s ON s.user_id = u.id
            WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1""",
                         (_token_hash(token), time.time())).fetchone()
    if not row:
        return None
    result = dict(row)
    result["permissions"] = permission_list(result)
    return result


def logout(state):
    token = state.get("auth_token")
    if isinstance(token, str) and token:
        with database.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    # Clear all chat, project selection, widget and identity state across users.
    state.clear()


def complete_password_reset(username, token, password, confirmation):
    """Consume a reset code once and revoke sessions atomically; never approve users."""
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    if not isinstance(token, str) or not 1 <= len(token.strip()) <= 256:
        raise ValueError("Invalid or expired reset code.")
    encoded = hash_password(password)
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        reset = db.execute("""SELECT r.user_id FROM password_resets r JOIN users u ON u.id = r.user_id
            WHERE r.token_hash = ? AND r.expires_at > ? AND u.username = ?""",
            (_token_hash(token.strip()), time.time(), username.strip().casefold())).fetchone()
        if not reset:
            raise ValueError("Invalid or expired reset code.")
        _replace_password(db, reset["user_id"], encoded)


def _replace_password(db, user_id, encoded, *, revoke_sessions=True):
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
               (encoded, datetime.now(timezone.utc).isoformat(timespec="seconds"), user_id))
    if revoke_sessions:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))


def reset_password_for_operator(username, password):
    """Existing trusted CLI workflow: replace a password without recovering the old one."""
    encoded = hash_password(password)
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT id FROM users WHERE username = ?", (username.strip().casefold(),)).fetchone()
        if not user:
            raise ValueError("Unknown user.")
        _replace_password(db, user["id"], encoded)


def _check_password_change_rate_limit(db, username):
    cutoff = time.time() - 900
    row = db.execute("SELECT COUNT(*) FROM password_change_attempts WHERE username = ? AND attempted_at >= ?", (username, cutoff)).fetchone()
    if int(row[0]) >= 8:
        raise ValueError("Too many password-change attempts. Please try again later.")


def change_password_from_login(username, full_name, email, new_password, confirmation):
    """Change an active user's password after full profile verification."""
    username = str(username or "").strip().casefold()
    full_name = " ".join(str(full_name or "").strip().split()).casefold()
    email = str(email or "").strip().casefold()
    if new_password != confirmation:
        raise ValueError("The passwords do not match.")
    encoded = hash_password(new_password)
    with database.connect() as db:
        _check_password_change_rate_limit(db, username)
        row = db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
        expected_name = " ".join(filter(None, [row["first_name"], row["last_name"]])).casefold() if row else ""
        if row and not expected_name:
            expected_name = str(row["name"] or "").strip().casefold()
        valid = bool(row and expected_name == full_name and str(row["email"] or "").casefold() == email and email)
        db.execute("INSERT INTO password_change_attempts(username, attempted_at, successful) VALUES (?, ?, ?)", (username, time.time(), int(valid)))
        if not valid:
            raise ValueError("The supplied account details could not be verified.")
        _replace_password(db, row["id"], encoded)
        db.execute("DELETE FROM password_change_attempts WHERE username = ? AND attempted_at < ?", (username, time.time() - 86400))


def change_own_password(state, current_password, new_password, confirmation):
    user = current_user(state)
    if not user:
        raise ValueError("Please sign in before changing your password.")
    if new_password != confirmation:
        raise ValueError("The passwords do not match.")
    if not authenticate(user["username"], current_password):
        raise ValueError("The current password is incorrect.")
    encoded = hash_password(new_password)
    with database.connect() as db:
        _replace_password(db, user["id"], encoded, revoke_sessions=False)
    return current_user(state)


def complete_first_password_change(state, new_password, confirmation):
    user = current_user(state)
    if not user:
        raise ValueError("Please sign in before changing your password.")
    if new_password != confirmation:
        raise ValueError("The passwords do not match.")
    encoded = hash_password(new_password)
    with database.connect() as db:
        _replace_password(db, user["id"], encoded, revoke_sessions=False)
    return current_user(state)
