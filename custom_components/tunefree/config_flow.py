"""Config flow for TuneFree integration."""
import logging
import re
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.media_player import DOMAIN as MP_DOMAIN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from homeassistant.helpers.storage import Store
from homeassistant.core import callback

from .const import (
    DOMAIN, 
    CONF_API_URL, 
    CONF_TARGET_PLAYER, 
    CONF_DEFAULT_SOURCE,
    DEFAULT_API_URL, 
    DEFAULT_SOURCE,
    SOURCES,
    PLAYLIST_SOURCES,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .api import TuneFreeAPI

_LOGGER = logging.getLogger(__name__)


def extract_playlist_id(url_or_id: str) -> str:
    """Extract playlist ID from URL or return as-is if already an ID."""
    # Try to extract ID from common URL formats
    patterns = [
        r'id=(\d+)',  # ?id=123456
        r'/playlist/(\d+)',  # /playlist/123456
        r'playlist\?.*id=(\d+)',  # playlist?...id=123456
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    # Return as-is if no URL pattern matched (assume it's already an ID)
    return url_or_id.strip()


class TuneFreeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TuneFree."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_url: str = DEFAULT_API_URL

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return TuneFreeOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step - API URL configuration."""
        errors: Dict[str, str] = {}
        
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = TuneFreeAPI(session, user_input[CONF_API_URL])
            
            try:
                if not await api.get_health():
                    raise Exception("Unhealthy API")
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                self._api_url = user_input[CONF_API_URL]
                return await self.async_step_player()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str,
                }
            ),
            errors=errors,
        )

    async def async_step_player(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the player and source selection step."""
        if user_input is not None:
            return self.async_create_entry(
                title="TuneFree",
                data={
                    CONF_API_URL: self._api_url,
                    CONF_TARGET_PLAYER: user_input.get(CONF_TARGET_PLAYER),
                    CONF_DEFAULT_SOURCE: user_input.get(CONF_DEFAULT_SOURCE, DEFAULT_SOURCE),
                },
            )

        return self.async_show_form(
            step_id="player",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_TARGET_PLAYER): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=MP_DOMAIN)
                    ),
                    vol.Required(CONF_DEFAULT_SOURCE, default=DEFAULT_SOURCE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in SOURCES.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )


class TuneFreeOptionsFlow(config_entries.OptionsFlow):
    """Handle TuneFree options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry
        self._store: Store | None = None

    async def _get_store(self) -> Store:
        """Get or create storage."""
        if self._store is None:
            self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)
        return self._store

    async def _load_playlists(self) -> list:
        """Load saved playlists from storage."""
        store = await self._get_store()
        data = await store.async_load()
        return data.get("playlists", []) if data else []

    async def _save_playlists(self, playlists: list) -> None:
        """Save playlists to storage."""
        store = await self._get_store()
        await store.async_save({"playlists": playlists})

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Show menu for options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "import_playlist", "manage_playlists"],
        )

    async def async_step_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage basic settings."""
        if user_input is not None:
            new_data = {**self._entry.data}
            new_data[CONF_TARGET_PLAYER] = user_input.get(CONF_TARGET_PLAYER)
            new_data[CONF_DEFAULT_SOURCE] = user_input.get(CONF_DEFAULT_SOURCE, DEFAULT_SOURCE)
            
            self.hass.config_entries.async_update_entry(
                self._entry, data=new_data
            )
            
            await self.hass.config_entries.async_reload(self._entry.entry_id)
            return self.async_create_entry(title="", data={})

        current_player = self._entry.data.get(CONF_TARGET_PLAYER)
        current_source = self._entry.data.get(CONF_DEFAULT_SOURCE, DEFAULT_SOURCE)
        
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TARGET_PLAYER,
                        default=current_player,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=MP_DOMAIN)
                    ),
                    vol.Required(
                        CONF_DEFAULT_SOURCE,
                        default=current_source,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in SOURCES.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_import_playlist(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Import a playlist by URL or ID."""
        errors: Dict[str, str] = {}
        
        if user_input is not None:
            playlist_url = user_input.get("playlist_url", "")
            source = user_input.get("source", "netease")
            
            # Extract playlist ID
            playlist_id = extract_playlist_id(playlist_url)
            
            if not playlist_id:
                errors["base"] = "invalid_playlist"
            else:
                # Fetch playlist info
                session = async_get_clientsession(self.hass)
                api = TuneFreeAPI(session, self._entry.data[CONF_API_URL])
                
                playlist_data = await api.get_playlist(playlist_id, source)
                
                if not playlist_data:
                    errors["base"] = "playlist_not_found"
                else:
                    # Extract playlist name from response
                    # Structure: data.info.name contains the playlist name
                    songs = playlist_data.get("list", [])
                    info = playlist_data.get("info", {})
                    playlist_name = (
                        info.get("name") or
                        playlist_data.get("name") or
                        playlist_data.get("title") or
                        f"歌单 {playlist_id}"
                    )
                    
                    # Save playlist
                    playlists = await self._load_playlists()
                    
                    # Check if already exists
                    existing = next((p for p in playlists if p["id"] == playlist_id and p["source"] == source), None)
                    if existing:
                        # Update existing
                        existing["name"] = playlist_name
                        existing["count"] = len(songs)
                    else:
                        # Add new
                        playlists.append({
                            "id": playlist_id,
                            "source": source,
                            "name": playlist_name,
                            "count": len(songs),
                        })
                    
                    await self._save_playlists(playlists)
                    
                    # Reload to update media browser
                    await self.hass.config_entries.async_reload(self._entry.entry_id)
                    
                    return self.async_create_entry(title="", data={})
        
        return self.async_show_form(
            step_id="import_playlist",
            data_schema=vol.Schema(
                {
                    vol.Required("playlist_url"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                    vol.Required("source", default="netease"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in PLAYLIST_SOURCES.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "example": "https://music.163.com/playlist?id=123456789 或直接输入 ID"
            },
        )

    async def async_step_manage_playlists(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage saved playlists."""
        playlists = await self._load_playlists()
        
        if user_input is not None:
            # Remove selected playlists
            to_remove = user_input.get("remove_playlists", [])
            if to_remove:
                playlists = [p for p in playlists if f"{p['source']}:{p['id']}" not in to_remove]
                await self._save_playlists(playlists)
                await self.hass.config_entries.async_reload(self._entry.entry_id)
            
            return self.async_create_entry(title="", data={})
        
        if not playlists:
            return self.async_show_form(
                step_id="manage_playlists",
                data_schema=vol.Schema({}),
                description_placeholders={"info": "暂无已导入的歌单"},
            )
        
        playlist_options = [
            selector.SelectOptionDict(
                value=f"{p['source']}:{p['id']}",
                label=f"{p['name']} ({p['count']}首) - {PLAYLIST_SOURCES.get(p['source'], p['source'])}"
            )
            for p in playlists
        ]
        
        return self.async_show_form(
            step_id="manage_playlists",
            data_schema=vol.Schema(
                {
                    vol.Optional("remove_playlists"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=playlist_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={
                "info": f"已导入 {len(playlists)} 个歌单"
            },
        )
