"""Data Update Coordinator for TuneFree."""
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TuneFreeAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class TuneFreeDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching TuneFree data."""

    def __init__(self, hass: HomeAssistant, api: TuneFreeAPI) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.api = api

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        try:
            health = await self.api.get_health()
            return {
                "health": health,
            }
        except Exception as err:
            _LOGGER.warning("Failed to update TuneFree data: %s", err)
            return {"health": False}
