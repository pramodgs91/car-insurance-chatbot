"""Google Identity Services — server-side ID-token verification."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID)


def _fetch_tokeninfo(id_token: str) -> dict:
    url = (
        "https://oauth2.googleapis.com/tokeninfo?"
        + urllib.parse.urlencode({"id_token": id_token})
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Google rejected the token ({exc.code})") from exc
    except Exception as exc:
        raise ValueError(f"Token verification error: {exc}") from exc


async def verify_google_token(id_token: str) -> dict[str, str]:
    """Return {email, name} for a valid Google credential, or raise ValueError."""
    if not GOOGLE_CLIENT_ID:
        raise ValueError("Google auth is not configured (GOOGLE_CLIENT_ID missing)")
    data = await asyncio.to_thread(_fetch_tokeninfo, id_token)
    if data.get("aud") != GOOGLE_CLIENT_ID:
        raise ValueError("Token audience mismatch — wrong Google client ID")
    if data.get("email_verified") != "true":
        raise ValueError("Google account email is not verified")
    return {
        "email": data["email"],
        "name": data.get("name", ""),
    }
