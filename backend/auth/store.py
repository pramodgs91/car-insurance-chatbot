"""User profile persistence and session token management."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class UserStore:
    """Persists per-user structured profiles as JSON files."""

    def __init__(self, users_dir: Path):
        self.users_dir = users_dir
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, email: str) -> Path:
        safe = email.replace("@", "_at_").replace(".", "_dot_")
        return self.users_dir / f"{safe}.json"

    def load(self, email: str) -> dict:
        path = self._path(email)
        if not path.exists():
            return self._default(email)
        try:
            with path.open() as fh:
                return json.load(fh)
        except Exception:
            return self._default(email)

    def save(self, email: str, profile: dict) -> None:
        with self._lock:
            path = self._path(email)
            profile["last_updated"] = datetime.now(timezone.utc).isoformat()
            with path.open("w") as fh:
                json.dump(profile, fh, indent=2, ensure_ascii=False)

    def update_name(self, email: str, name: str) -> None:
        profile = self.load(email)
        if name and not profile.get("name"):
            profile["name"] = name
            self.save(email, profile)

    def merge_session(self, email: str, session_data: dict) -> None:
        """Merge tool-fetched facts into the persistent user profile."""
        profile = self.load(email)
        car = session_data.get("car_info") or {}
        if car:
            veh = profile.setdefault("vehicle_info", {})
            skip = {"source", "error"}
            for k, v in car.items():
                if v and k not in skip:
                    veh[k] = v
        self.save(email, profile)

    def all_profiles(self) -> list[dict]:
        out = []
        for f in sorted(self.users_dir.glob("*.json")):
            try:
                with f.open() as fh:
                    out.append(json.load(fh))
            except Exception:
                pass
        return out

    @staticmethod
    def _default(email: str) -> dict:
        return {
            "email": email,
            "name": "",
            "vehicle_info": {},
            "policy_info": {},
            "preferences": {},
            "last_updated": None,
        }


class UserSessionStore:
    """In-memory store of issued user auth tokens (email/name only)."""

    def __init__(self):
        self._tokens: dict[str, dict] = {}
        self._lock = threading.RLock()

    def issue(self, email: str, name: str) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._tokens[token] = {
                "email": email,
                "name": name,
                "issued_at": datetime.now(timezone.utc).isoformat(),
            }
        return token

    def get(self, token: str | None) -> dict | None:
        if not token:
            return None
        return self._tokens.get(token)

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)
