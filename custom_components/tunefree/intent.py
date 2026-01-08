"""Intent handlers for TuneFree - Expose tools for AI assistants."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


async def async_setup_intents(hass: HomeAssistant):
    """Set up the TuneFree intents."""
    intent.async_register(hass, TuneFreePlayMusicIntent())
    intent.async_register(hass, TuneFreePlayToplistIntent())
    intent.async_register(hass, TuneFreePlayPlaylistIntent())
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
        entity_id = slots.get("entity_id", {}).get("value") or "media_player.tunefree_service_tunefree_player"

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
    description = "播放音乐榜单。常用榜单ID：网易云飙升榜(19723756)、网易云新歌榜(3779629)、网易云热歌榜(3778678)。"
    slot_schema = {
        vol.Required("toplist_id", description="榜单ID"): intent.non_empty_string,
        vol.Optional("source", description="音乐平台: netease/kuwo/qq"): str,
        vol.Optional("shuffle", description="是否随机播放"): bool,
        vol.Optional("entity_id", description="TuneFree播放器实体ID"): str,
    }

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        toplist_id = slots.get("toplist_id", {}).get("value", "")
        source = slots.get("source", {}).get("value") or "netease"
        shuffle = slots.get("shuffle", {}).get("value") or False
        entity_id = slots.get("entity_id", {}).get("value") or "media_player.tunefree_service_tunefree_player"

        _LOGGER.info("TuneFreePlayToplist: toplist_id=%s, source=%s", toplist_id, source)

        try:
            await hass.services.async_call(
                DOMAIN,
                "play_toplist",
                {
                    "toplist_id": toplist_id,
                    "entity_id": entity_id,
                    "source": source,
                    "shuffle": shuffle,
                },
            )
            response = intent_obj.create_response()
            response.response_type = intent.IntentResponseType.ACTION_DONE
            response.async_set_speech(f"正在播放榜单")
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
        entity_id = slots.get("entity_id", {}).get("value") or "media_player.tunefree_service_tunefree_player"

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
