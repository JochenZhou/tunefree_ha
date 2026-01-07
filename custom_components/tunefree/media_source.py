"""Media Source for TuneFree."""
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .api import TuneFreeAPI

_LOGGER = logging.getLogger(__name__)

# Chinese labels for sources
SOURCE_NAMES = {
    "netease": "网易云音乐",
    "kuwo": "酷我音乐",
    "qq": "QQ音乐",
}

async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """Set up TuneFree media source."""
    entry_data = next(iter(hass.data.get(DOMAIN, {}).values()), None)
    if not entry_data:
        return TuneFreeMediaSource(hass, None)
    return TuneFreeMediaSource(hass, entry_data["api"])

class TuneFreeMediaSource(MediaSource):
    """Provide TuneFree media source."""

    name: str = "TuneFree"

    def __init__(self, hass: HomeAssistant, api: TuneFreeAPI | None) -> None:
        """Initialize TuneFree source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self.api = api

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        if not self.api:
             raise Unresolvable("TuneFree integration not loaded")

        song_id = item.identifier
        parts = song_id.split(":", 1)
        source = "netease"
        real_id = song_id
        if len(parts) == 2 and parts[0] in ["netease", "kuwo", "qq"]:
            source = parts[0]
            real_id = parts[1]

        url_endpoint = self.api.get_song_url_endpoint(real_id, source=source)
        final_url = await self.api.resolve_song_redirect(url_endpoint)
        
        if not final_url:
            raise Unresolvable(f"Could not resolve URL for song ID {song_id}")

        return PlayMedia(final_url, "audio/mpeg")

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Browse media."""
        if not self.api:
             raise MediaSourceError("TuneFree integration not loaded")

        media_content_id = item.identifier

        if not media_content_id:
            return self._build_root_source()

        if media_content_id == "toplists":
            return self._build_toplists_sources()
            
        if media_content_id.startswith("toplists:"):
            source = media_content_id.split(":")[1]
            return await self._build_toplists_for_source(source)

        if media_content_id.startswith("toplist:"):
            parts = media_content_id.split(":")
            if len(parts) == 3:
                return await self._build_toplist_songs(parts[1], parts[2])

        if media_content_id.startswith("playlist:"):
            parts = media_content_id.split(":")
            if len(parts) == 3:
                return await self._build_playlist_songs(parts[1], parts[2])

        if media_content_id.startswith("search:"):
            query = media_content_id[len("search:"):]
            return await self._build_search_result(query)

        raise MediaSourceError(f"Unknown media content id: {media_content_id}")

    def _build_root_source(self) -> BrowseMediaSource:
        """Build the root browse source."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="TuneFree 音乐",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier="toplists",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title="🔥 热门榜单",
                    can_play=False,
                    can_expand=True,
                )
            ],
        )

    def _build_toplists_sources(self) -> BrowseMediaSource:
        """Build the sources for top lists."""
        sources = [
            ("netease", "网易云音乐"),
            ("kuwo", "酷我音乐"),
            ("qq", "QQ音乐"),
        ]
        children = []
        for source_id, source_name in sources:
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"toplists:{source_id}",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title=source_name,
                    can_play=False,
                    can_expand=True,
                )
            )
        
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="toplists",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="选择音乐平台",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.DIRECTORY,
        )

    async def _build_toplists_for_source(self, source: str) -> BrowseMediaSource:
        """Build top lists for a specific source."""
        lists = await self.api.get_toplists(source)
        children = []
        for item in lists:
            list_id = item.get("id")
            name = item.get("name", "未知榜单")
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"toplist:{source}:{list_id}",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title=name,
                    can_play=False,
                    can_expand=True,
                )
            )
        
        source_name = SOURCE_NAMES.get(source, source)
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"toplists:{source}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=f"{source_name} 榜单",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.MUSIC,
        )

    async def _build_toplist_songs(self, source: str, list_id: str) -> BrowseMediaSource:
        """Build songs for a top list."""
        songs = await self.api.get_toplist_songs(list_id, source)
        children = []
        for song in songs:
             children.append(self._create_song_item(song, source))
             
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"toplist:{source}:{list_id}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="歌曲列表",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.MUSIC,
        )

    async def _build_playlist_songs(self, source: str, playlist_id: str) -> BrowseMediaSource:
        """Build songs for a playlist."""
        playlist_data = await self.api.get_playlist(playlist_id, source)
        if not playlist_data:
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"playlist:{source}:{playlist_id}",
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.MUSIC,
                title="播放列表",
                can_play=False,
                can_expand=True,
                children=[],
            )
        
        songs = playlist_data.get("list", [])
        children = []
        for song in songs:
             children.append(self._create_song_item(song, source))
        
        playlist_name = playlist_data.get("name", "播放列表")
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"playlist:{source}:{playlist_id}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=playlist_name,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.MUSIC,
        )

    async def _build_search_result(self, query: str) -> BrowseMediaSource:
        """Build search result source."""
        songs = await self.api.search(query, search_type="aggregateSearch")
        
        children = []
        for song in songs:
            source = song.get("platform", "netease")
            children.append(self._create_song_item(song, source))

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"search:{query}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=f"搜索: {query}",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.MUSIC,
        )

    def _create_song_item(self, song: dict, source: str) -> BrowseMediaSource:
        """Helper to create a song item."""
        song_id = str(song.get("id"))
        title = song.get("name", "未知歌曲")
        artists = song.get("artist", "")
        identifier = f"{source}:{song_id}"
        
        # Try to get thumbnail
        thumbnail = song.get("pic")
        if not thumbnail:
             album = song.get("album")
             if isinstance(album, dict):
                 thumbnail = album.get("picUrl") or album.get("pic")
        
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.MUSIC,
            media_content_type="audio/mpeg",
            title=f"{title} - {artists}",
            can_play=True,
            can_expand=False,
            thumbnail=thumbnail,
        )
