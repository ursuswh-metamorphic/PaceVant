"""Short-lived, demo-only credentials. The server signing secret never leaves here."""

import base64
import hashlib
import hmac
import json
import secrets
import time

SESSION_SECONDS = 86400
DOMAIN = b"pacevant-demo-session-v1:"


def issue_demo_session(secret, *, now=None):
    now = int(time.time()) if now is None else now
    data = {
        "account_id": "demo",
        "expires_at": now + SESSION_SECONDS,
        "nonce": secrets.token_urlsafe(16),
    }
    body = (
        base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(secret.encode(), DOMAIN + body.encode(), hashlib.sha256).hexdigest()
    return body + "." + signature, data["expires_at"]


def valid_demo_session(token, secret, *, now=None):
    now = int(time.time()) if now is None else now
    try:
        if len(token) > 1024:
            return False
        body, signature = token.split(".")
        expected = hmac.new(secret.encode(), DOMAIN + body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        data = json.loads(
            base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
        )
        return (
            set(data) == {"account_id", "expires_at", "nonce"}
            and data["account_id"] == "demo"
            and type(data["expires_at"]) is int
            and now < data["expires_at"] <= now + SESSION_SECONDS
            and isinstance(data["nonce"], str)
            and 16 <= len(data["nonce"]) <= 64
        )
    except (ValueError, TypeError, UnicodeError):
        return False
