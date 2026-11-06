"""Cloud API client for the Sinilink account (login + device discovery).

Protocol details were reverse-engineered from the official Android app
(`com.xydc`, version 2.2.15) and verified against the live backend.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE,
    API_CLASSIFY_PATH,
    API_DEVICES_PATH,
    API_LOGIN_PATH,
    DEFAULT_LOCALE,
    TRIBLE_DES_KEY,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class SinilinkAuthError(Exception):
    """Raised when the account login is rejected."""


class SinilinkApiError(Exception):
    """Raised on an unexpected backend response."""


def _pkcs7_pad(data: bytes, block: int = 8) -> bytes:
    pad = block - (len(data) % block)
    return data + bytes([pad]) * pad


def _des3_ecb_encrypt(plaintext: str) -> bytes:
    """TripleDES-ECB + Pkcs7, matching the app's CryptoJS usage."""
    try:
        from Crypto.Cipher import DES3
    except ImportError as err:  # pragma: no cover - dependency guard
        raise SinilinkApiError(
            "pycryptodome is required (pip install pycryptodome)"
        ) from err

    padded = _pkcs7_pad(plaintext.encode("utf-8"), 8)
    return DES3.new(TRIBLE_DES_KEY, DES3.MODE_ECB).encrypt(padded)


def _json_escape(value: str) -> str:
    """Escape a value for the backend's lenient JSON parser.

    The app concatenates values raw into `{key:"value"}`. The backend accepts
    unquoted keys but returns "System exception..." if a value contains an
    unescaped double quote or backslash (verified live).
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def encrypt_params(pseudo_json: str) -> str:
    """base64(TripleDES-ECB-Pkcs7(pseudo_json))."""
    return base64.b64encode(_des3_ecb_encrypt(pseudo_json)).decode("ascii")


def build_login_params(login: str, password: str, dial_code: str, locale: str) -> str:
    """Build the encrypted `params` field for /api/user/login."""
    payload = (
        '{dianHuaQuHao:"%s",phone:"%s",password:"%s",locale:"%s"}'
        % (
            _json_escape(dial_code),
            _json_escape(login),
            _json_escape(password),
            _json_escape(locale),
        )
    )
    return encrypt_params(payload)


class SinilinkApi:
    """Thin async wrapper around the Sinilink cloud endpoints."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _post_form(
        self,
        path: str,
        fields: dict[str, str],
        token: str | None = None,
        locale: str = DEFAULT_LOCALE,
    ) -> Any:
        url = f"{API_BASE}{path}"
        sep = "&" if "?" in path else "?"
        url = f"{url}{sep}lang={locale}"

        headers = {"Accept": "application/json"}
        if token:
            headers["xAuthToken"] = token

        async with self._session.post(
            url, data=fields, headers=headers, timeout=_TIMEOUT
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise SinilinkApiError(f"HTTP {resp.status} from {path}: {text[:200]}")
            try:
                return json.loads(text)
            except ValueError as err:
                raise SinilinkApiError(
                    f"Non-JSON response from {path}: {text[:200]}"
                ) from err

    async def async_login(
        self, login: str, password: str, dial_code: str, locale: str
    ) -> str:
        """Log in and return the appLoginToken (used as xAuthToken)."""
        params = build_login_params(login, password, dial_code, locale)
        data = await self._post_form(
            f"{API_LOGIN_PATH}", {"params": params}, locale=locale
        )

        if data.get("success"):
            token = (data.get("result") or {}).get("appLoginToken")
            if token:
                return token
            raise SinilinkApiError("Login succeeded but no appLoginToken returned")

        errors = data.get("errorMsg") or []
        message = errors[0] if errors else "unknown error"
        raise SinilinkAuthError(message)

    async def async_get_devices(self, token: str, locale: str) -> list[dict[str, Any]]:
        """Return every device of the account as a flat list of dicts.

        The account endpoint returns *classifications* (groups); each group's
        devices are fetched separately. The group's `businessId` (a UUID) is the
        id the API expects — using the numeric `id` returns an empty list with
        no error, which silently hides every device.
        """
        groups = await self._post_form(
            API_CLASSIFY_PATH, {"param": encrypt_params("{}")}, token=token, locale=locale
        )
        if not groups.get("success"):
            errors = groups.get("errorMsg") or ["unknown error"]
            raise SinilinkApiError(f"Device list failed: {errors[0]}")

        devices: list[dict[str, Any]] = []
        for group in groups.get("result") or []:
            classify_id = group.get("businessId") or group.get("id")
            data = await self._post_form(
                f"{API_DEVICES_PATH}?classifyId={classify_id}",
                {"param": encrypt_params("{}")},
                token=token,
                locale=locale,
            )
            for device in data.get("result") or []:
                device["_group"] = group.get("name")
                devices.append(device)
        return devices
