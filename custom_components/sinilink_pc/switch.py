"""Switch platform: the "Power on after power loss" (power-boot) flag.

The controller can be told to press the power button by itself when the module
is re-energised while the PC is off (e.g. after a mains failure). That flag is
param[1] of the state array and is read/written with the `boot` command:

    {"method":"boot","param":"1"}   -> enabled
    {"method":"boot","param":"0"}   -> disabled

Note: `boot` WRITES. It is never used to read state — the read command is
`{"method":"find"}` (see const.CMD_READ).

The PC's own on/off state is deliberately NOT a switch here: the module has only
one physical action (a short press on the power button), so on/off are two
separate button entities instead.
"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SinilinkCoordinator
from .entity import SinilinkEntity

_LOGGER = logging.getLogger(__name__)

# Entities are updated by the shared coordinator, not by per-entity polling.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinilinkCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SinilinkPowerBootSwitch(coordinator, device)
        for device in coordinator.devices.values()
    )


class SinilinkPowerBootSwitch(SinilinkEntity, SwitchEntity):
    """Auto power-on when the module is re-energised with the PC off."""

    _attr_icon = "mdi:power-settings"
    _attr_translation_key = "power_boot"

    def __init__(self, coordinator: SinilinkCoordinator, device) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.mac}_power_boot"

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        return device.power_boot

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        device = self.device
        if not device:
            return {}
        return {"mac": device.mac, "raw_param": device.state}

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.set_power_boot(self._mac, True)

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.set_power_boot(self._mac, False)
