/**
 * radiko Stream Player - Application Logic
 *
 * HLS.js を使用して radiko のライブストリームを再生するフロントエンド。
 * BACKEND_URL は env-config.js (コンテナ起動時に自動生成) から取得。
 */

(() => {
  "use strict";

  // ─── Configuration ─────────────────────────────────
  // env-config.js で window.__RADIKO_BACKEND_URL が設定される
  // 未設定時は same-origin にフォールバック
  function getBackendUrl() {
    const url = window.__RADIKO_BACKEND_URL || "";
    // 末尾スラッシュを除去
    return url.replace(/\/+$/, "");
  }

  function apiUrl(path) {
    return getBackendUrl() + path;
  }

  // ─── DOM Elements ──────────────────────────────────
  const $ = (id) => document.getElementById(id);

  const els = {
    authArea: $("auth-area"),
    connectionDot: $("connection-dot"),
    loadingState: $("loading-state"),
    errorState: $("error-state"),
    errorMessage: $("error-message"),
    retryBtn: $("retry-btn"),
    stationGrid: $("station-grid"),
    nowPlaying: $("now-playing"),
    npLogo: $("np-logo"),
    npName: $("np-name"),
    npStatus: $("np-status"),
    npPlayBtn: $("np-play-btn"),
    npIconPlay: $("np-icon-play"),
    npIconPause: $("np-icon-pause"),
    npIconLoading: $("np-icon-loading"),
    npCloseBtn: $("np-close-btn"),
    volumeSlider: $("volume-slider"),
    visualizer: $("visualizer"),
    audioPlayer: $("audio-player"),
  };

  // ─── State ─────────────────────────────────────────
  let hls = null;
  let currentStation = null;
  let isPlaying = false;
  let isLoading = false;
  let programsMap = {}; // station_id -> { title, img, performer, ... }
  let programRefreshTimer = null;

  // ─── Init ──────────────────────────────────────────
  async function init() {
    try {
      await checkAuthStatus();
      await loadStations();
      setupEventListeners();
      // 番組情報の定期更新 (60秒ごと)
      if (programRefreshTimer) clearInterval(programRefreshTimer);
      programRefreshTimer = setInterval(refreshPrograms, 60000);
    } catch (err) {
      showError(`初期化に失敗しました: ${err.message}`);
    }
  }

  // ─── Auth Status ───────────────────────────────────
  async function checkAuthStatus() {
    try {
      const resp = await fetch(apiUrl("/api/auth/status"));
      const data = await resp.json();

      if (data.authenticated) {
        els.authArea.textContent = `${data.area_id} ${data.area_name}`;
        els.connectionDot.classList.add("connected");
      } else {
        els.authArea.textContent = "未認証";
        els.connectionDot.classList.remove("connected");
      }
    } catch {
      els.authArea.textContent = "接続エラー";
      els.connectionDot.classList.remove("connected");
    }
  }

  // ─── Load Stations ─────────────────────────────────
  async function loadStations() {
    showLoading();

    try {
      // 放送局一覧と番組情報を並行取得
      const [stationsResp, programsResp] = await Promise.all([
        fetch(apiUrl("/api/stations")),
        fetch(apiUrl("/api/programs")).catch(() => null),
      ]);

      if (!stationsResp.ok) throw new Error(`HTTP ${stationsResp.status}`);

      const stationsData = await stationsResp.json();
      const stations = stationsData.stations || [];

      // 番組情報をマッピング
      if (programsResp && programsResp.ok) {
        const programsData = await programsResp.json();
        programsMap = programsData.programs || {};
      }

      if (stations.length === 0) {
        showError("放送局が見つかりませんでした");
        return;
      }

      renderStations(stations);
      showStationGrid();
    } catch (err) {
      showError(`放送局の読み込みに失敗しました: ${err.message}`);
    }
  }

  // ─── Refresh Programs ─────────────────────────────
  async function refreshPrograms() {
    try {
      const resp = await fetch(apiUrl("/api/programs"));
      if (!resp.ok) return;
      const data = await resp.json();
      programsMap = data.programs || {};
      // カード上の番組情報を更新
      updateProgramsOnCards();
      // Now Playing バーの番組情報も更新
      if (currentStation && programsMap[currentStation.id]) {
        const prog = programsMap[currentStation.id];
        const npProgram = document.getElementById("np-program");
        if (npProgram) npProgram.textContent = prog.title;
      }
    } catch {
      // 番組更新失敗は無視
    }
  }

  function updateProgramsOnCards() {
    document.querySelectorAll(".station-card").forEach((card) => {
      const stationId = card.dataset.stationId;
      const prog = programsMap[stationId];
      if (!prog) return;

      const titleEl = card.querySelector(".program-title");
      const performerEl = card.querySelector(".program-performer");
      const imgEl = card.querySelector(".program-img");
      const placeholderEl = card.querySelector(".program-img-placeholder");

      if (titleEl) titleEl.textContent = prog.title || "";
      if (performerEl) performerEl.textContent = prog.performer || "";

      if (imgEl && prog.img) {
        imgEl.src = prog.img;
        imgEl.style.display = "";
        if (placeholderEl) placeholderEl.style.display = "none";
      }
    });
  }

  // ─── Render Stations ───────────────────────────────
  function renderStations(stationList) {
    els.stationGrid.innerHTML = "";

    stationList.forEach((station) => {
      const card = document.createElement("div");
      card.className = "station-card";
      card.dataset.stationId = station.id;
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");

      const prog = programsMap[station.id] || {};
      const progTitle = prog.title || "";
      const progImg = prog.img || "";
      const progPerformer = prog.performer || "";

      card.innerHTML = `
        <div class="station-card-left">
          <div class="station-logo-wrap">
            ${
              station.logo_url
                ? `<img class="station-logo" src="${station.logo_url}" alt="${station.name}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='block'" />
                   <span class="station-logo-placeholder" style="display:none">${station.id}</span>`
                : `<span class="station-logo-placeholder">${station.id}</span>`
            }
          </div>
          <div class="station-info">
            <div class="station-name">${station.name}</div>
            <div class="program-title">${progTitle}</div>
            <div class="program-performer">${progPerformer}</div>
          </div>
        </div>
        <div class="station-card-right">
          <div class="program-img-wrap">
            ${progImg
              ? `<img class="program-img" src="${progImg}" alt="${progTitle}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />
                 <div class="program-img-placeholder" style="display:none">
                   <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" opacity="0.3"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
                 </div>`
              : `<div class="program-img-placeholder">
                   <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" opacity="0.3"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
                 </div>`
            }
          </div>
          <div class="station-eq">
            <div class="station-eq-bar"></div>
            <div class="station-eq-bar"></div>
            <div class="station-eq-bar"></div>
            <div class="station-eq-bar"></div>
          </div>
          <div class="station-play-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
          </div>
        </div>
      `;

      card.addEventListener("click", () => onStationClick(station));
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onStationClick(station);
        }
      });

      els.stationGrid.appendChild(card);
    });
  }

  // ─── Station Click Handler ─────────────────────────
  function onStationClick(station) {
    if (currentStation && currentStation.id === station.id) {
      if (isPlaying) {
        stopPlayback();
      } else {
        playStation(station);
      }
    } else {
      playStation(station);
    }
  }

  // ─── Play Station ──────────────────────────────────
  function playStation(station) {
    currentStation = station;
    setLoadingState(true);
    updateNowPlaying(station);
    updateActiveCard(station.id);
    showNowPlaying();

    if (hls) {
      hls.destroy();
      hls = null;
    }

    const streamUrl = apiUrl(`/api/stream/${station.id}`);

    if (Hls.isSupported()) {
      hls = new Hls({
        liveSyncDurationCount: 3,
        liveMaxLatencyDurationCount: 6,
        maxBufferLength: 10,
        maxMaxBufferLength: 30,
        enableWorker: true,
      });

      hls.loadSource(streamUrl);
      hls.attachMedia(els.audioPlayer);

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        els.audioPlayer
          .play()
          .then(() => {
            isPlaying = true;
            setLoadingState(false);
            updatePlayPauseIcon();
            startVisualizer();
          })
          .catch((err) => {
            console.error("再生エラー:", err);
            setLoadingState(false);
          });
      });

      hls.on(Hls.Events.ERROR, (_event, data) => {
        console.error("HLS エラー:", data);
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              stopPlayback();
              break;
          }
        }
      });
    } else if (els.audioPlayer.canPlayType("application/vnd.apple.mpegurl")) {
      els.audioPlayer.src = streamUrl;
      els.audioPlayer
        .play()
        .then(() => {
          isPlaying = true;
          setLoadingState(false);
          updatePlayPauseIcon();
          startVisualizer();
        })
        .catch((err) => {
          console.error("再生エラー:", err);
          setLoadingState(false);
        });
    } else {
      showError("お使いのブラウザは HLS 再生に対応していません");
    }
  }

  // ─── Stop Playback ─────────────────────────────────
  function stopPlayback() {
    if (hls) {
      hls.destroy();
      hls = null;
    }
    els.audioPlayer.pause();
    els.audioPlayer.removeAttribute("src");
    els.audioPlayer.load();
    isPlaying = false;
    isLoading = false;
    updatePlayPauseIcon();
    stopVisualizer();
    updateActiveCard(null);
  }

  // ─── UI Helpers ────────────────────────────────────
  function showLoading() {
    els.loadingState.classList.remove("hidden");
    els.errorState.classList.add("hidden");
    els.stationGrid.classList.add("hidden");
  }

  function showError(message) {
    els.loadingState.classList.add("hidden");
    els.errorState.classList.remove("hidden");
    els.stationGrid.classList.add("hidden");
    els.errorMessage.textContent = message;
  }

  function showStationGrid() {
    els.loadingState.classList.add("hidden");
    els.errorState.classList.add("hidden");
    els.stationGrid.classList.remove("hidden");
  }

  function setLoadingState(loading) {
    isLoading = loading;
    updatePlayPauseIcon();
  }

  function updatePlayPauseIcon() {
    els.npIconPlay.classList.toggle("hidden", isPlaying || isLoading);
    els.npIconPause.classList.toggle("hidden", !isPlaying || isLoading);
    els.npIconLoading.classList.toggle("hidden", !isLoading);
  }

  function updateNowPlaying(station) {
    els.npLogo.src = station.logo_url || "";
    els.npLogo.alt = station.name;
    els.npName.textContent = station.name;
    // 番組情報をNow Playingバーに表示
    const prog = programsMap[station.id];
    const npProgram = document.getElementById("np-program");
    if (npProgram) {
      npProgram.textContent = prog ? prog.title : "";
    }
  }

  function showNowPlaying() {
    els.nowPlaying.classList.remove("hidden");
    requestAnimationFrame(() => {
      els.nowPlaying.classList.add("visible");
    });
  }

  function hideNowPlaying() {
    els.nowPlaying.classList.remove("visible");
    setTimeout(() => {
      els.nowPlaying.classList.add("hidden");
    }, 400);
  }

  function updateActiveCard(stationId) {
    document.querySelectorAll(".station-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.stationId === stationId);
      const icon = card.querySelector(".station-play-icon svg");
      if (card.dataset.stationId === stationId && isPlaying) {
        icon.innerHTML = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
      } else {
        icon.innerHTML = '<path d="M8 5v14l11-7z"/>';
      }
    });
  }

  function startVisualizer() {
    els.visualizer.classList.add("active");
  }

  function stopVisualizer() {
    els.visualizer.classList.remove("active");
  }

  // ─── Event Listeners ──────────────────────────────
  function setupEventListeners() {
    els.npPlayBtn.addEventListener("click", () => {
      if (isLoading) return;
      if (isPlaying) stopPlayback();
      else if (currentStation) playStation(currentStation);
    });

    els.npCloseBtn.addEventListener("click", () => {
      stopPlayback();
      hideNowPlaying();
      currentStation = null;
    });

    els.volumeSlider.addEventListener("input", (e) => {
      els.audioPlayer.volume = e.target.value / 100;
    });

    els.audioPlayer.volume = els.volumeSlider.value / 100;

    els.retryBtn.addEventListener("click", () => init());

    document.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT") return;
      switch (e.key) {
        case " ":
          e.preventDefault();
          if (currentStation) {
            if (isPlaying) stopPlayback();
            else playStation(currentStation);
          }
          break;
        case "Escape":
          if (isPlaying) stopPlayback();
          break;
      }
    });
  }

  // ─── Start ─────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", init);
})();
