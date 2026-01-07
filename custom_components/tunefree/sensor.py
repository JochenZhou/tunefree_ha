"""Platform for sensor entities."""
from __future__ import annotations

from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TuneFreeDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TuneFree sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = [
        TuneFreeHealthSensor(coordinator, entry),
    ]
    
    async_add_entities(entities)

class TuneFreeEntity(CoordinatorEntity):
    """Base TuneFree entity."""

    def __init__(self, coordinator: TuneFreeDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="TuneFree Service",
            manufacturer="TuneHub",
        )

class TuneFreeHealthSensor(TuneFreeEntity, BinarySensorEntity):
    """TuneFree API Health Sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "TuneFree API Status"

    def __init__(self, coordinator: TuneFreeDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_health"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.coordinator.data.get("health", False)
