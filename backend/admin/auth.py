"""
Admin authentication — password stored in env (ADMIN_PASSWORD), short-lived
session tokens held server-side. Never exposes password to LLM or frontend.
"""
from __future__ import annotations
import hmac
import os
import secrets
import threading
import time


SESSION_TTL_SECONDS = 60 * 60 * 4  # 4 hours


def _get_expected_password() -> str | None:
    pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    return pw or None


def verify_password(submitted: str) -> bool:
    expected = _get_expected_password()
    if not expected:
        # Refuse if no password configured — production must set one.
        return False
    return hmac.compare_digest(submitted.encode(), expected.encode())


def admin_configured() -> bool:
    return _get_expected_password() is not None


class AdminSession:
    """In-memory session store for admin tokens."""

    def __init__(self):
        self._lock = threading.RLock()
        self._tokens: dict[str, float] = {}

    def issue(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens[token] = time.time() + SESSION_TTL_SECONDS
        return token

    def validate(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            expiry = self._tokens.get(token)
            if expiry is None:
                return False
            if expiry < time.time():
                del self._tokens[token]
                return False
            return True

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)
