"""Config flow for Sinilink PC Power."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinilinkApi, SinilinkApiError, SinilinkAuthError
from .const import (
    CONF_DIAL_CODE,
    CONF_LOCALE,
    CONF_LOGIN,
    CONF_PASSWORD,
    CONF_TOKEN,
    DEFAULT_DIAL_CODE,
    DEFAULT_LOCALE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOGIN): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_DIAL_CODE, default=DEFAULT_DIAL_CODE): str,
        vol.Optional(CONF_LOCALE, default=DEFAULT_LOCALE): vol.In(
            ["en_US", "zh_CN", "pt"]
        ),
    }
)


class SinilinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup: log in and verify devices are reachable."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_LOGIN].lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = SinilinkApi(session)
            try:
                token = await api.async_login(
                    user_input[CONF_LOGIN],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_DIAL_CODE],
                    user_input[CONF_LOCALE],
                )
                devices = await api.async_get_devices(token, user_input[CONF_LOCALE])
            except SinilinkAuthError as err:
                _LOGGER.debug("Login rejected: %s", err)
                message = str(err).lower()
                if "valid account" in message:
                    errors["base"] = "invalid_account"
                elif "valid password" in message:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except SinilinkApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_LOGIN],
                    data={**user_input, CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SinilinkOptionsFlow()


class SinilinkOptionsFlow(OptionsFlow):
    """Allow changing the credentials without removing the integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = SinilinkApi(session)
            try:
                await api.async_login(
                    user_input[CONF_LOGIN],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_DIAL_CODE],
                    user_input[CONF_LOCALE],
                )
            except SinilinkAuthError as err:
                message = str(err).lower()
                errors["base"] = (
                    "invalid_auth" if "password" in message else "invalid_account"
                )
            except SinilinkApiError:
                errors["base"] = "cannot_connect"
            else:
                # drop the cached token so the new credentials take effect
                return self.async_create_entry(
                    title="", data={**user_input, "_refresh_token": True}
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOGIN, default=self.config_entry.data.get(CONF_LOGIN, "")
                ): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_DIAL_CODE,
                    default=self.config_entry.data.get(
                        CONF_DIAL_CODE, DEFAULT_DIAL_CODE
                    ),
                ): str,
                vol.Optional(
                    CONF_LOCALE,
                    default=self.config_entry.data.get(CONF_LOCALE, DEFAULT_LOCALE),
                ): vol.In(["en_US", "zh_CN", "pt"]),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
