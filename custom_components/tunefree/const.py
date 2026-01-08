"""Constants for the TuneFree integration."""

DOMAIN = "tunefree"
CONF_API_URL = "api_url"
CONF_TARGET_PLAYER = "target_player"
CONF_DEFAULT_SOURCE = "default_source"
CONF_PLAYLISTS = "playlists"
CONF_IS_XIAOAI_SPEAKER = "is_xiaoai_speaker"
DEFAULT_API_URL = "https://music-dl.sayqz.com"
DEFAULT_SOURCE = "netease"
STORAGE_KEY = f"{DOMAIN}_playlists"
STORAGE_VERSION = 1

# Available music sources
SOURCES = {
    "netease": "网易云音乐",
    "kuwo": "酷我音乐",
    "qq": "QQ音乐",
    "all": "全平台搜索",
}

# Sources for playlist import (without 'all')
PLAYLIST_SOURCES = {
    "netease": "网易云音乐",
    "kuwo": "酷我音乐",
    "qq": "QQ音乐",
}
