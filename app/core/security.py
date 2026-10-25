import hashlib
import hmac
import re

SIGNATURE_FORMAT = re.compile(r"[0-9a-f]{64}")


def valid_webhook_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """Check Kapso's X-Webhook-Signature: hex HMAC-SHA256 of the raw body."""
    # Check the shape first: compare_digest raises on non-ASCII input.
    if not signature or not SIGNATURE_FORMAT.fullmatch(signature):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


ADMIN_USERNAME = "admin"


def valid_admin_credentials(expected_password: str, username: str, password: str) -> bool:
    # Compare both in constant time, and always both, so timing doesn't reveal which was wrong.
    username_ok = hmac.compare_digest(username.encode(), ADMIN_USERNAME.encode())
    password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return username_ok and password_ok
