"""Shared entity helpers for the Sinilink PC Power integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinilinkCoordinator, SinilinkDevice


class SinilinkEntity(CoordinatorEntity[SinilinkCoordinator]):
    """Base class binding an entity to one controller."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SinilinkCoordinator, device: SinilinkDevice) -> None:
        super().__init__(coordinator)
        self._mac = device.mac

    @property
    def device(self) -> SinilinkDevice | None:
        """The controller this entity belongs to."""
        return self.coordinator.devices.get(self._mac)

    @property
    def available(self) -> bool:
        """Entities are unavailable while the controller is offline."""
        device = self.device
        return bool(device and device.online)

    @property
    def device_info(self) -> DeviceInfo:
        device = self.device
        name = device.name if device else self._mac
        model = "XY-WPCE PC power controller"
        if device and device.model:
            model = device.model
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=name,
            manufacturer="Sinilink",
            model=model,
            sw_version=device.firmware if device else None,
        )
