"""Number platform: how often the integration refreshes the PC state.

The controller publishes its state on change, not periodically, so the
integration polls it with a harmless `find`. Without that polling the PC state
can sit stale. This entity exposes that interval (1 to 30 minutes) as an
adjustable number, one per controller.
"""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    REFRESH_MAX,
    REFRESH_MIN,
    REFRESH_STEP,
)
from .coordinator import SinilinkCoordinator
from .entity import SinilinkEntity

_LOGGER = logging.getLogger(__name__)

# Entities are updated by the shared coordinator, not by per-entity polling.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinilinkCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SinilinkRefreshIntervalNumber(coordinator, device)
        for device in coordinator.devices.values()
    )


class SinilinkRefreshIntervalNumber(SinilinkEntity, NumberEntity):
    """Seconds between two state refreshes (1 to 30 minutes)."""

    _attr_translation_key = "refresh_interval"
    _attr_icon = "mdi:timer-refresh"
    _attr_native_min_value = REFRESH_MIN
    _attr_native_max_value = REFRESH_MAX
    _attr_native_step = REFRESH_STEP
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SinilinkCoordinator, device) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{device.mac}_refresh_interval"

    @property
    def native_value(self) -> float:
        return self.coordinator.refresh_interval

    async def async_set_native_value(self, value: float) -> None:
        """Apply the new interval to the running coordinator and persist it."""
        await self.coordinator.async_set_refresh_interval(int(value))
        self.async_write_ha_state()
