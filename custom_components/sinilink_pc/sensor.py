"""Sensor platform: diagnostics exposed by the controller."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    PC_STATE_FORCING_OFF,
    PC_STATE_OFF,
    PC_STATE_ON,
    PC_STATE_SHUTTING_DOWN,
    PC_STATE_SHUTTING_DOWN_ALT,
)
from .coordinator import SinilinkCoordinator
from .entity import SinilinkEntity

_LOGGER = logging.getLogger(__name__)

# Entities are updated by the shared coordinator, not by per-entity polling.
PARALLEL_UPDATES = 0

_STATE_NAMES = {
    PC_STATE_OFF: "off",
    PC_STATE_ON: "on",
    PC_STATE_SHUTTING_DOWN: "shutting_down",
    PC_STATE_SHUTTING_DOWN_ALT: "shutting_down",
    PC_STATE_FORCING_OFF: "forcing_off",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinilinkCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SinilinkStatusSensor(coordinator, device)
        for device in coordinator.devices.values()
    )


class SinilinkStatusSensor(SinilinkEntity, SensorEntity):
    """Raw status reported by the controller.

    Useful for automations that need the exact value (e.g. telling
    "forcing power off" apart from a plain "off").
    """

    _attr_translation_key = "pc_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: SinilinkCoordinator, device) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.mac}_pc_status"

    @property
    def native_value(self) -> str | None:
        device = self.device
        if not device or device.pc_state_raw is None:
            return None
        return _STATE_NAMES.get(device.pc_state_raw, str(device.pc_state_raw))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        device = self.device
        if not device:
            return {}
        return {
            "raw_param": device.state,
            "power_boot": device.power_boot,
            "prohibit_key": device.prohibit_key,
            "firmware": device.firmware,
            "group": device.group,
        }
