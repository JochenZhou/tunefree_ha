"""The TuneFree integration."""
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.components import media_source

from .const import DOMAIN, CONF_API_URL, CONF_DEFAULT_SOURCE, DEFAULT_SOURCE
from .api import TuneFreeAPI

from .coordinator import TuneFreeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.MEDIA_PLAYER]

# Service schemas
PLAY_MUSIC_SCHEMA = vol.Schema({
    vol.Required("keyword"): cv.string,
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("source"): cv.string,
})

SEARCH_MUSIC_SCHEMA = vol.Schema({
    vol.Required("keyword"): cv.string,
    vol.Optional("limit", default=10): cv.positive_int,
    vol.Optional("source"): cv.string,
})

PLAY_TOPLIST_SCHEMA = vol.Schema({
    vol.Required("toplist_id"): cv.string,
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("source", default="netease"): cv.string,
    vol.Optional("shuffle", default=False): cv.boolean,
})

PLAY_SEARCH_LIST_SCHEMA = vol.Schema({
    vol.Required("keyword"): cv.string,
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("limit", default=20): cv.positive_int,
    vol.Optional("source"): cv.string,
    vol.Optional("shuffle", default=False): cv.boolean,
})

PLAY_PLAYLIST_SCHEMA = vol.Schema({
    vol.Required("playlist_id"): cv.string,
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("source", default="netease"): cv.string,
    vol.Optional("shuffle", default=False): cv.boolean,
})

GET_LYRICS_SCHEMA = vol.Schema({
    vol.Required("song_id"): cv.string,
    vol.Optional("source", default="netease"): cv.string,
})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TuneFree from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Register static path for custom card (only once)
    if "_static_registered" not in hass.data[DOMAIN]:
        from homeassistant.components.http import StaticPathConfig
        try:
            await hass.http.async_register_static_paths([
                StaticPathConfig(
                    "/tunefree/tunefree-lyrics-card.js",
                    hass.config.path("custom_components/tunefree/www/tunefree-lyrics-card.js"),
                    cache_headers=False,
                )
            ])
        except RuntimeError:
            pass  # Already registered
        
        # Auto register lovelace resource
        try:
            from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
            from homeassistant.components.lovelace.resources import ResourceStorageCollection
            
            if LOVELACE_DOMAIN in hass.data:
                lovelace = hass.data[LOVELACE_DOMAIN]
                if hasattr(lovelace, "resources") and isinstance(lovelace.resources, ResourceStorageCollection):
                    resources = lovelace.resources
                    url = "/tunefree/tunefree-lyrics-card.js"
                    # Check if already registered
                    existing = [r for r in resources.async_items() if r.get("url") == url]
                    if not existing:
                        await resources.async_create_item({"url": url, "res_type": "module"})
                        _LOGGER.info("TuneFree lyrics card resource registered")
        except Exception as e:
            _LOGGER.debug("Could not auto-register lovelace resource: %s", e)
        
        hass.data[DOMAIN]["_static_registered"] = True
    
    session = async_get_clientsession(hass)
    api_url = entry.data[CONF_API_URL]
    api = TuneFreeAPI(session, api_url)
    
    coordinator = TuneFreeDataUpdateCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "default_source": entry.data.get(CONF_DEFAULT_SOURCE, DEFAULT_SOURCE),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Get default source from config
    default_source = entry.data.get(CONF_DEFAULT_SOURCE, DEFAULT_SOURCE)

    # Register Custom Services
    async def handle_play_music(call: ServiceCall):
        """Handle the play_music service."""
        keyword = call.data.get("keyword")
        entity_id = call.data.get("entity_id")
        source = call.data.get("source", default_source)
        
        if not keyword or not entity_id:
            _LOGGER.error("Keyword and entity_id are required")
            return

        _LOGGER.info(f"Searching for '{keyword}' (source: {source}) to play on {entity_id}")
        
        # Determine search type based on source
        if source == "all":
            search_type = "aggregateSearch"
            songs = await api.search(keyword, search_type=search_type)
        else:
            songs = await api.search(keyword, source=source, search_type="search")
        
        if not songs:
            _LOGGER.warning(f"No songs found for '{keyword}'")
            return
            
        song = songs[0]
        song_id = str(song.get("id"))
        song_name = song.get("name", "Unknown")
        song_artist = song.get("artist", "")
        source = song.get("platform", "netease")
        
        if not song_id:
             _LOGGER.error("Song found but has no ID")
             return

        # Get URL Endpoint
        url_endpoint = api.get_song_url_endpoint(song_id, source=source)
        
        # Resolve Redirect
        final_url = await api.resolve_song_redirect(url_endpoint)
        
        if not final_url:
             _LOGGER.warning(f"Could not resolve URL for song '{song_name}' (ID: {song_id})")
             return
        
        # Get song info for cover art
        song_info = await api.get_song_info(song_id, source=source)
        thumbnail = None
        if song_info:
            thumbnail = song_info.get("pic")
            if not thumbnail:
                thumbnail = f"{api._api_url}/api/?source={source}&id={song_id}&type=pic"
             
        # Play with metadata
        service_data = {
            "entity_id": entity_id,
            "media_content_id": final_url,
            "media_content_type": "music",
        }
        
        # Add extra metadata for players that support it
        extra = {}
        if thumbnail:
            extra["thumb"] = thumbnail
            extra["entity_picture"] = thumbnail
        extra["title"] = song_name
        extra["artist"] = song_artist
        
        if extra:
            service_data["extra"] = extra
        
        await hass.services.async_call(
            "media_player",
            "play_media",
            service_data,
        )

    async def handle_search_music(call: ServiceCall) -> ServiceResponse:
        """Handle the search_music service - returns results for MCP/AI assistants."""
        keyword = call.data.get("keyword")
        limit = call.data.get("limit", 10)
        
        if not keyword:
            return {"success": False, "error": "Keyword is required", "results": []}

        _LOGGER.info(f"MCP/AI Search: '{keyword}' (limit: {limit})")
        
        # Search using aggregate search
        songs = await api.search(keyword, search_type="aggregateSearch")
        
        if not songs:
            return {
                "success": True,
                "keyword": keyword,
                "count": 0, 
                "results": [],
                "message": f"没有找到与 '{keyword}' 相关的音乐"
            }
        
        # Format results for AI/MCP consumption
        results = []
        for i, song in enumerate(songs[:limit]):
            song_id = str(song.get("id"))
            source = song.get("platform", "netease")
            results.append({
                "index": i + 1,
                "id": song_id,
                "name": song.get("name", "未知歌曲"),
                "artist": song.get("artist", "未知歌手"),
                "platform": source,
                "media_content_id": f"media-source://tunefree/{source}:{song_id}",
                "play_command": f"在 TuneFree Player 上播放 media_content_id: media-source://tunefree/{source}:{song_id}",
            })
        
        return {
            "success": True,
            "keyword": keyword,
            "count": len(results),
            "results": results,
            "message": f"找到 {len(results)} 首与 '{keyword}' 相关的音乐",
            "usage_hint": "使用 media_player.play_media 服务，将 media_content_id 传递给 TuneFree Player 即可播放"
        }

    async def handle_play_toplist(call: ServiceCall):
        """Handle the play_toplist service - play songs from a chart."""
        import random
        
        toplist_id = call.data.get("toplist_id")
        entity_id = call.data.get("entity_id")
        source = call.data.get("source", default_source)
        shuffle = call.data.get("shuffle", False)
        
        _LOGGER.info(f"Playing toplist {toplist_id} from {source} on {entity_id}")
        
        # Get songs from toplist
        songs = await api.get_toplist_songs(toplist_id, source)
        if not songs:
            _LOGGER.warning(f"No songs found in toplist {toplist_id}")
            return
        
        # Add source info to each song
        for song in songs:
            song["source"] = source
        
        if shuffle:
            random.shuffle(songs)
        
        # Check if entity is the TuneFree player - use set_playlist for queue
        tunefree_player_id = f"media_player.{DOMAIN}_{entry.entry_id.replace('-', '_')}_tunefree_player"
        if entity_id.startswith("media_player.tunefree"):
            # Find the TuneFree player entity
            from homeassistant.helpers import entity_registry as er
            registry = er.async_get(hass)
            entity_entry = registry.async_get(entity_id)
            if entity_entry:
                entity = hass.data["entity_components"]["media_player"].get_entity(entity_id)
                if entity and hasattr(entity, "set_playlist"):
                    await entity.set_playlist(songs)
                    _LOGGER.info(f"Playing toplist: {len(songs)} songs via TuneFree queue")
                    return
        
        # Fallback: play first song via service call
        first_song = songs[0]
        song_id = str(first_song.get("id"))
        song_name = first_song.get("name", "Unknown")
        song_artist = first_song.get("artist", "")
        
        url_endpoint = api.get_song_url_endpoint(song_id, source=source)
        final_url = await api.resolve_song_redirect(url_endpoint)
        
        if not final_url:
            _LOGGER.error(f"Could not resolve URL for song {song_id}")
            return
        
        song_info = await api.get_song_info(song_id, source=source)
        thumbnail = song_info.get("pic") if song_info else None
        
        await hass.services.async_call("media_player", "play_media", {
            "entity_id": entity_id,
            "media_content_id": final_url,
            "media_content_type": "music",
            "extra": {"title": song_name, "artist": song_artist, "thumb": thumbnail},
        })
        _LOGGER.info(f"Playing toplist (single): '{song_name}'")

    async def handle_play_search_list(call: ServiceCall):
        """Handle the play_search_list service - search and play results as queue."""
        import random
        
        keyword = call.data.get("keyword")
        entity_id = call.data.get("entity_id")
        limit = call.data.get("limit", 20)
        source = call.data.get("source", default_source)
        shuffle = call.data.get("shuffle", False)
        
        _LOGGER.info(f"Searching '{keyword}' (limit: {limit}) to play on {entity_id}")
        
        # Search for songs
        if source == "all":
            songs = await api.search(keyword, search_type="aggregateSearch")
        else:
            songs = await api.search(keyword, source=source, search_type="search")
        
        if not songs:
            _LOGGER.warning(f"No songs found for '{keyword}'")
            return
        
        # Limit results and add source info
        songs = songs[:limit]
        for song in songs:
            if "platform" not in song and "source" not in song:
                song["source"] = source if source != "all" else "netease"
        
        if shuffle:
            random.shuffle(songs)
        
        # Check if entity is the TuneFree player - use set_playlist for queue
        if entity_id.startswith("media_player.tunefree"):
            entity = hass.data["entity_components"]["media_player"].get_entity(entity_id)
            if entity and hasattr(entity, "set_playlist"):
                await entity.set_playlist(songs)
                _LOGGER.info(f"Playing search '{keyword}': {len(songs)} songs via TuneFree queue")
                return
        
        # Fallback: play first song via service call
        first_song = songs[0]
        song_id = str(first_song.get("id"))
        song_name = first_song.get("name", "Unknown")
        song_artist = first_song.get("artist", "")
        song_source = first_song.get("platform", first_song.get("source", "netease"))
        
        url_endpoint = api.get_song_url_endpoint(song_id, source=song_source)
        final_url = await api.resolve_song_redirect(url_endpoint)
        
        if not final_url:
            _LOGGER.error(f"Could not resolve URL for song {song_id}")
            return
        
        song_info = await api.get_song_info(song_id, source=song_source)
        thumbnail = song_info.get("pic") if song_info else None
        
        await hass.services.async_call("media_player", "play_media", {
            "entity_id": entity_id,
            "media_content_id": final_url,
            "media_content_type": "music",
            "extra": {"title": song_name, "artist": song_artist, "thumb": thumbnail},
        })
        _LOGGER.info(f"Playing search (single): '{song_name}'")

    async def handle_play_playlist(call: ServiceCall):
        """Handle the play_playlist service - import and play a playlist."""
        import random
        
        playlist_id = call.data.get("playlist_id")
        entity_id = call.data.get("entity_id")
        source = call.data.get("source", default_source)
        shuffle = call.data.get("shuffle", False)
        
        _LOGGER.info(f"Playing playlist {playlist_id} from {source} on {entity_id}")
        
        # Get playlist data
        playlist_data = await api.get_playlist(playlist_id, source)
        if not playlist_data:
            _LOGGER.warning(f"Could not load playlist {playlist_id}")
            return
        
        songs = playlist_data.get("list", [])
        if not songs:
            _LOGGER.warning(f"No songs in playlist {playlist_id}")
            return
        
        # Add source to each song
        for song in songs:
            song["source"] = source
        
        if shuffle:
            random.shuffle(songs)
        
        # Use TuneFree player's set_playlist if available
        if entity_id.startswith("media_player.tunefree"):
            entity = hass.data["entity_components"]["media_player"].get_entity(entity_id)
            if entity and hasattr(entity, "set_playlist"):
                await entity.set_playlist(songs)
                _LOGGER.info(f"Playing playlist: {len(songs)} songs via TuneFree queue")
                return
        
        # Fallback: play first song
        first_song = songs[0]
        song_id = str(first_song.get("id"))
        song_name = first_song.get("name", "Unknown")
        song_artist = first_song.get("artist", "")
        
        url_endpoint = api.get_song_url_endpoint(song_id, source=source)
        final_url = await api.resolve_song_redirect(url_endpoint)
        
        if final_url:
            await hass.services.async_call("media_player", "play_media", {
                "entity_id": entity_id,
                "media_content_id": final_url,
                "media_content_type": "music",
            })

    async def handle_get_lyrics(call: ServiceCall) -> ServiceResponse:
        """Handle the get_lyrics service - return lyrics for a song."""
        song_id = call.data.get("song_id")
        source = call.data.get("source", default_source)
        
        _LOGGER.info(f"Getting lyrics for song {song_id} from {source}")
        
        lyrics = await api.get_lyrics(song_id, source)
        
        if lyrics:
            return {
                "success": True,
                "song_id": song_id,
                "source": source,
                "lyrics": lyrics,
            }
        else:
            return {
                "success": False,
                "song_id": song_id,
                "source": source,
                "lyrics": "",
                "error": "无法获取歌词"
            }

    # Register services
    hass.services.async_register(
        DOMAIN, 
        "play_music", 
        handle_play_music,
        schema=PLAY_MUSIC_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN, 
        "search_music", 
        handle_search_music,
        schema=SEARCH_MUSIC_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    
    hass.services.async_register(
        DOMAIN,
        "play_toplist",
        handle_play_toplist,
        schema=PLAY_TOPLIST_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        "play_search_list",
        handle_play_search_list,
        schema=PLAY_SEARCH_LIST_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        "play_playlist",
        handle_play_playlist,
        schema=PLAY_PLAYLIST_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        "get_lyrics",
        handle_get_lyrics,
        schema=GET_LYRICS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
