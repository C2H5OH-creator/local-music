from pathlib import Path
import sys
from typing import Any
from dataclasses import dataclass
import tempfile
import zipfile


_YANDEX_MUSIC_DOWNLOADER_PATH = (
    Path(__file__).resolve().parents[1] / "external_tools" / "yandex-music-downloader"
)
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "storage" / "cache"


@dataclass(frozen=True)
class CachedAudio:
    path: Path
    media_type: str


@dataclass(frozen=True)
class DownloadedArchive:
    path: Path
    filename: str


def _ensure_yandex_music_downloader_importable() -> None:
    path = str(_YANDEX_MUSIC_DOWNLOADER_PATH)
    if path not in sys.path:
        sys.path.insert(0, path)


class YandexMusicProvider:
    def __init__(
        self,
        token: str,
        timeout: int = 20,
        max_try_count: int = 20,
        retry_delay: int = 5,
    ) -> None:
        _ensure_yandex_music_downloader_importable()

        try:
            from ymd import core
        except ImportError as error:
            raise RuntimeError(
                "Cannot import yandex-music-downloader. Make sure its dependencies "
                "are installed: yandex-music, mutagen, StrEnum, pycryptodome."
            ) from error

        self.client = core.init_client(
            token=token,
            timeout=timeout,
            max_try_count=max_try_count,
            retry_delay=retry_delay,
        )

    def get_track(self, track_id: int | str) -> Any:
        tracks = self.client.tracks(track_id)
        if not tracks:
            raise ValueError(f"Yandex Music track not found: {track_id}")
        return tracks[0]

    def get_track_info(self, track_id: int | str) -> dict[str, Any]:
        track = self.get_track(track_id)
        return self._track_to_info(track)

    def get_album(self, album_id: int | str) -> Any:
        album = self.client.albums_with_tracks(album_id)
        if album is None:
            raise ValueError(f"Yandex Music album not found: {album_id}")
        return album

    def get_album_info(self, album_id: int | str) -> dict[str, Any]:
        album = self.get_album(album_id)
        tracks = [
            self._track_to_info(track)
            for volume in album.volumes or []
            for track in volume
        ]

        return {
            "id": album.id,
            "title": album.title,
            "version": album.version,
            "available": album.available,
            "year": album.year,
            "release_date": album.release_date,
            "genre": album.genre,
            "cover_uri": album.cover_uri,
            "track_count": album.track_count,
            "artists": [self._artist_to_info(artist) for artist in album.artists],
            "tracks": tracks,
        }

    def get_track_audio_preview(
        self,
        track_id: int | str,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
    ) -> CachedAudio:
        _ensure_yandex_music_downloader_importable()
        from ymd import api

        track = self.get_track(track_id)
        download_info = api.get_download_info(track, api.ApiTrackQuality.LOW)
        suffix = self._container_to_suffix(download_info.file_format.container)
        media_type = self._container_to_media_type(download_info.file_format.container)
        cache_path = cache_dir / "yandex" / "tracks" / f"{track.id}{suffix}"

        if not cache_path.is_file():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            track_data = api.download_track(self.client, download_info)
            temporary_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
            temporary_path.write_bytes(track_data)
            temporary_path.replace(cache_path)

        return CachedAudio(path=cache_path, media_type=media_type)

    def download_album_archive(
        self,
        album_id: int | str,
        quality: str,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
    ) -> DownloadedArchive:
        _ensure_yandex_music_downloader_importable()
        from ymd import core

        quality_value = self._quality_to_core_quality(quality)
        album = self.get_album(album_id)
        album_info = self.get_album_info(album_id)
        album_name = self._safe_name(album_info["title"] or f"album-{album_id}")
        archive_path = cache_dir / "yandex" / "albums" / f"{album.id}-{quality}.zip"

        if archive_path.is_file():
            return DownloadedArchive(
                path=archive_path,
                filename=f"{album_name}-{quality}.zip",
            )

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            covers_cache = {}

            for volume in album.volumes or []:
                for track in volume:
                    if not track.available:
                        continue

                    base_path = tmpdir_path / core.prepare_base_path(
                        core.DEFAULT_PATH_PATTERN,
                        track,
                    )
                    base_path.parent.mkdir(parents=True, exist_ok=True)
                    downloadable = core.to_downloadable_track(
                        track,
                        quality_value,
                        base_path,
                    )
                    core.download_track(
                        track_info=downloadable,
                        cover_resolution=-1,
                        embed_cover=True,
                        covers_cache=covers_cache,
                    )

            temporary_archive_path = archive_path.with_suffix(".zip.tmp")
            with zipfile.ZipFile(
                temporary_archive_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for file_path in sorted(tmpdir_path.rglob("*")):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(tmpdir_path))

            temporary_archive_path.replace(archive_path)

        return DownloadedArchive(
            path=archive_path,
            filename=f"{album_name}-{quality}.zip",
        )

    def _track_to_info(self, track: Any) -> dict[str, Any]:
        album = track.albums[0] if track.albums else None
        position = album.track_position if album else None
        full_title = track.title
        if track.version:
            full_title = f"{track.title} ({track.version})"

        return {
            "id": track.id,
            "title": track.title,
            "version": track.version,
            "full_title": full_title,
            "available": track.available,
            "duration_ms": track.duration_ms,
            "track_number": position.index if position else None,
            "disc_number": position.volume if position else None,
            "artists": [self._artist_to_info(artist) for artist in track.artists],
            "album": None
            if album is None
            else {
                "id": album.id,
                "title": album.title,
                "year": album.year,
                "track_count": album.track_count,
            },
            "cover_uri": track.cover_uri,
        }

    @staticmethod
    def _artist_to_info(artist: Any) -> dict[str, Any]:
        return {
            "id": artist.id,
            "name": artist.name,
        }

    @staticmethod
    def _container_to_suffix(container: Any) -> str:
        if container.name == "MP3":
            return ".mp3"
        if container.name == "MP4":
            return ".m4a"
        if container.name == "FLAC":
            return ".flac"
        raise RuntimeError(f"Unknown audio container: {container}")

    @staticmethod
    def _container_to_media_type(container: Any) -> str:
        if container.name == "MP3":
            return "audio/mpeg"
        if container.name == "MP4":
            return "audio/mp4"
        if container.name == "FLAC":
            return "audio/flac"
        raise RuntimeError(f"Unknown audio container: {container}")

    @staticmethod
    def _quality_to_core_quality(quality: str) -> Any:
        from ymd import core

        quality_mapping = {
            "low": core.CoreTrackQuality.LOW,
            "normal": core.CoreTrackQuality.NORMAL,
            "lossless": core.CoreTrackQuality.LOSSLESS,
        }
        try:
            return quality_mapping[quality]
        except KeyError as error:
            raise ValueError(f"Unsupported quality: {quality}") from error

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(
            character if character.isalnum() or character in " ._-" else "_"
            for character in value
        ).strip(" ._") or "album"
