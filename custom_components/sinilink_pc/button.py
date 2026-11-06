"""Button platform: Power on, Power off, Force off and State refresh.

The controller sits on the motherboard's power-button pin, and the two power
commands are NOT symmetric (verified against the hardware):

    poweron  -> short press. Powers the PC ON when it is off. On a PC that is
                already running it does not shut it down.
    softoff  -> the clean, OS-driven shutdown.
    forceoff -> hold the button (~10s): immediate ATX cut.

Each button refreshes the state first and only acts when the state matches its
label, so pressing "Power on" on a running PC never turns it off (and vice
versa):

    * Power on  -> refresh, then `poweron` only if the PC is OFF
    * Power off -> refresh, then `softoff` only if the PC is ON

If the device does not answer the refresh, the button refuses to act rather
than command blind. After a command the state is refreshed until it changes.

"Force power off" is the hard ATX cut and is intentionally unconditional.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SinilinkCoordinator
from .entity import SinilinkEntity

_LOGGER = logging.getLogger(__name__)

# Buttons may wait for a fresh state, so let requests overlap.
PARALLEL_UPDATES = 5

# translation key -> icon. The command is dispatched in `async_press`.
BUTTONS: dict[str, str] = {
    "power_on": "mdi:power",
    "power_off": "mdi:power-off",
    "force_off": "mdi:power-plug-off",
    "refresh_state": "mdi:refresh",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinilinkCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SinilinkButton(coordinator, device, key)
        for device in coordinator.devices.values()
        for key in BUTTONS
    ]
    async_add_entities(entities)


class SinilinkButton(SinilinkEntity, ButtonEntity):
    """A button that sends a specific command to the controller."""

    def __init__(self, coordinator: SinilinkCoordinator, device, key: str) -> None:
        super().__init__(coordinator, device)
        self._key = key
        self._attr_unique_id = f"{device.mac}_{key}"
        self._attr_translation_key = key
        self._attr_icon = BUTTONS[key]

    async def async_press(self) -> None:
        """Refresh the PC state, then dispatch the command for this key."""
        device = self.device
        if device is None:
            return
        mac = device.mac

        if self._key == "refresh_state":
            self.coordinator.read_state(mac)
            return

        if self._key == "force_off":
            # Hard ATX cut: deliberately unconditional, no state gate.
            self.coordinator.force_off(mac)
            return

        # Power on / Power off: both are one short press of the power button, so
        # the decision must come from a FRESH state, never from a cached one.
        fresh = await self.coordinator.async_refresh_state_and_wait(mac)
        if not fresh:
            _LOGGER.warning(
                "Not pressing %s on %s: current state could not be confirmed",
                self._key,
                mac,
            )
            return

        is_on = device.pc_is_on
        if self._key == "power_on":
            if is_on:
                _LOGGER.debug("%s is already on; power_on ignored", mac)
                return
            self.coordinator.power_press(mac)
            expected_on = True
        elif self._key == "power_off":
            if not is_on:
                _LOGGER.debug("%s is already off; power_off ignored", mac)
                return
            # `poweron` only powers a PC on; shutting down needs `softoff`.
            self.coordinator.soft_off(mac)
            expected_on = False
        else:
            return

        # A press does not report its own result: the PC takes a few seconds to
        # power up or shut down, and the module only publishes on change. Keep
        # refreshing in the background until the expected state shows up, so the
        # dashboard follows on its own instead of needing a manual refresh.
        self.hass.async_create_task(
            self.coordinator.async_confirm_state_change(mac, expected_on)
        )
