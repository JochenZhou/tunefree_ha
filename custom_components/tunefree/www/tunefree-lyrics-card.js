/**
 * TuneFree Lyrics Card - Pro Edition with Playback Controls
 * A beautiful, performant lyrics display card for Home Assistant
 */
class TuneFreeLyricsCard extends HTMLElement {
  static get properties() {
    return { hass: {}, _config: {} };
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config && this._initialized) {
      this._update();
    }
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }
    this._config = config;
    this._initialized = false;
    this._initElements();
  }

  getCardSize() {
    return this._config.card_height ? Math.ceil(this._config.card_height / 50) : 6;
  }

  _initElements() {
    if (this._initialized) return;

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    const height = this._config.card_height || 400;
    const showControls = this._config.show_controls !== false;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          --lyric-active-color: #fff;
          --lyric-inactive-color: rgba(255,255,255,0.5);
        }
        ha-card {
          height: ${height}px;
          overflow: hidden;
          position: relative;
          background: var(--ha-card-background, #1a1a2e);
        }
        .bg {
          position: absolute;
          inset: 0;
          background-size: cover;
          background-position: center;
          filter: blur(25px) brightness(0.5) saturate(1.2);
          transform: scale(1.1);
          transition: background-image 0.6s ease;
        }
        .overlay {
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.6) 100%);
        }
        .container {
          position: relative;
          height: 100%;
          display: flex;
          flex-direction: column;
        }
        .header {
          display: none;
          padding: 12px 16px;
          background: rgba(0,0,0,0.2);
          backdrop-filter: blur(10px);
          border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 12px 16px;
          background: rgba(0,0,0,0.2);
          backdrop-filter: blur(10px);
          border-top: 1px solid rgba(255,255,255,0.1);
        }
        .song-info {
          display: flex;
          align-items: center;
          gap: 12px;
          flex: 1;
          min-width: 0;
        }
        .cover {
          width: 40px;
          height: 40px;
          border-radius: 6px;
          background: #333;
          background-size: cover;
          box-shadow: 0 2px 8px rgba(0,0,0,0.4);
          flex-shrink: 0;
        }
        .meta {
          flex: 1;
          min-width: 0;
          color: #fff;
        }
        .title {
          font-size: 13px;
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .artist {
          font-size: 11px;
          opacity: 0.7;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .lyrics-wrap {
          flex: 1;
          overflow: hidden;
          position: relative;
        }
        .lyrics-mask {
          position: absolute;
          inset: 0;
          pointer-events: none;
          background: linear-gradient(
            to bottom,
            rgba(0,0,0,0.8) 0%,
            transparent 15%,
            transparent 85%,
            rgba(0,0,0,0.8) 100%
          );
          z-index: 1;
        }
        .lyrics {
          position: relative;
          height: 100%;
          overflow-y: auto;
          scroll-behavior: smooth;
          padding: 20px 16px;
          scrollbar-width: none;
        }
        .lyrics::-webkit-scrollbar { display: none; }
        .spacer { height: 40%; }
        .line {
          text-align: center;
          padding: 8px 12px;
          color: var(--lyric-inactive-color);
          font-size: 15px;
          line-height: 1.5;
          transition: all 0.25s ease-out;
          will-change: transform, opacity;
        }
        .line.active {
          color: var(--lyric-active-color);
          font-size: 17px;
          font-weight: 600;
          transform: scale(1.02);
          text-shadow: 0 1px 3px rgba(0,0,0,0.5);
        }
        .empty {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: rgba(255,255,255,0.4);
          font-style: italic;
        }
        .controls {
          display: ${showControls ? 'flex' : 'none'};
          align-items: center;
          gap: 8px;
        }
        .control-btn {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: rgba(255,255,255,0.1);
          border: 1px solid rgba(255,255,255,0.2);
          color: #fff;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
          flex-shrink: 0;
        }
        .control-btn:hover {
          background: rgba(255,255,255,0.2);
          transform: scale(1.05);
        }
        .control-btn:active {
          transform: scale(0.95);
        }
        .control-btn svg {
          width: 20px;
          height: 20px;
          fill: currentColor;
        }
        @media (max-aspect-ratio: 1/1) {
          .header { display: block; }
          .footer .song-info { display: none; }
          .footer { justify-content: center; }
        }
      </style>
      <ha-card>
        <div class="bg" id="bg"></div>
        <div class="overlay"></div>
        <div class="container">
          <div class="header">
            <div class="song-info">
              <div class="cover" id="cover2"></div>
              <div class="meta">
                <div class="title" id="title2"></div>
                <div class="artist" id="artist2"></div>
              </div>
            </div>
          </div>
          <div class="lyrics-wrap">
            <div class="lyrics-mask"></div>
            <div class="lyrics" id="lyrics"></div>
          </div>
          <div class="footer">
            <div class="song-info">
              <div class="cover" id="cover"></div>
              <div class="meta">
                <div class="title" id="title">未播放</div>
                <div class="artist" id="artist"></div>
              </div>
            </div>
            <div class="controls">
            <button class="control-btn" id="prev" title="上一曲">
              <svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
            </button>
            <button class="control-btn" id="playPause" title="播放/暂停">
              <svg id="playIcon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              <svg id="pauseIcon" viewBox="0 0 24 24" style="display:none"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
            </button>
            <button class="control-btn" id="next" title="下一曲">
              <svg viewBox="0 0 24 24"><path d="M5.5 18V6l8.5 6zm10.5-12h2v12h-2z"/></svg>
            </button>
            <button class="control-btn" id="browse" title="浏览媒体">
              <svg viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
            </button>
          </div>
        </div>
      </ha-card>
    `;

    // Cache DOM refs
    this._bg = this.shadowRoot.getElementById("bg");
    this._cover = this.shadowRoot.getElementById("cover");
    this._title = this.shadowRoot.getElementById("title");
    this._artist = this.shadowRoot.getElementById("artist");
    this._cover2 = this.shadowRoot.getElementById("cover2");
    this._title2 = this.shadowRoot.getElementById("title2");
    this._artist2 = this.shadowRoot.getElementById("artist2");
    this._lyrics = this.shadowRoot.getElementById("lyrics");
    this._playIcon = this.shadowRoot.getElementById("playIcon");
    this._pauseIcon = this.shadowRoot.getElementById("pauseIcon");

    // Bind control events
    if (showControls) {
      this.shadowRoot.getElementById("prev").onclick = () => this._callService("media_previous_track");
      this.shadowRoot.getElementById("playPause").onclick = () => this._togglePlayPause();
      this.shadowRoot.getElementById("next").onclick = () => this._callService("media_next_track");
      this.shadowRoot.getElementById("browse").onclick = () => this._openBrowser();
    }

    // State
    this._lastCover = null;
    this._lastLyrics = null;
    this._lastState = null;
    this._lastTitle = null;
    this._lyricsData = [];
    this._activeIdx = -1;
    this._lineEls = [];
    this._animId = null;

    this._initialized = true;
    this._startLoop();
  }

  _callService(service) {
    if (!this._hass || !this._config) return;
    this._hass.callService("media_player", service, {
      entity_id: this._config.entity
    });
  }

  _togglePlayPause() {
    if (!this._hass || !this._config) return;
    const entity = this._hass.states[this._config.entity];
    if (!entity) return;

    const service = entity.state === "playing" ? "media_pause" : "media_play";
    this._callService(service);
  }

  _openBrowser() {
    if (!this._hass || !this._config) return;
    // Open more-info dialog which includes media browser
    const event = new Event("hass-more-info", {
      bubbles: true,
      composed: true,
    });
    event.detail = { entityId: this._config.entity };
    this.dispatchEvent(event);
  }

  _startLoop() {
    let lastUpdate = 0;
    const loop = (ts) => {
      if (ts - lastUpdate > 300) {
        this._syncLyrics();
        lastUpdate = ts;
      }
      this._animId = requestAnimationFrame(loop);
    };
    this._animId = requestAnimationFrame(loop);
  }

  disconnectedCallback() {
    if (this._animId) {
      cancelAnimationFrame(this._animId);
      this._animId = null;
    }
  }

  connectedCallback() {
    if (this._initialized && !this._animId) {
      this._startLoop();
      this._syncLyrics();
    }
  }

  _parseLRC(lrc) {
    if (!lrc || typeof lrc !== 'string') return [];
    const lines = lrc.split(/\r?\n/);
    const result = [];
    const timeReg = /\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]/g;

    for (const line of lines) {
      const times = [];
      let match;
      while ((match = timeReg.exec(line)) !== null) {
        const min = parseInt(match[1], 10);
        const sec = parseInt(match[2], 10);
        const ms = match[3] ? parseInt(match[3].padEnd(3, '0').slice(0, 3), 10) : 0;
        times.push(min * 60 + sec + ms / 1000);
      }
      const text = line.replace(/\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]/g, '').trim();
      if (text && times.length) {
        times.forEach(t => result.push({ time: t, text }));
      }
    }
    return result.sort((a, b) => a.time - b.time);
  }

  _update() {
    if (!this._hass || !this._config) return;
    const entity = this._hass.states[this._config.entity];
    if (!entity) return;

    const attrs = entity.attributes;
    const cover = attrs.entity_picture || "";
    const title = attrs.media_title || "未播放";
    const artist = attrs.media_artist || "";
    const lyrics = attrs.lyrics || "";
    const state = entity.state;

    // Update play/pause icon
    if (state !== this._lastState && this._playIcon && this._pauseIcon) {
      if (state === "playing") {
        this._playIcon.style.display = "none";
        this._pauseIcon.style.display = "block";
      } else {
        this._playIcon.style.display = "block";
        this._pauseIcon.style.display = "none";
      }
      this._lastState = state;
    }

    // Update cover/bg only on change
    if (cover !== this._lastCover) {
      const url = cover ? `url(${cover})` : "";
      this._bg.style.backgroundImage = url;
      this._cover.style.backgroundImage = url;
      this._cover2.style.backgroundImage = url;
      this._lastCover = cover;
    }

    // Update meta
    this._title.textContent = title;
    this._artist.textContent = artist;
    this._title2.textContent = title;
    this._artist2.textContent = artist;

    // Detect song change by title
    const songChanged = title !== this._lastTitle;
    if (songChanged) {
      this._lastTitle = title;
    }

    // Update lyrics only on change
    if (lyrics !== this._lastLyrics) {
      this._lyricsData = this._parseLRC(lyrics);
      this._renderLyrics();
      this._lastLyrics = lyrics;
      this._activeIdx = -1;
    }

    // On song change, always reset to first line
    if (songChanged && this._lyricsData.length && this._lineEls.length) {
      this._setActive(0);
    }
  }

  _renderLyrics() {
    const container = this._lyrics;
    container.innerHTML = "";
    this._lineEls = [];

    if (!this._lyricsData.length) {
      container.innerHTML = '<div class="empty">暂无歌词或纯音乐</div>';
      return;
    }

    const topSpacer = document.createElement("div");
    topSpacer.className = "spacer";
    container.appendChild(topSpacer);

    this._lyricsData.forEach((item, i) => {
      const div = document.createElement("div");
      div.className = "line";
      div.textContent = item.text;
      container.appendChild(div);
      this._lineEls.push(div);
    });

    const bottomSpacer = document.createElement("div");
    bottomSpacer.className = "spacer";
    container.appendChild(bottomSpacer);
  }

  _syncLyrics() {
    if (!this._hass || !this._config || !this._lyricsData.length) return;

    const entity = this._hass.states[this._config.entity];
    if (!entity || entity.state !== "playing") return;

    const pos = entity.attributes.media_position;
    const updatedAt = entity.attributes.media_position_updated_at;
    if (pos === undefined || !updatedAt) return;

    const elapsed = (Date.now() - new Date(updatedAt).getTime()) / 1000;
    const currentTime = pos + elapsed;

    let activeIdx = -1;
    let lo = 0, hi = this._lyricsData.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (this._lyricsData[mid].time <= currentTime) {
        activeIdx = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }

    if (activeIdx !== this._activeIdx && activeIdx >= 0) {
      this._setActive(activeIdx);
    }
  }

  _setActive(idx) {
    // Remove old active
    if (this._activeIdx >= 0 && this._lineEls[this._activeIdx]) {
      this._lineEls[this._activeIdx].classList.remove("active");
    }

    // Set new active
    if (idx >= 0 && this._lineEls[idx]) {
      const line = this._lineEls[idx];
      line.classList.add("active");

      // Scroll within container only (not affecting page scroll)
      const container = this._lyrics;
      const scrollTo = line.offsetTop - container.clientHeight / 2 + line.clientHeight / 2;
      container.scrollTop = scrollTo;
    }
    this._activeIdx = idx;
  }

  static getConfigElement() {
    return document.createElement("tunefree-lyrics-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "media_player.tunefree_service_tunefree_player",
      show_controls: true,
      card_height: 400
    };
  }
}

customElements.define("tunefree-lyrics-card", TuneFreeLyricsCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "tunefree-lyrics-card",
  name: "TuneFree 歌词卡片",
  description: "显示歌词并同步滚动，支持播放控制",
  preview: true,
});
