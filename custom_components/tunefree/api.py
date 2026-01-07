"""API Client for TuneFree."""
import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any

_LOGGER = logging.getLogger(__name__)

class TuneFreeAPI:
    """TuneFree API Client."""

    def __init__(self, session: aiohttp.ClientSession, api_url: str = "https://music-dl.sayqz.com") -> None:
        """Initialize the API client."""
        self._session = session
        self._api_url = api_url.rstrip("/")

    async def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None, retries: int = 2) -> Any:
        """Make an API request with retry."""
        url = f"{self._api_url}/{endpoint}"
        timeout = aiohttp.ClientTimeout(total=15, connect=10)
        last_error: Optional[Exception] = None
        
        for attempt in range(retries + 1):
            try:
                async with self._session.get(url, params=params, timeout=timeout) as response:
                    response.raise_for_status()
                    return await response.json()
            except asyncio.TimeoutError as err:
                _LOGGER.warning("Timeout connecting to TuneFree API at %s (attempt %d/%d)", url, attempt + 1, retries + 1)
                last_error = err
            except aiohttp.ServerDisconnectedError as err:
                _LOGGER.warning("Server disconnected from TuneFree API at %s (attempt %d/%d)", url, attempt + 1, retries + 1)
                last_error = err
                await asyncio.sleep(0.5)  # Brief delay before retry
            except aiohttp.ClientError as err:
                _LOGGER.error("Error connecting to TuneFree API: %s", err)
                raise
        
        _LOGGER.error("Failed to connect to TuneFree API after %d attempts: %s", retries + 1, last_error)
        raise last_error

    async def get_health(self) -> bool:
        """Check API health."""
        try:
            data = await self._request("health")
            # API returns { "data": { "status": "healthy" } }
            if isinstance(data, dict):
                return data.get("data", {}).get("status") == "healthy"
            return False
        except Exception:
            return False

    async def get_stats(self, period: str = "today") -> Dict[str, Any]:
        """Get API usage stats."""
        try:
            # Endpoint: /stats?period=[today|week|month]&groupBy=[platform]
            return await self._request("stats", {"period": period})
        except Exception as e:
            _LOGGER.error("Failed to fetch stats: %s", e)
            return {}

    async def get_toplists(self, source: str = "netease") -> List[Dict[str, Any]]:
        """Get top lists from a source."""
        try:
            # Endpoint: /api/?source={source}&type=toplists
            data = await self._request("api/", {"source": source, "type": "toplists"})
            if data and data.get("code") == 200:
                return data.get("data", {}).get("list", [])
            return []
        except Exception as e:
            _LOGGER.error("Failed to fetch toplists for %s: %s", source, e)
            return []

    async def get_toplist_songs(self, list_id: str, source: str = "netease") -> List[Dict[str, Any]]:
        """Get songs from a top list."""
        try:
            # Endpoint: /api/?source={source}&id={id}&type=toplist
            data = await self._request("api/", {"source": source, "id": list_id, "type": "toplist"})
            if data and data.get("code") == 200:
                result = data.get("data", {})
                # Normalize song structure if needed
                return result.get("list", [])
            return []
        except Exception as e:
            _LOGGER.error("Failed to fetch songs for list %s: %s", list_id, e)
            return []

    async def search(self, keywords: str, source: str = "netease", search_type: str = "search") -> List[Dict[str, Any]]:
        """Search for music.
        
        Args:
            keywords: The search term.
            source: The music source (netease, kwuo, qq).
            search_type: 'search' or 'aggregateSearch'.
        """
        try:
            params = {"keyword": keywords}
            if search_type == "aggregateSearch":
                params["type"] = "aggregateSearch"
            else:
                params["type"] = "search"
                params["source"] = source

            data = await self._request("api/", params)
            
            if data and data.get("code") == 200:
                result_data = data.get("data", {})
                # For aggregateSearch, 'results' is direct list in data['data']['results']?
                # The doc said: { "data": { "keyword": "...", "results": [...] } }
                return result_data.get("results", [])
            return []
        except Exception as e:
            _LOGGER.error("Failed to search TuneFree: %s", e)
            return []

    async def get_song_info(self, song_id: str, source: str = "netease") -> Optional[Dict[str, Any]]:
        """Get song details including album art."""
        try:
            # Endpoint: /api/?source={source}&id={id}&type=info
            data = await self._request("api/", {"source": source, "id": song_id, "type": "info"})
            if data and data.get("code") == 200:
                return data.get("data")
            return None
        except Exception as e:
            _LOGGER.error("Failed to get info for song %s: %s", song_id, e)
            return None

    async def get_playlist(self, playlist_id: str, source: str = "netease") -> Optional[Dict[str, Any]]:
        """Get playlist info and songs."""
        try:
            # Endpoint: /api/?source={source}&id={id}&type=playlist
            data = await self._request("api/", {"source": source, "id": playlist_id, "type": "playlist"})
            if data and data.get("code") == 200:
                return data.get("data", {})
            return None
        except Exception as e:
            _LOGGER.error("Failed to get playlist %s: %s", playlist_id, e)
            return None

    async def resolve_song_redirect(self, song_url_endpoint: str) -> Optional[str]:
        """Resolve the final URL from the redirecting endpoint."""
        try:
            async with self._session.get(song_url_endpoint, allow_redirects=False, timeout=10) as response:
                if response.status in (301, 302, 303, 307, 308):
                    return response.headers.get("Location")
                if response.status == 200:
                    # Maybe it's not a redirect but the direct file?
                    return str(response.url)
                return None
        except Exception as e:
            _LOGGER.error("Failed to resolve redirect for %s: %s", song_url_endpoint, e)
            return None

    def get_song_url_endpoint(self, song_id: str, source: str = "netease", br: str = "320k") -> str:
        """Construct the URL endpoint for a song."""
        # This is just the API endpoint string, not the resolved media file
        return f"{self._api_url}/api/?source={source}&id={song_id}&type=url&br={br}"

    async def get_lyrics(self, song_id: str, source: str = "netease") -> Optional[str]:
        """Get lyrics for a song. Returns raw LRC text."""
        try:
            # Endpoint returns plain text LRC, not JSON
            url = f"{self._api_url}/api/"
            params = {"source": source, "id": song_id, "type": "lrc"}
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with self._session.get(url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    # Return raw text content
                    return await response.text()
                return None
        except Exception as e:
            _LOGGER.error("Failed to get lyrics for song %s: %s", song_id, e)
            return None

