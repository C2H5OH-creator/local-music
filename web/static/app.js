let currentTrackButton = null;

function getTrackButtons() {
  return Array.from(document.querySelectorAll("[data-audio-src]"));
}

function getCurrentTrackIndex() {
  return getTrackButtons().indexOf(currentTrackButton);
}

function setMediaSessionMetadata(button) {
  if (!("mediaSession" in navigator) || !("MediaMetadata" in window)) {
    return;
  }

  const artwork = [];
  if (button.dataset.coverSrc) {
    const coverType = button.dataset.coverType || "image/jpeg";
    for (const size of [100, 200, 400]) {
      artwork.push({
        src: `${button.dataset.coverSrc}&size=${size}x${size}`,
        sizes: `${size}x${size}`,
        type: coverType,
      });
    }
  }

  navigator.mediaSession.metadata = new MediaMetadata({
    title: button.dataset.trackTitle || "",
    artist: button.dataset.trackArtists || "",
    album: button.dataset.albumTitle || "",
    artwork,
  });
}

function setMediaSessionHandlers(player) {
  if (!("mediaSession" in navigator)) {
    return;
  }

  navigator.mediaSession.setActionHandler("play", () => player.play());
  navigator.mediaSession.setActionHandler("pause", () => player.pause());
  navigator.mediaSession.setActionHandler("previoustrack", playPreviousTrack);
  navigator.mediaSession.setActionHandler("nexttrack", playNextTrack);
}

function playTrackButton(button) {
  const player = document.getElementById("album-player");
  const title = document.getElementById("player-title");
  if (!player || !button) {
    return;
  }

  currentTrackButton = button;
  player.src = button.dataset.audioSrc;
  if (title) {
    title.textContent = button.dataset.trackTitle || "Трек";
  }

  setMediaSessionMetadata(button);
  setMediaSessionHandlers(player);
  player.play();
}

function playAdjacentTrack(direction) {
  const buttons = getTrackButtons();
  if (!buttons.length) {
    return;
  }

  const currentIndex = getCurrentTrackIndex();
  const fallbackIndex = direction > 0 ? 0 : buttons.length - 1;
  const nextIndex =
    currentIndex === -1
      ? fallbackIndex
      : (currentIndex + direction + buttons.length) % buttons.length;

  playTrackButton(buttons[nextIndex]);
}

function playNextTrack() {
  playAdjacentTrack(1);
}

function playPreviousTrack() {
  playAdjacentTrack(-1);
}

document.addEventListener("click", (event) => {
  const profileToggle = event.target.closest("#profile-menu-toggle");
  if (profileToggle) {
    const submenu = document.getElementById(
      profileToggle.getAttribute("aria-controls"),
    );
    if (!submenu) {
      return;
    }

    const isOpen = profileToggle.getAttribute("aria-expanded") === "true";
    profileToggle.setAttribute("aria-expanded", String(!isOpen));
    submenu.hidden = isOpen;
    return;
  }

  const downloadButton = event.target.closest("#download-album-button");
  if (downloadButton) {
    const albumInput = document.getElementById("album-id-input");
    const albumQualitySelect = document.getElementById("album-quality-select");
    const coverQualitySelect = document.getElementById("cover-quality-select");
    const coverModeSelect = document.getElementById("cover-mode-select");
    const albumId = albumInput?.value?.trim();
    if (!albumId) {
      albumInput?.focus();
      return;
    }

    const params = new URLSearchParams({
      album_id: albumId,
      albumQuality: albumQualitySelect?.value || "normal",
      coverQuality: coverQualitySelect?.value || "400",
      coverMode: coverModeSelect?.value || "embedded",
    });
    window.location.href = `/api/yandex/albums/download/stream?${params.toString()}`;
    return;
  }

  const button = event.target.closest("[data-audio-src]");
  if (!button) {
    return;
  }

  playTrackButton(button);
});

document.addEventListener(
  "ended",
  (event) => {
    if (event.target.id === "album-player") {
      playNextTrack();
    }
  },
  true,
);
