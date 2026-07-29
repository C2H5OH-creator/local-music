from pathlib import Path
import sys
import struct
from typing import Any, Iterator
from dataclasses import dataclass
import tempfile
import zipfile
import zlib


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


@dataclass(frozen=True)
class StreamedArchive:
    filename: str
    chunks: Iterator[bytes]


@dataclass(frozen=True)
class DownloadedAlbumDirectory:
    path: Path
    track_count: int


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
        from ymd import core

        track = self.get_track(track_id)
        base_path = cache_dir / "yandex" / "tracks" / str(track.id)
        downloadable = core.to_downloadable_track(
            track,
            core.CoreTrackQuality.LOW,
            base_path,
        )
        cache_path = downloadable.path
        media_type = self._path_to_media_type(cache_path)

        if not cache_path.is_file():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            core.download_track(
                track_info=downloadable,
                embed_cover=False,
                separate_cover=False,
            )

        return CachedAudio(path=cache_path, media_type=media_type)

    def download_album_archive(
        self,
        album_id: int | str,
        quality: str,
        cover_quality: str = "400",
        cover_mode: str = "embedded",
        cache_dir: Path = _DEFAULT_CACHE_DIR,
    ) -> DownloadedArchive:
        _ensure_yandex_music_downloader_importable()
        from ymd import core

        quality_value = self._quality_to_core_quality(quality)
        cover_resolution = self._cover_quality_to_resolution(cover_quality)
        cover_mode_value = self._cover_mode_to_options(cover_mode)
        album = self.get_album(album_id)
        album_info = self.get_album_info(album_id)
        album_name = self._safe_name(album_info["title"] or f"album-{album_id}")
        archive_path = (
            cache_dir
            / "yandex"
            / "albums"
            / f"{album.id}-{quality}-cover-{cover_quality}-{cover_mode}.zip"
        )

        if archive_path.is_file():
            return DownloadedArchive(
                path=archive_path,
                filename=f"{album_name}-{quality}-cover-{cover_quality}-{cover_mode}.zip",
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
                        cover_resolution=cover_resolution,
                        embed_cover=cover_mode_value["embed"],
                        separate_cover=cover_mode_value["separate"],
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
            filename=f"{album_name}-{quality}-cover-{cover_quality}-{cover_mode}.zip",
        )

    def download_album_to_directory(
        self,
        album_id: int | str,
        quality: str,
        target_root: Path,
        cover_quality: str = "400",
        cover_mode: str = "embedded",
    ) -> DownloadedAlbumDirectory:
        _ensure_yandex_music_downloader_importable()
        from ymd import core

        quality_value = self._quality_to_core_quality(quality)
        cover_resolution = self._cover_quality_to_resolution(cover_quality)
        cover_mode_value = self._cover_mode_to_options(cover_mode)
        album = self.get_album(album_id)

        target_root.mkdir(parents=True, exist_ok=True)
        covers_cache = {}
        track_count = 0

        for volume in album.volumes or []:
            for track in volume:
                if not track.available:
                    continue

                base_path = target_root / core.prepare_base_path(
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
                    cover_resolution=cover_resolution,
                    embed_cover=cover_mode_value["embed"],
                    separate_cover=cover_mode_value["separate"],
                    covers_cache=covers_cache,
                )
                track_count += 1

        return DownloadedAlbumDirectory(path=target_root, track_count=track_count)

    def stream_album_archive(
        self,
        album_id: int | str,
        quality: str,
        cover_quality: str = "400",
        cover_mode: str = "embedded",
    ) -> StreamedArchive:
        _ensure_yandex_music_downloader_importable()

        quality_value = self._quality_to_core_quality(quality)
        cover_resolution = self._cover_quality_to_resolution(cover_quality)
        cover_mode_value = self._cover_mode_to_options(cover_mode)
        album = self.get_album(album_id)
        album_info = self.get_album_info(album_id)
        album_name = self._safe_name(album_info["title"] or f"album-{album_id}")

        return StreamedArchive(
            filename=f"{album_name}-{quality}-cover-{cover_quality}-{cover_mode}.zip",
            chunks=self._iter_album_archive_chunks(
                album,
                quality_value,
                cover_resolution,
                cover_mode_value,
            ),
        )

    def _iter_album_archive_chunks(
        self,
        album: Any,
        quality_value: Any,
        cover_resolution: int,
        cover_mode_value: dict[str, bool],
    ) -> Iterator[bytes]:
        from ymd import core

        central_directory = []
        archive_offset = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            covers_cache = {}
            emitted_paths: set[Path] = set()

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

                    archive_name = downloadable.path.relative_to(tmpdir_path).as_posix()
                    header = self._zip_local_file_header(archive_name)
                    yield header
                    archive_offset += len(header)

                    core.download_track(
                        track_info=downloadable,
                        cover_resolution=cover_resolution,
                        embed_cover=cover_mode_value["embed"],
                        separate_cover=cover_mode_value["separate"],
                        covers_cache=covers_cache,
                    )

                    for chunk in self._iter_zip_file_data(downloadable.path):
                        yield chunk
                        archive_offset += len(chunk)

                    file_info = self._zip_file_info(
                        archive_name,
                        downloadable.path,
                        archive_offset_start=archive_offset
                        - self._zip_streamed_member_size(downloadable.path, archive_name),
                    )
                    central_directory.append(file_info)
                    emitted_paths.add(downloadable.path)

                    for file_path in sorted(downloadable.path.parent.glob("cover.*")):
                        if file_path in emitted_paths or not file_path.is_file():
                            continue
                        for chunk in self._iter_zip_member(
                            file_path.relative_to(tmpdir_path).as_posix(),
                            file_path,
                            archive_offset,
                        ):
                            yield chunk
                            archive_offset += len(chunk)
                        central_directory.append(
                            self._zip_file_info(
                                file_path.relative_to(tmpdir_path).as_posix(),
                                file_path,
                                archive_offset_start=archive_offset
                                - self._zip_streamed_member_size(
                                    file_path,
                                    file_path.relative_to(tmpdir_path).as_posix(),
                                ),
                            )
                        )
                        emitted_paths.add(file_path)

            central_directory_offset = archive_offset
            for file_info in central_directory:
                header = self._zip_central_directory_header(file_info)
                yield header
                archive_offset += len(header)

            end_record = self._zip_end_record(
                file_count=len(central_directory),
                central_directory_size=archive_offset - central_directory_offset,
                central_directory_offset=central_directory_offset,
            )
            yield end_record

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
        if container.name == "AAC":
            return ".aac"
        if container.name == "MP3":
            return ".mp3"
        if container.name == "MP4":
            return ".m4a"
        if container.name == "FLAC":
            return ".flac"
        raise RuntimeError(f"Unknown audio container: {container}")

    @staticmethod
    def _container_to_media_type(container: Any) -> str:
        if container.name == "AAC":
            return "audio/aac"
        if container.name == "MP3":
            return "audio/mpeg"
        if container.name == "MP4":
            return "audio/mp4"
        if container.name == "FLAC":
            return "audio/flac"
        raise RuntimeError(f"Unknown audio container: {container}")

    @staticmethod
    def _path_to_media_type(path: Path) -> str:
        if path.suffix == ".mp3":
            return "audio/mpeg"
        if path.suffix == ".m4a":
            return "audio/mp4"
        if path.suffix == ".flac":
            return "audio/flac"
        raise RuntimeError(f"Unknown audio file suffix: {path.suffix}")

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
    def _cover_quality_to_resolution(cover_quality: str) -> int:
        if cover_quality == "original":
            return -1

        try:
            resolution = int(cover_quality)
        except ValueError as error:
            raise ValueError(f"Unsupported cover quality: {cover_quality}") from error

        if resolution < 100:
            raise ValueError(f"Unsupported cover quality: {cover_quality}")
        return resolution

    @staticmethod
    def _cover_mode_to_options(cover_mode: str) -> dict[str, bool]:
        cover_mode_mapping = {
            "no-cover": {"embed": False, "separate": False},
            "embedded": {"embed": True, "separate": False},
            "separate": {"embed": False, "separate": True},
            "both": {"embed": True, "separate": True},
        }
        try:
            return cover_mode_mapping[cover_mode]
        except KeyError as error:
            raise ValueError(f"Unsupported cover mode: {cover_mode}") from error

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(
            character if character.isalnum() or character in " ._-" else "_"
            for character in value
        ).strip(" ._") or "album"

    @staticmethod
    def _dos_time(timestamp: float) -> tuple[int, int]:
        import datetime as dt

        modified_at = dt.datetime.fromtimestamp(timestamp)
        dos_time = (
            (modified_at.hour << 11)
            | (modified_at.minute << 5)
            | (modified_at.second // 2)
        )
        dos_date = (
            ((modified_at.year - 1980) << 9)
            | (modified_at.month << 5)
            | modified_at.day
        )
        return dos_time, dos_date

    @staticmethod
    def _zip_local_file_header(archive_name: str) -> bytes:
        encoded_name = archive_name.encode("utf-8")
        return struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            0x0808,
            8,
            0,
            0,
            0,
            0,
            0,
            len(encoded_name),
            0,
        ) + encoded_name

    @staticmethod
    def _iter_zip_file_data(file_path: Path) -> Iterator[bytes]:
        crc = 0
        compressed_size = 0
        uncompressed_size = 0
        compressor = zlib.compressobj(
            level=6,
            method=zlib.DEFLATED,
            wbits=-15,
        )

        with file_path.open("rb") as file:
            while data := file.read(1024 * 1024):
                crc = zlib.crc32(data, crc)
                uncompressed_size += len(data)
                compressed = compressor.compress(data)
                if compressed:
                    compressed_size += len(compressed)
                    yield compressed

        compressed = compressor.flush()
        if compressed:
            compressed_size += len(compressed)
            yield compressed

        yield struct.pack(
            "<IIII",
            0x08074B50,
            crc & 0xFFFFFFFF,
            compressed_size,
            uncompressed_size,
        )

    def _iter_zip_member(
        self,
        archive_name: str,
        file_path: Path,
        archive_offset: int,
    ) -> Iterator[bytes]:
        header = self._zip_local_file_header(archive_name)
        yield header
        yield from self._iter_zip_file_data(file_path)

    @staticmethod
    def _zip_file_info(
        archive_name: str,
        file_path: Path,
        archive_offset_start: int,
    ) -> dict[str, Any]:
        crc = 0
        compressed_size = 0
        uncompressed_size = 0
        compressor = zlib.compressobj(level=6, method=zlib.DEFLATED, wbits=-15)

        with file_path.open("rb") as file:
            while data := file.read(1024 * 1024):
                crc = zlib.crc32(data, crc)
                uncompressed_size += len(data)
                compressed_size += len(compressor.compress(data))
        compressed_size += len(compressor.flush())
        dos_time, dos_date = YandexMusicProvider._dos_time(file_path.stat().st_mtime)

        return {
            "archive_name": archive_name,
            "crc": crc & 0xFFFFFFFF,
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size,
            "dos_time": dos_time,
            "dos_date": dos_date,
            "offset": archive_offset_start,
        }

    def _zip_streamed_member_size(self, file_path: Path, archive_name: str) -> int:
        file_info = self._zip_file_info(archive_name, file_path, 0)
        return (
            len(self._zip_local_file_header(archive_name))
            + file_info["compressed_size"]
            + 16
        )

    @staticmethod
    def _zip_central_directory_header(file_info: dict[str, Any]) -> bytes:
        encoded_name = file_info["archive_name"].encode("utf-8")
        return struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,
            20,
            0x0808,
            8,
            file_info["dos_time"],
            file_info["dos_date"],
            file_info["crc"],
            file_info["compressed_size"],
            file_info["uncompressed_size"],
            len(encoded_name),
            0,
            0,
            0,
            0,
            0,
            file_info["offset"],
        ) + encoded_name

    @staticmethod
    def _zip_end_record(
        file_count: int,
        central_directory_size: int,
        central_directory_offset: int,
    ) -> bytes:
        return struct.pack(
            "<IHHHHIIH",
            0x06054B50,
            0,
            0,
            file_count,
            file_count,
            central_directory_size,
            central_directory_offset,
            0,
        )
