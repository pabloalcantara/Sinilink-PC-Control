"""DataUpdateCoordinator for Sinilink PC Power.

Holds the login token, the device list, the MQTT client, and the last known
state of every device. Entities read from this coordinator and ask it to issue
commands.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SinilinkApi, SinilinkApiError, SinilinkAuthError
from .const import (
    CMD_FORCE_OFF,
    CMD_POWER_BOOT_OFF,
    CMD_POWER_BOOT_ON,
    CMD_POWER_PRESS,
    CMD_READ,
    CMD_SOFT_OFF,
    CONF_DIAL_CODE,
    CONF_LOCALE,
    CONF_LOGIN,
    CONF_PASSWORD,
    CONF_REFRESH_INTERVAL,
    CONF_TOKEN,
    CONFIRM_INTERVAL,
    CONFIRM_TIMEOUT,
    DEFAULT_DIAL_CODE,
    DEFAULT_LOCALE,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    IDX_PC_STATE,
    IDX_POWER_BOOT,
    IDX_PROHIBIT_KEY,
    NAME,
    PC_STATES_ON,
    REFRESH_MAX,
    REFRESH_MIN,
    STATE_WAIT_TIMEOUT,
)
from .mqtt_client import SinilinkMqtt

_LOGGER = logging.getLogger(__name__)

# Fired (with the MAC as payload) every time a device reports a new state, so
# button entities waiting for a fresh reading can wake up instead of polling.
SIGNAL_STATE_UPDATED = f"{DOMAIN}_state_updated"


@dataclass
class SinilinkDevice:
    """One PC power controller."""

    mac: str
    name: str
    model: str | None = None
    firmware: str | None = None
    group: str | None = None
    business_id: str | None = None
    # last reported state array (param[0..5]); None until the device answers
    state: list[int] | None = None
    online: bool = False
    # loop monotonic time of the last state message (None until one arrives)
    state_updated_at: float | None = None

    @property
    def pc_is_on(self) -> bool:
        if not self.state:
            return False
        return self.state[IDX_PC_STATE] in PC_STATES_ON

    @property
    def pc_state_raw(self) -> int | None:
        return self.state[IDX_PC_STATE] if self.state else None

    @property
    def power_boot(self) -> bool | None:
        if not self.state or len(self.state) <= IDX_POWER_BOOT:
            return None
        return bool(self.state[IDX_POWER_BOOT])

    @property
    def prohibit_key(self) -> bool | None:
        if not self.state or len(self.state) <= IDX_PROHIBIT_KEY:
            return None
        return bool(self.state[IDX_PROHIBIT_KEY])


class SinilinkCoordinator(DataUpdateCoordinator[dict[str, SinilinkDevice]]):
    """Coordinate cloud login, device discovery and MQTT state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{NAME} ({entry.data.get(CONF_LOGIN)})",
            update_interval=timedelta(seconds=_stored_interval(entry)),
        )
        self.entry = entry
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._api = SinilinkApi(self._session)
        self.devices: dict[str, SinilinkDevice] = {}
        self._mqtt_active = False
        self._mqtt = SinilinkMqtt(
            on_state=self._handle_state,
            on_online=self._handle_online,
            on_connection=self._handle_connection,
            client_id=f"ha-sinilink-{entry.entry_id[:8]}",
        )

    # -- refresh interval ---------------------------------------------------
    @property
    def refresh_interval(self) -> int:
        """Current polling interval in seconds (options win over data)."""
        return _stored_interval(self.entry)

    async def async_set_refresh_interval(self, seconds: int) -> None:
        """Persist a new refresh interval and apply it to the running coordinator."""
        seconds = max(REFRESH_MIN, min(REFRESH_MAX, int(seconds)))
        self.update_interval = timedelta(seconds=seconds)
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, CONF_REFRESH_INTERVAL: seconds},
        )
        _LOGGER.debug("Refresh interval set to %ss", seconds)

    # -- tokens -------------------------------------------------------------
    @property
    def token(self) -> str | None:
        return self.entry.data.get(CONF_TOKEN)

    async def _async_login(self) -> str:
        login = self.entry.data[CONF_LOGIN]
        password = self.entry.data[CONF_PASSWORD]
        dial = self.entry.data.get(CONF_DIAL_CODE, DEFAULT_DIAL_CODE)
        locale = self.entry.data.get(CONF_LOCALE, DEFAULT_LOCALE)
        try:
            return await self._api.async_login(login, password, dial, locale)
        except SinilinkAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

    # -- coordinator API ----------------------------------------------------
    async def _async_update_data(self) -> dict[str, SinilinkDevice]:
        locale = self.entry.data.get(CONF_LOCALE, DEFAULT_LOCALE)

        token = self.token
        if not token:
            token = await self._async_login()
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, CONF_TOKEN: token}
            )

        try:
            raw_devices = await self._api.async_get_devices(token, locale)
        except SinilinkAuthError:
            token = await self._async_login()
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, CONF_TOKEN: token}
            )
            raw_devices = await self._api.async_get_devices(token, locale)
        except SinilinkApiError as err:
            raise UpdateFailed(str(err)) from err

        for raw in raw_devices:
            mac = (raw.get("macAddress") or "").upper()
            if not mac:
                continue
            device = self.devices.get(mac)
            if device is None:
                device = SinilinkDevice(mac=mac, name=raw.get("nickName") or mac)
                self.devices[mac] = device
            device.name = raw.get("nickName") or device.name
            device.firmware = raw.get("guJianBanBen")
            device.group = raw.get("_group")
            device.business_id = raw.get("businessId")

        self._ensure_mqtt()
        # Ask every device for its state. This is what keeps the PC state fresh
        # even though the device only publishes when something changes.
        for mac in self.devices:
            self._mqtt.request_state(mac)

        self._expire_silent_devices()
        return self.devices

    def _expire_silent_devices(self) -> None:
        """Mark a device offline when it stopped answering our refreshes.

        Home Assistant does not rewrite a state whose value did not change, so a
        device that goes silent would otherwise keep showing its last known
        state forever. A device that is merely steady still answers every
        `find`, which updates `state_updated_at`; only a truly silent device
        falls behind. Two missed rounds is enough to stop trusting it.
        """
        threshold = self.refresh_interval * 2 + STATE_WAIT_TIMEOUT
        now = time.monotonic()
        for device in self.devices.values():
            if device.state_updated_at is None:
                continue
            if now - device.state_updated_at > threshold and device.online:
                _LOGGER.warning(
                    "%s stopped reporting for %.0fs; marking offline",
                    device.mac,
                    now - device.state_updated_at,
                )
                device.online = False

    async def async_ensure_mqtt(self) -> None:
        """Start the MQTT client once, off the event loop."""
        if not self.devices or self._mqtt_active:
            return
        macs = list(self.devices)
        self._mqtt.set_devices(macs)
        # paho's connect() performs a blocking TCP handshake.
        await self.hass.async_add_executor_job(self._mqtt.connect)
        self._mqtt_active = True

    def _ensure_mqtt(self) -> None:
        """Update the tracked MACs; connection is started by async_ensure_mqtt."""
        if not self.devices or self._mqtt_active:
            return
        self._mqtt.set_devices(list(self.devices))

    # -- MQTT callbacks -----------------------------------------------------
    # These run on the paho network thread, so they must not touch the event
    # loop directly: state is stored here (plain attributes) and the reactive
    # work is scheduled onto the HA loop.
    def _handle_state(self, mac: str, state: list[int]) -> None:
        device = self.devices.get(mac)
        if device is None:
            return
        device.state = state
        device.state_updated_at = time.monotonic()

        def _notify() -> None:
            self.async_set_updated_data(self.devices)
            async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED, mac)

        self.hass.loop.call_soon_threadsafe(_notify)

    def _handle_online(self, mac: str, online: bool) -> None:
        device = self.devices.get(mac)
        if device is None:
            return
        device.online = online
        self.hass.loop.call_soon_threadsafe(
            self.async_set_updated_data, self.devices
        )

    def _handle_connection(self, connected: bool) -> None:
        """React to the broker link going up or down.

        Called from the paho network thread, so the work is handed to the HA
        event loop. While the link is down, every device is marked offline so
        entities turn `unavailable` instead of showing a state that can no
        longer be trusted. On reconnect, each device is asked for a fresh
        reading right away.
        """

        def _apply() -> None:
            if not connected:
                for device in self.devices.values():
                    device.online = False
                self.async_set_updated_data(self.devices)
                return
            for mac in self.devices:
                self._mqtt.request_state(mac)

        self.hass.loop.call_soon_threadsafe(_apply)

    # -- commands -----------------------------------------------------------
    def send_command(self, mac: str, payload: str) -> None:
        self._mqtt.send(mac, payload)

    def power_press(self, mac: str) -> None:
        """Short press of the power button: powers the PC on when it is off.

        Note: on a PC that is already running this does NOT shut it down; use
        `soft_off()` for that (verified live).
        """
        self.send_command(mac, CMD_POWER_PRESS)

    def soft_off(self, mac: str) -> None:
        """Ask the PC to shut down cleanly (the OS-driven power off)."""
        self.send_command(mac, CMD_SOFT_OFF)

    def force_off(self, mac: str) -> None:
        self.send_command(mac, CMD_FORCE_OFF)

    def set_power_boot(self, mac: str, enabled: bool) -> None:
        self.send_command(mac, CMD_POWER_BOOT_ON if enabled else CMD_POWER_BOOT_OFF)

    def read_state(self, mac: str) -> None:
        self.send_command(mac, CMD_READ)

    async def async_refresh_state_and_wait(
        self, mac: str, timeout: float = STATE_WAIT_TIMEOUT
    ) -> bool:
        """Ask a device for its state and wait for a fresh reading.

        Returns True when a state message arrives within the timeout after the
        request. The device answers a `find` on ClientProducerToServer<MAC>,
        usually within a second.
        """
        device = self.devices.get(mac)
        if device is None:
            return False

        started = time.monotonic()
        got_update = asyncio.Event()

        @callback
        def _on_update(updated_mac: str) -> None:
            if updated_mac == mac:
                got_update.set()

        unsub = async_dispatcher_connect(self.hass, SIGNAL_STATE_UPDATED, _on_update)
        try:
            self.read_state(mac)
            try:
                await asyncio.wait_for(got_update.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "No state returned by %s within %.1fs; refusing to act",
                    mac,
                    timeout,
                )
                return False
        finally:
            unsub()

        # A message that predates the request cannot be used to gate a command.
        if device.state_updated_at is None or device.state_updated_at < started:
            return False
        return True

    async def async_confirm_state_change(
        self,
        mac: str,
        expected_on: bool,
        interval: float = CONFIRM_INTERVAL,
        timeout: float = CONFIRM_TIMEOUT,
    ) -> bool:
        """After a press, refresh until the PC state matches the expectation.

        The module only publishes when something changes, and the PC takes a few
        seconds to actually power up or shut down, so a single refresh right
        after the press usually still reports the old state. This asks for a
        fresh state every `interval` seconds and stops as soon as the reported
        state matches `expected_on`, or when `timeout` is reached.

        Returns True when the change was confirmed, False when the deadline
        passed with the state still not matching.
        """
        device = self.devices.get(mac)
        if device is None:
            return False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.read_state(mac)
            # Give the device time to answer, then look at what it reported.
            await asyncio.sleep(interval)
            if device.pc_is_on == expected_on:
                _LOGGER.debug(
                    "State of %s confirmed as %s after press",
                    mac,
                    "on" if expected_on else "off",
                )
                return True

        _LOGGER.warning(
            "State of %s did not become %s within %.0fs",
            mac,
            "on" if expected_on else "off",
            timeout,
        )
        return False

    async def async_shutdown(self) -> None:
        self._mqtt.disconnect()
        self._mqtt_active = False


def _stored_interval(entry: ConfigEntry) -> int:
    """Return the saved refresh interval in seconds, clamped to the valid range."""
    raw = entry.options.get(
        CONF_REFRESH_INTERVAL,
        entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_REFRESH_INTERVAL
    return max(REFRESH_MIN, min(REFRESH_MAX, value))
