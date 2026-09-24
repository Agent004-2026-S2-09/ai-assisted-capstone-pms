"""Password hashing and revocable database sessions, without extra dependencies."""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
import time

import database

SESSION_SECONDS = 8 * 60 * 60
RESET_SECONDS = 30 * 60
PUBLIC_USER_COLUMNS = "id, name, username, role, active, status, registered_at"


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


def create_user(name, username, password, role, active=True):
    name, username = name.strip(), username.strip().casefold()
    if not name or not username or role not in database.ROLES:
        raise ValueError("Name, username/email and a supported role are required.")
    encoded = hash_password(password)
    with database.connect() as db:
        cursor = db.execute("""INSERT INTO users(name, username, password_hash, role, active, status, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (name, username, encoded, role, int(active),
                "active" if active else "disabled", datetime.now(timezone.utc).isoformat()))
        return cursor.lastrowid


def _authenticate(db, username, password):
    row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip().casefold(),)).fetchone()
    valid = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not valid or not row["active"]:
        return None
    return {key: row[key] for key in ("id", "name", "username", "role", "active", "status")}


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


def current_user(state):
    token = state.get("auth_token")
    if not isinstance(token, str) or not token:
        return None
    with database.connect() as db:
        row = db.execute("""SELECT u.id, u.name, u.username, u.role, u.active, u.status
            FROM users u JOIN sessions s ON s.user_id = u.id
            WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1""",
                         (_token_hash(token), time.time())).fetchone()
    return dict(row) if row else None


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


def _replace_password(db, user_id, encoded):
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (encoded, user_id))
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
