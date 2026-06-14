"""Autenticacao simples (1 usuario) para o VDL Studio.

Persistido em <state_dir>/auth.json. Inicializa admin/admin no primeiro boot,
com flag must_change. Sessoes por token Bearer, tambem persistidas para
sobreviver a reload do processo.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
SESSION_TTL_HOURS = 24 * 7
PBKDF2_ROUNDS = 240_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
    )
    return digest.hex()


class AuthError(Exception):
    """Falha de autenticacao (credenciais invalidas, sessao expirada)."""


class AuthManager:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.auth_file = self.state_dir / "auth.json"
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._load()

    # ---- persistencia ----------------------------------------------------
    def _load(self) -> None:
        if self.auth_file.exists():
            try:
                self._data = json.loads(self.auth_file.read_text("utf-8"))
            except (ValueError, OSError):
                self._data = {}
        if not self._data.get("password_hash"):
            self._seed_default()
        self._data.setdefault("sessions", {})
        self._prune_locked()

    def _seed_default(self) -> None:
        salt = secrets.token_hex(16)
        self._data = {
            "username": DEFAULT_USER,
            "salt": salt,
            "password_hash": _hash_password(DEFAULT_PASSWORD, salt),
            "must_change": True,
            "sessions": {},
        }
        self._save_locked()

    def _save_locked(self) -> None:
        tmp = self.auth_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2), "utf-8")
        os.replace(tmp, self.auth_file)

    # ---- sessoes ---------------------------------------------------------
    def _prune_locked(self) -> None:
        now = _now()
        sessions = self._data.get("sessions", {})
        valid = {
            token: exp
            for token, exp in sessions.items()
            if _parse(exp) and _parse(exp) > now
        }
        if len(valid) != len(sessions):
            self._data["sessions"] = valid
            self._save_locked()

    def _issue_token(self) -> str:
        token = secrets.token_urlsafe(32)
        expiry = (_now() + timedelta(hours=SESSION_TTL_HOURS)).isoformat()
        self._data.setdefault("sessions", {})[token] = expiry
        self._save_locked()
        return token

    # ---- api publica -----------------------------------------------------
    def login(self, username: str, password: str) -> dict[str, Any]:
        with self._lock:
            expected = self._data.get("password_hash")
            salt = self._data.get("salt", "")
            user_ok = (username or "").strip() == self._data.get("username")
            pass_ok = bool(expected) and secrets.compare_digest(
                _hash_password(password or "", salt), expected
            )
            if not (user_ok and pass_ok):
                raise AuthError("Usuario ou senha invalidos.")
            token = self._issue_token()
            return {
                "token": token,
                "username": self._data["username"],
                "must_change": bool(self._data.get("must_change")),
            }

    def validate(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            expiry = self._data.get("sessions", {}).get(token)
            if not expiry:
                return False
            parsed = _parse(expiry)
            if not parsed or parsed <= _now():
                self._data["sessions"].pop(token, None)
                self._save_locked()
                return False
            return True

    def me(self, token: str | None) -> dict[str, Any]:
        if not self.validate(token):
            raise AuthError("Sessao invalida ou expirada.")
        with self._lock:
            return {
                "username": self._data["username"],
                "must_change": bool(self._data.get("must_change")),
            }

    def change_password(self, token: str | None, current: str, new: str) -> dict[str, Any]:
        if not self.validate(token):
            raise AuthError("Sessao invalida ou expirada.")
        with self._lock:
            salt = self._data.get("salt", "")
            if not secrets.compare_digest(
                _hash_password(current or "", salt), self._data.get("password_hash", "")
            ):
                raise AuthError("Senha atual incorreta.")
            new = (new or "").strip()
            if len(new) < 8:
                raise AuthError("A nova senha deve ter ao menos 8 caracteres.")
            new_salt = secrets.token_hex(16)
            self._data["salt"] = new_salt
            self._data["password_hash"] = _hash_password(new, new_salt)
            self._data["must_change"] = False
            # invalida todas as sessoes menos a atual
            self._data["sessions"] = {token: self._data["sessions"][token]}
            self._save_locked()
            return {"username": self._data["username"], "must_change": False}

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            if self._data.get("sessions", {}).pop(token, None) is not None:
                self._save_locked()


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
