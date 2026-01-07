"""Media Player platform for TuneFree."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    MediaClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import DOMAIN, CONF_TARGET_PLAYER
from .api import TuneFreeAPI

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TuneFree media player platform."""
    target_player = entry.data.get(CONF_TARGET_PLAYER)
    
    if not target_player:
        _LOGGER.debug("No target player configured, skipping media player setup")
        return
    
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    async_add_entities([TuneFreeMediaPlayer(hass, entry, api, target_player)])

class TuneFreeMediaPlayer(MediaPlayerEntity):
    """TuneFree Media Player that wraps another player."""

    _attr_has_entity_name = True
    _attr_name = "TuneFree Player"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: TuneFreeAPI,
        target_player: str,
    ) -> None:
        """Initialize the TuneFree media player."""
        self.hass = hass
        self._entry = entry
        self._api = api
        self._target_player = target_player
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="TuneFree Service",
            manufacturer="TuneHub",
        )
        
        # Current media info
        self._media_title: str | None = None
        self._media_artist: str | None = None
        self._media_image_url: str | None = None
        self._media_content_id: str | None = None
        self._current_song_id: str | None = None
        self._current_source: str | None = None
        self._lyrics: str | None = None
        
        # Playlist queue
        self._playlist: list[dict] = []
        self._playlist_index: int = 0
        self._last_state: str | None = None
        self._shuffle: bool = False
        self._repeat: str = "off"  # off, all, one

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Track state changes of the target player
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._target_player], self._async_target_state_changed
            )
        )

    @callback
    def _async_target_state_changed(self, event) -> None:
        """Handle target player state changes."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if new_state is None:
            return
        
        current_state = new_state.state
        previous_state = old_state.state if old_state else None
        
        # Auto-advance: when player goes from playing to idle, play next track
        if (
            previous_state == "playing" 
            and current_state == "idle" 
            and self._playlist
        ):
            if self._repeat == "one":
                # Repeat current track
                self.hass.async_create_task(self._play_current_track())
            elif self._playlist_index < len(self._playlist) - 1:
                self._playlist_index += 1
                self.hass.async_create_task(self._play_current_track())
            elif self._repeat == "all":
                # Loop back to start
                self._playlist_index = 0
                self.hass.async_create_task(self._play_current_track())
        
        self.async_write_ha_state()

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the player."""
        target_state = self.hass.states.get(self._target_player)
        if not target_state or target_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return MediaPlayerState.IDLE
        
        state_map = {
            "playing": MediaPlayerState.PLAYING,
            "paused": MediaPlayerState.PAUSED,
            "idle": MediaPlayerState.IDLE,
            "off": MediaPlayerState.OFF,
            "on": MediaPlayerState.ON,
            "buffering": MediaPlayerState.BUFFERING,
        }
        return state_map.get(target_state.state, MediaPlayerState.IDLE)

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported features based on target player."""
        # TuneFree's own features
        features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.SHUFFLE_SET
            | MediaPlayerEntityFeature.REPEAT_SET
        )
        # Add target player's volume/seek features
        target_state = self.hass.states.get(self._target_player)
        if target_state:
            target_features = target_state.attributes.get("supported_features", 0)
            if target_features & MediaPlayerEntityFeature.VOLUME_SET:
                features |= MediaPlayerEntityFeature.VOLUME_SET
            if target_features & MediaPlayerEntityFeature.VOLUME_STEP:
                features |= MediaPlayerEntityFeature.VOLUME_STEP
            if target_features & MediaPlayerEntityFeature.VOLUME_MUTE:
                features |= MediaPlayerEntityFeature.VOLUME_MUTE
            if target_features & MediaPlayerEntityFeature.SEEK:
                features |= MediaPlayerEntityFeature.SEEK
            if target_features & MediaPlayerEntityFeature.TURN_ON:
                features |= MediaPlayerEntityFeature.TURN_ON
            if target_features & MediaPlayerEntityFeature.TURN_OFF:
                features |= MediaPlayerEntityFeature.TURN_OFF
        return features

    @property
    def volume_level(self) -> float | None:
        """Return the volume level."""
        target_state = self.hass.states.get(self._target_player)
        if target_state:
            return target_state.attributes.get("volume_level")
        return None

    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        return self._media_title

    @property
    def media_artist(self) -> str | None:
        """Return the artist of current playing media."""
        return self._media_artist

    @property
    def media_image_url(self) -> str | None:
        """Return the image URL of current playing media."""
        return self._media_image_url

    @property
    def media_content_id(self) -> str | None:
        """Return the content ID of current playing media."""
        return self._media_content_id

    @property
    def media_content_type(self) -> MediaType | str | None:
        """Return the content type of current playing media."""
        return MediaType.MUSIC

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {
            "playlist_count": len(self._playlist),
            "playlist_position": self._playlist_index + 1 if self._playlist else 0,
        }
        if self._current_song_id:
            attrs["song_id"] = self._current_song_id
        if self._current_source:
            attrs["source"] = self._current_source
        if self._lyrics:
            attrs["lyrics"] = self._lyrics
        return attrs

    async def set_playlist(self, songs: list[dict], start_index: int = 0) -> None:
        """Set the playlist queue and start playing."""
        self._playlist = songs
        self._playlist_index = start_index
        if songs:
            await self._play_current_track()

    async def _play_current_track(self) -> None:
        """Play the current track in the playlist."""
        if not self._playlist or self._playlist_index >= len(self._playlist):
            return
        
        song = self._playlist[self._playlist_index]
        song_id = str(song.get("id"))
        source = song.get("platform", song.get("source", "netease"))
        
        self._media_title = song.get("name", "未知歌曲")
        self._media_artist = song.get("artist", "")
        self._media_image_url = song.get("pic")
        self._current_song_id = song_id
        self._current_source = source
        
        # Get playback URL
        url_endpoint = self._api.get_song_url_endpoint(song_id, source=source)
        final_url = await self._api.resolve_song_redirect(url_endpoint)
        
        if not final_url:
            # Try next track if this one fails
            if self._playlist_index < len(self._playlist) - 1:
                self._playlist_index += 1
                await self._play_current_track()
            return
        
        self._media_content_id = f"media-source://tunefree/{source}:{song_id}"
        
        # Get cover if not available
        if not self._media_image_url:
            song_info = await self._api.get_song_info(song_id, source=source)
            if song_info:
                self._media_image_url = song_info.get("pic")
        
        # Fetch lyrics asynchronously
        self._lyrics = await self._api.get_lyrics(song_id, source)
        
        # Forward to target player
        extra = {
            "title": self._media_title,
            "artist": self._media_artist,
            "thumb": self._media_image_url,
            "entity_picture": self._media_image_url,
        }
        
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": self._target_player,
                "media_content_id": final_url,
                "media_content_type": "music",
                "extra": extra,
            },
        )
        self.async_write_ha_state()

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media on the TuneFree player.
        
        Supports:
        - toplist:source:list_id - Play entire toplist as queue
        - media-source://tunefree/source:song_id - Direct song play
        - search:keyword - Search and play first result (voice assistant)
        - Any other URL - Forward to target player
        """
        _LOGGER.info("TuneFree Player: Playing media %s (type: %s)", media_id, media_type)
        
        # Handle toplist playback - play entire chart as queue
        if media_id.startswith("toplist:") and not media_id.startswith("toplist_song:"):
            parts = media_id.split(":")
            if len(parts) == 3:
                source = parts[1]
                list_id = parts[2]
                _LOGGER.info("TuneFree: Playing toplist %s from %s", list_id, source)
                
                songs = await self._api.get_toplist_songs(list_id, source)
                if songs:
                    # Add source to each song
                    for song in songs:
                        song["source"] = source
                    await self.set_playlist(songs)
                    return
                else:
                    _LOGGER.warning("No songs found in toplist %s", list_id)
                    return
        
        # Handle toplist song - play from specific index in toplist
        if media_id.startswith("toplist_song:"):
            parts = media_id.split(":")
            if len(parts) == 4:
                source = parts[1]
                list_id = parts[2]
                start_index = int(parts[3])
                _LOGGER.info("TuneFree: Playing toplist %s from index %d", list_id, start_index)
                
                songs = await self._api.get_toplist_songs(list_id, source)
                if songs:
                    for song in songs:
                        song["source"] = source
                    await self.set_playlist(songs, start_index=start_index)
                    return
                else:
                    _LOGGER.warning("No songs found in toplist %s", list_id)
                    return
        
        # Handle playlist playback - play entire playlist as queue
        if media_id.startswith("playlist:") and not media_id.startswith("playlist_song:"):
            parts = media_id.split(":")
            if len(parts) == 3:
                source = parts[1]
                playlist_id = parts[2]
                _LOGGER.info("TuneFree: Playing playlist %s from %s", playlist_id, source)
                
                playlist_data = await self._api.get_playlist(playlist_id, source)
                if playlist_data:
                    songs = playlist_data.get("list", [])
                    for song in songs:
                        song["source"] = source
                    await self.set_playlist(songs)
                    return
                else:
                    _LOGGER.warning("No songs found in playlist %s", playlist_id)
                    return
        
        # Handle playlist song - play from specific index in playlist
        if media_id.startswith("playlist_song:"):
            parts = media_id.split(":")
            if len(parts) == 4:
                source = parts[1]
                playlist_id = parts[2]
                start_index = int(parts[3])
                _LOGGER.info("TuneFree: Playing playlist %s from index %d", playlist_id, start_index)
                
                playlist_data = await self._api.get_playlist(playlist_id, source)
                if playlist_data:
                    songs = playlist_data.get("list", [])
                    for song in songs:
                        song["source"] = source
                    await self.set_playlist(songs, start_index=start_index)
                    return
                else:
                    _LOGGER.warning("No songs found in playlist %s", playlist_id)
                    return
        
        # Voice assistant search support: search:keyword or just plain text
        if media_id.startswith("search:") or (
            media_type in ("music", "audio", MediaType.MUSIC) 
            and not media_id.startswith("http") 
            and not media_id.startswith("media-source://")
            and not media_id.startswith("toplist:")
        ):
            # Extract keyword
            keyword = media_id
            if media_id.startswith("search:"):
                keyword = media_id[len("search:"):]
            
            _LOGGER.info("TuneFree: Voice search for '%s'", keyword)
            
            # Search and play first result
            songs = await self._api.search(keyword, search_type="aggregateSearch")
            if not songs:
                _LOGGER.warning("No songs found for '%s'", keyword)
                return
            
            song = songs[0]
            song_id = str(song.get("id"))
            source = song.get("platform", "netease")
            
            self._media_title = song.get("name", "未知歌曲")
            self._media_artist = song.get("artist", "")
            self._media_image_url = song.get("pic")
            if not self._media_image_url:
                self._media_image_url = f"{self._api._api_url}/api/?source={source}&id={song_id}&type=pic"
            
            # Get playback URL
            url_endpoint = self._api.get_song_url_endpoint(song_id, source=source)
            final_url = await self._api.resolve_song_redirect(url_endpoint)
            
            if not final_url:
                _LOGGER.error("Could not resolve URL for song %s", song_id)
                return
            
            self._media_content_id = f"media-source://tunefree/{source}:{song_id}"
            
            # Forward to target player with metadata
            extra = {
                "title": self._media_title,
                "artist": self._media_artist,
                "thumb": self._media_image_url,
                "entity_picture": self._media_image_url,
            }
            
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": self._target_player,
                    "media_content_id": final_url,
                    "media_content_type": "music",
                    "extra": extra,
                },
            )
            self.async_write_ha_state()
            return
        
        # Check if this is a TuneFree media source URI
        # Format: media-source://tunefree/source:song_id
        if media_id.startswith("media-source://tunefree/"):
            identifier = media_id.replace("media-source://tunefree/", "")
            parts = identifier.split(":", 1)
            source = "netease"
            song_id = identifier
            if len(parts) == 2 and parts[0] in ["netease", "kuwo", "qq"]:
                source = parts[0]
                song_id = parts[1]
            
            # Get song info for metadata
            song_info = await self._api.get_song_info(song_id, source=source)
            if song_info:
                self._media_title = song_info.get("name", "Unknown")
                self._media_artist = song_info.get("artist", "")
                self._media_image_url = song_info.get("pic")
                if not self._media_image_url:
                    self._media_image_url = f"{self._api._api_url}/api/?source={source}&id={song_id}&type=pic"
            
            # Get playback URL
            url_endpoint = self._api.get_song_url_endpoint(song_id, source=source)
            final_url = await self._api.resolve_song_redirect(url_endpoint)
            
            if not final_url:
                _LOGGER.error("Could not resolve URL for song %s", song_id)
                return
            
            self._media_content_id = media_id
            
            # Build extra metadata for players that support it (like Browser Mod)
            extra = {
                "title": self._media_title or "Unknown",
                "artist": self._media_artist or "",
                "thumb": self._media_image_url,
                "entity_picture": self._media_image_url,
            }
            
            # Forward to target player with metadata
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": self._target_player,
                    "media_content_id": final_url,
                    "media_content_type": "music",
                    "extra": extra,
                },
            )
        else:
            # Direct URL or other format - just forward
            self._media_content_id = media_id
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": self._target_player,
                    "media_content_id": media_id,
                    "media_content_type": media_type,
                },
            )
        
        self.async_write_ha_state()

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.hass.services.async_call(
            "media_player", "media_play", {"entity_id": self._target_player}
        )

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.hass.services.async_call(
            "media_player", "media_pause", {"entity_id": self._target_player}
        )

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self.hass.services.async_call(
            "media_player", "media_stop", {"entity_id": self._target_player}
        )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        await self.hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": self._target_player, "volume_level": volume},
        )

    async def async_volume_up(self) -> None:
        """Turn volume up."""
        await self.hass.services.async_call(
            "media_player", "volume_up", {"entity_id": self._target_player}
        )

    async def async_volume_down(self) -> None:
        """Turn volume down."""
        await self.hass.services.async_call(
            "media_player", "volume_down", {"entity_id": self._target_player}
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the player."""
        await self.hass.services.async_call(
            "media_player",
            "volume_mute",
            {"entity_id": self._target_player, "is_volume_muted": mute},
        )

    async def async_media_next_track(self) -> None:
        """Play next track in playlist."""
        if self._playlist and self._playlist_index < len(self._playlist) - 1:
            self._playlist_index += 1
            await self._play_current_track()
        else:
            # Fallback to target player if no playlist
            await self.hass.services.async_call(
                "media_player", "media_next_track", {"entity_id": self._target_player}
            )

    async def async_media_previous_track(self) -> None:
        """Play previous track in playlist."""
        if self._playlist and self._playlist_index > 0:
            self._playlist_index -= 1
            await self._play_current_track()
        else:
            # Fallback to target player if no playlist
            await self.hass.services.async_call(
                "media_player", "media_previous_track", {"entity_id": self._target_player}
            )

    async def async_media_seek(self, position: float) -> None:
        """Seek to a position."""
        await self.hass.services.async_call(
            "media_player",
            "media_seek",
            {"entity_id": self._target_player, "seek_position": position},
        )

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode."""
        import random
        self._shuffle = shuffle
        if shuffle and self._playlist:
            # Shuffle the playlist but keep current song
            current_song = self._playlist[self._playlist_index] if self._playlist_index < len(self._playlist) else None
            random.shuffle(self._playlist)
            if current_song:
                # Move current song to current index
                try:
                    idx = self._playlist.index(current_song)
                    self._playlist[idx], self._playlist[self._playlist_index] = self._playlist[self._playlist_index], self._playlist[idx]
                except ValueError:
                    pass
        self.async_write_ha_state()

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode."""
        self._repeat = repeat
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on the player."""
        await self.hass.services.async_call(
            "media_player", "turn_on", {"entity_id": self._target_player}
        )

    async def async_turn_off(self) -> None:
        """Turn off the player."""
        await self.hass.services.async_call(
            "media_player", "turn_off", {"entity_id": self._target_player}
        )

    @property
    def is_volume_muted(self) -> bool | None:
        """Return true if volume is muted."""
        target_state = self.hass.states.get(self._target_player)
        if target_state:
            return target_state.attributes.get("is_volume_muted")
        return None

    @property
    def media_position(self) -> float | None:
        """Return the current playback position."""
        target_state = self.hass.states.get(self._target_player)
        if target_state:
            return target_state.attributes.get("media_position")
        return None

    @property
    def media_position_updated_at(self):
        """When was the position last updated."""
        target_state = self.hass.states.get(self._target_player)
        if target_state:
            return target_state.attributes.get("media_position_updated_at")
        return None

    @property
    def media_duration(self) -> float | None:
        """Return the duration of current playing media."""
        target_state = self.hass.states.get(self._target_player)
        if target_state:
            return target_state.attributes.get("media_duration")
        return None

    @property
    def shuffle(self) -> bool | None:
        """Return true if shuffle is enabled."""
        return self._shuffle

    @property
    def repeat(self) -> str | None:
        """Return the repeat mode."""
        return self._repeat

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Implement media browsing for TuneFree."""
        # Source name mapping
        source_names = {
            "netease": "网易云音乐",
            "kuwo": "酷我音乐",
            "qq": "QQ音乐",
        }
        
        # Helper to load saved playlists
        async def load_saved_playlists():
            from homeassistant.helpers.storage import Store
            from .const import STORAGE_KEY, STORAGE_VERSION
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)
            data = await store.async_load()
            return data.get("playlists", []) if data else []
        
        # Root level - show TuneFree sources
        if media_content_id is None or media_content_id == "":
            saved_playlists = await load_saved_playlists()
            children = [
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id="toplists",
                    media_content_type="",
                    title="🔥 热门榜单",
                    can_play=False,
                    can_expand=True,
                ),
            ]
            
            # Add saved playlists folder if any exist
            if saved_playlists:
                children.append(
                    BrowseMedia(
                        media_class=MediaClass.DIRECTORY,
                        media_content_id="my_playlists",
                        media_content_type="",
                        title=f"📋 我的歌单 ({len(saved_playlists)})",
                        can_play=False,
                        can_expand=True,
                    )
                )
            
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id="",
                media_content_type="",
                title="TuneFree 音乐",
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.DIRECTORY,
                children=children,
            )
        
        # My playlists - show saved playlists
        if media_content_id == "my_playlists":
            saved_playlists = await load_saved_playlists()
            children = [
                BrowseMedia(
                    media_class=MediaClass.PLAYLIST,
                    media_content_id=f"playlist:{p['source']}:{p['id']}",
                    media_content_type="music",
                    title=f"{p['name']} ({p['count']}首)",
                    can_play=True,
                    can_expand=True,
                )
                for p in saved_playlists
            ]
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id="my_playlists",
                media_content_type="",
                title="我的歌单",
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.PLAYLIST,
                children=children,
            )
        
        # Top lists sources selection
        if media_content_id == "toplists":
            sources = [
                ("netease", "网易云音乐"),
                ("kuwo", "酷我音乐"),
                ("qq", "QQ音乐"),
            ]
            children = [
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=f"toplists:{source_id}",
                    media_content_type="",
                    title=source_name,
                    can_play=False,
                    can_expand=True,
                )
                for source_id, source_name in sources
            ]
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id="toplists",
                media_content_type="",
                title="选择音乐平台",
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.DIRECTORY,
                children=children,
            )
        
        # Top lists for a specific source
        if media_content_id.startswith("toplists:"):
            source = media_content_id.split(":")[1]
            lists = await self._api.get_toplists(source)
            children = [
                BrowseMedia(
                    media_class=MediaClass.PLAYLIST,
                    media_content_id=f"toplist:{source}:{item.get('id')}",
                    media_content_type="music",
                    title=item.get("name", "未知榜单"),
                    can_play=True,  # Can play entire toplist as queue
                    can_expand=True,  # Can also expand to see songs
                )
                for item in lists
            ]
            source_name = source_names.get(source, source)
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=media_content_id,
                media_content_type="",
                title=f"{source_name} 榜单",
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.PLAYLIST,
                children=children,
            )
        
        # Songs in a top list
        if media_content_id.startswith("toplist:"):
            parts = media_content_id.split(":")
            if len(parts) == 3:
                source = parts[1]
                list_id = parts[2]
                songs = await self._api.get_toplist_songs(list_id, source)
                children = [
                    BrowseMedia(
                        media_class=MediaClass.MUSIC,
                        # Include toplist context: toplist_song:source:list_id:index
                        media_content_id=f"toplist_song:{source}:{list_id}:{idx}",
                        media_content_type="audio/mpeg",
                        title=f"{song.get('name', '未知歌曲')} - {song.get('artist', '')}",
                        can_play=True,
                        can_expand=False,
                        thumbnail=song.get("pic"),
                    )
                    for idx, song in enumerate(songs)
                ]
                return BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=media_content_id,
                    media_content_type="",
                    title="歌曲列表",
                    can_play=False,
                    can_expand=True,
                    children_media_class=MediaClass.MUSIC,
                    children=children,
                )
        
        # Songs in a playlist
        if media_content_id.startswith("playlist:") and not media_content_id.startswith("playlist_song:"):
            parts = media_content_id.split(":")
            if len(parts) == 3:
                source = parts[1]
                playlist_id = parts[2]
                playlist_data = await self._api.get_playlist(playlist_id, source)
                if playlist_data:
                    songs = playlist_data.get("list", [])
                    info = playlist_data.get("info", {})
                    playlist_name = info.get("name") or playlist_data.get("name") or "歌单"
                    children = [
                        BrowseMedia(
                            media_class=MediaClass.MUSIC,
                            media_content_id=f"playlist_song:{source}:{playlist_id}:{idx}",
                            media_content_type="audio/mpeg",
                            title=f"{song.get('name', '未知歌曲')} - {song.get('artist', '')}",
                            can_play=True,
                            can_expand=False,
                            thumbnail=song.get("pic"),
                        )
                        for idx, song in enumerate(songs)
                    ]
                    return BrowseMedia(
                        media_class=MediaClass.PLAYLIST,
                        media_content_id=media_content_id,
                        media_content_type="music",
                        title=playlist_name,
                        can_play=True,
                        can_expand=True,
                        children_media_class=MediaClass.MUSIC,
                        children=children,
                    )
        
        # Default fallback
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id="",
            media_content_type="",
            title="TuneFree 音乐",
            can_play=False,
            can_expand=True,
            children=[],
        )
