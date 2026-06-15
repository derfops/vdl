from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CookieExtractor = Callable[[str], tuple[str, str, str | None, list[dict] | None] | None]


@dataclass(frozen=True)
class AuthDetails:
    source_label: str
    user_agent: str
    cookie_header: str
    referer: str | None = None
    cookies_list: list[dict] | None = None

    @property
    def is_valid(self) -> bool:
        return bool(self.user_agent and self.cookie_header)

    def masked_label(self) -> str:
        return self.source_label


def resolve_auth_from_environment(
    environ: dict[str, str], extractor: CookieExtractor
) -> AuthDetails | None:
    token = environ.get("VDL_TOKEN", "").strip()
    if not token:
        return None
    return resolve_pasted_auth(token, extractor, "VDL_TOKEN do ambiente")


def resolve_auth_from_file(path: str, extractor: CookieExtractor) -> AuthDetails | None:
    content = Path(path).expanduser().read_text(encoding="utf-8").strip()
    return resolve_pasted_auth(content, extractor, f"arquivo {Path(path).name}")


def resolve_pasted_auth(
    raw_value: str, extractor: CookieExtractor, source_label: str = "entrada colada"
) -> AuthDetails | None:
    value = _compact_possible_base64(raw_value)
    decoded = _try_decode_base64(value)
    if decoded:
        auth = _resolve_decoded(decoded, extractor, f"{source_label} (base64)")
        if auth:
            return auth

    return _resolve_decoded(raw_value.strip(), extractor, source_label)


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * 12}{value[-visible:]}"


def _resolve_decoded(
    decoded: str, extractor: CookieExtractor, source_label: str
) -> AuthDetails | None:
    text = decoded.strip()
    if _looks_like_json_cookies(text):
        extracted = extractor(text)
        if not extracted:
            return None
        user_agent, cookie_header, referer, cookies_list = extracted
        return AuthDetails(source_label, user_agent, cookie_header, referer, cookies_list)

    if _looks_like_legacy_user_agent_cookie(text):
        user_agent, cookie_header = text.split(";", 1)
        return AuthDetails(source_label, user_agent, cookie_header, None, None)

    if _looks_like_cookie_header(text):
        return AuthDetails(source_label, DEFAULT_USER_AGENT, text, None, None)

    return None


def _try_decode_base64(value: str) -> str | None:
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _compact_possible_base64(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _looks_like_json_cookies(value: str) -> bool:
    if not (value.startswith("[") and value.endswith("]")):
        return False
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, list)


def _looks_like_legacy_user_agent_cookie(value: str) -> bool:
    return ";" in value and "Mozilla/" in value.split(";", 1)[0]


def _looks_like_cookie_header(value: str) -> bool:
    if "\n" in value or "[" in value or "{" in value:
        return False
    return bool(re.search(r"(^|;\s*)[^=;\s]+=[^;]+", value))
