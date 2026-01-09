"""Intent handlers for TuneFree - Expose tools for AI assistants."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


def _find_tunefree_player(hass) -> str | None:
    """Find the first available TuneFree player entity."""
    for state in hass.states.async_all("media_player"):
        entity_id = state.entity_id
        if "tunefree" in entity_id.lower() and "player" in entity_id.lower():
            _LOGGER.debug("Found TuneFree player: %s", entity_id)
            return entity_id
    return None


async def async_setup_intents(hass: HomeAssistant):
    """Set up the TuneFree intents."""
    # Only register intents once to avoid "being overwritten" warnings
    if hass.data.get(DOMAIN, {}).get("_intents_registered"):
        return
    
    intent.async_register(hass, TuneFreePlayMusicIntent())
    intent.async_register(hass, TuneFreePlayToplistIntent())
    intent.async_register(hass, TuneFreePlayPlaylistIntent())
    
    # Mark as registered
    hass.data.setdefault(DOMAIN, {})["_intents_registered"] = True
    _LOGGER.info("TuneFree intents registered")


class TuneFreePlayMusicIntent(intent.IntentHandler):
    """Handle TuneFreePlayMusic intent."""

    intent_type = "TuneFreePlayMusic"
    description = "播放音乐。根据歌曲名、歌手名或关键词搜索并播放歌曲。"
    slot_schema = {
        vol.Required("keyword", description="歌曲名或歌手名"): intent.non_empty_string,
        vol.Optional("entity_id", description="TuneFree播放器实体ID"): str,
    }

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        keyword = slots.get("keyword", {}).get("value", "")
        entity_id = slots.get("entity_id", {}).get("value")
        
        # If no entity_id provided, find the TuneFree player dynamically
        if not entity_id:
            entity_id = _find_tunefree_player(hass)
            if not entity_id:
                _LOGGER.error("TuneFreePlayMusic: No TuneFree player found")
                response = intent_obj.create_response()
                response.response_type = intent.IntentResponseType.ERROR
                response.async_set_speech("未找到 TuneFree 播放器，请确保已配置目标播放器")
                return response

        _LOGGER.info("TuneFreePlayMusic: keyword=%s, entity_id=%s", keyword, entity_id)

        try:
            await hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": entity_id,
                    "media_content_id": keyword,
                    "media_content_type": "music",
                },
            )
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ACTION_DONE
            response.async_set_speech(f"正在搜索并播放: {keyword}")
            return response
        except Exception as e:
            _LOGGER.error("TuneFreePlayMusic failed: %s", e)
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(f"播放失败: {e}")
            return response


class TuneFreePlayToplistIntent(intent.IntentHandler):
    """Handle TuneFreePlayToplist intent."""

    intent_type = "TuneFreePlayToplist"
    description = ("播放音乐榜单。直接说出榜单名称即可，如'播放酷我热歌榜'、'播放网易云飙升榜'、'播放QQ新歌榜'等。"
                   "系统会自动匹配对应平台的榜单。支持的平台：网易云、酷我、QQ音乐。")
    slot_schema = {
        vol.Required("toplist_name", description="榜单名称，如'酷我热歌榜'、'网易云飙升榜'"): intent.non_empty_string,
        vol.Optional("shuffle", description="是否随机播放"): bool,
        vol.Optional("entity_id", description="TuneFree播放器实体ID"): str,
    }

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        toplist_name = slots.get("toplist_name", {}).get("value", "")
        shuffle = slots.get("shuffle", {}).get("value") or False
        entity_id = slots.get("entity_id", {}).get("value")
        
        # If no entity_id provided, find the TuneFree player dynamically
        if not entity_id:
            entity_id = _find_tunefree_player(hass)
            if not entity_id:
                _LOGGER.error("TuneFreePlayToplist: No TuneFree player found")
                response = intent_obj.create_response()
                response.response_type = intent.IntentResponseType.ERROR
                response.async_set_speech("未找到 TuneFree 播放器，请确保已配置目标播放器")
                return response

        _LOGGER.info("TuneFreePlayToplist: toplist_name=%s", toplist_name)
        
        # Determine which platform to search based on name
        platform_keywords = {
            "netease": ["网易", "网易云", "163"],
            "kuwo": ["酷我"],
            "qq": ["qq", "QQ", "腾讯"],
        }
        
        # Find matching platform from toplist_name
        target_sources = []
        toplist_name_lower = toplist_name.lower()
        for source, keywords in platform_keywords.items():
            for kw in keywords:
                if kw.lower() in toplist_name_lower:
                    target_sources = [source]
                    break
            if target_sources:
                break
        
        # If no platform specified, search all platforms
        if not target_sources:
            target_sources = ["netease", "kuwo", "qq"]
        
        # Get API instance
        api = None
        for key, value in hass.data.get(DOMAIN, {}).items():
            if isinstance(value, dict) and "api" in value:
                api = value["api"]
                break
        
        if not api:
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech("TuneFree 服务未就绪")
            return response
        
        # Search for matching toplist
        matched_toplist = None
        matched_source = None
        
        for source in target_sources:
            toplists = await api.get_toplists(source)
            for toplist in toplists:
                toplist_title = toplist.get("name", "").lower()
                # Check if any keyword from user input matches the toplist name
                search_terms = toplist_name_lower.replace("网易云", "").replace("网易", "").replace("酷我", "").replace("qq", "").replace("腾讯", "").strip()
                if search_terms and search_terms in toplist_title:
                    matched_toplist = toplist
                    matched_source = source
                    break
                # Also check if toplist name contains the search term
                if toplist_title in toplist_name_lower:
                    matched_toplist = toplist
                    matched_source = source
                    break
            if matched_toplist:
                break
        
        if not matched_toplist:
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(f"未找到匹配的榜单: {toplist_name}")
            return response
        
        toplist_id = str(matched_toplist.get("id"))
        toplist_display_name = matched_toplist.get("name", toplist_name)
        
        _LOGGER.info("TuneFreePlayToplist: matched %s from %s (id=%s)", toplist_display_name, matched_source, toplist_id)

        try:
            await hass.services.async_call(
                DOMAIN,
                "play_toplist",
                {
                    "toplist_id": toplist_id,
                    "entity_id": entity_id,
                    "source": matched_source,
                    "shuffle": shuffle,
                },
            )
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ACTION_DONE
            response.async_set_speech(f"正在播放{toplist_display_name}")
            return response
        except Exception as e:
            _LOGGER.error("TuneFreePlayToplist failed: %s", e)
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(f"播放榜单失败: {e}")
            return response


class TuneFreePlayPlaylistIntent(intent.IntentHandler):
    """Handle TuneFreePlayPlaylist intent."""

    intent_type = "TuneFreePlayPlaylist"
    description = "播放已导入的歌单。根据歌单名称播放已导入到 TuneFree 的歌单。"
    slot_schema = {
        vol.Required("playlist_name", description="歌单名称"): intent.non_empty_string,
        vol.Optional("shuffle", description="是否随机播放"): bool,
        vol.Optional("entity_id", description="TuneFree播放器实体ID"): str,
    }

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        playlist_name = slots.get("playlist_name", {}).get("value", "")
        shuffle = slots.get("shuffle", {}).get("value") or False
        entity_id = slots.get("entity_id", {}).get("value")
        
        # If no entity_id provided, find the TuneFree player dynamically
        if not entity_id:
            entity_id = _find_tunefree_player(hass)
            if not entity_id:
                _LOGGER.error("TuneFreePlayPlaylist: No TuneFree player found")
                response = intent_obj.create_response()
                response.response_type = intent.IntentResponseType.ERROR
                response.async_set_speech("未找到 TuneFree 播放器，请确保已配置目标播放器")
                return response

        _LOGGER.info("TuneFreePlayPlaylist: playlist_name=%s", playlist_name)

        # Load saved playlists and find matching
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        data = await store.async_load()
        saved_playlists = data.get("playlists", []) if data else []

        matched_playlist = None
        for p in saved_playlists:
            if playlist_name.lower() in p["name"].lower() or p["name"].lower() in playlist_name.lower():
                matched_playlist = p
                break

        if not matched_playlist:
            available = [p["name"] for p in saved_playlists] if saved_playlists else ["无"]
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(f"未找到歌单 '{playlist_name}'，可用歌单: {', '.join(available)}")
            return response

        try:
            await hass.services.async_call(
                DOMAIN,
                "play_playlist",
                {
                    "playlist_id": matched_playlist["id"],
                    "entity_id": entity_id,
                    "source": matched_playlist["source"],
                    "shuffle": shuffle,
                },
            )
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ACTION_DONE
            response.async_set_speech(f"正在播放歌单: {matched_playlist['name']}")
            return response
        except Exception as e:
            _LOGGER.error("TuneFreePlayPlaylist failed: %s", e)
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_speech(f"播放歌单失败: {e}")
            return response
