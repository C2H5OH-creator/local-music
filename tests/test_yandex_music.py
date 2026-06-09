import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def load_env_file() -> None:
    for env_path in (
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parent / ".env",
    ):
        if not env_path.is_file():
            continue

        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "-"

    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def format_artists(artists: list[dict]) -> str:
    return ", ".join(artist["name"] for artist in artists if artist.get("name"))


class YandexMusicProviderTest(unittest.TestCase):
    def test_remuxes_flac_mp4_to_native_flac(self) -> None:
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is not installed")

        from connectors.yandex_music import _ensure_yandex_music_downloader_importable

        _ensure_yandex_music_downloader_importable()
        from ymd import core

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "source.m4a"
            target_path = tmpdir_path / "target.flac"

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    "-c:a",
                    "flac",
                    "-f",
                    "mp4",
                    str(source_path),
                ],
                check=True,
            )

            core.remux_flac_mp4_via_temporary_file(
                source_path.read_bytes(),
                target_path,
            )

            self.assertTrue(target_path.is_file())
            self.assertEqual(target_path.read_bytes()[:4], b"fLaC")

    def create_provider(self, token: str):
        from connectors.yandex_music import YandexMusicProvider

        try:
            return YandexMusicProvider(token=token)
        except RuntimeError as error:
            if "Cannot import yandex-music-downloader" in str(error):
                self.skipTest(str(error))
            raise

    def print_track_info(self, track_info: dict) -> None:
        try:
            from rich.console import Console
            from rich.table import Table
        except ImportError:
            self.skipTest("rich is not installed")

        table = Table(title="Yandex Music Track")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("ID", str(track_info["id"]))
        table.add_row("Title", track_info["title"])
        table.add_row("Version", track_info["version"] or "-")
        table.add_row("Artists", format_artists(track_info["artists"]))
        table.add_row("Album", (track_info["album"] or {}).get("title", "-"))
        table.add_row("Available", str(track_info["available"]))
        table.add_row("Duration", format_duration(track_info["duration_ms"]))
        table.add_row("Track number", str(track_info["track_number"] or "-"))
        table.add_row("Disc number", str(track_info["disc_number"] or "-"))
        table.add_row("Cover URI", track_info["cover_uri"] or "-")

        Console().print(table)

    def print_album_info(self, album_info: dict) -> None:
        try:
            from rich.console import Console
            from rich.table import Table
        except ImportError:
            self.skipTest("rich is not installed")

        console = Console()

        album_table = Table(title="Yandex Music Album")
        album_table.add_column("Field")
        album_table.add_column("Value")
        album_table.add_row("ID", str(album_info["id"]))
        album_table.add_row("Title", album_info["title"])
        album_table.add_row("Version", album_info["version"] or "-")
        album_table.add_row("Artists", format_artists(album_info["artists"]))
        album_table.add_row("Available", str(album_info["available"]))
        album_table.add_row("Year", str(album_info["year"] or "-"))
        album_table.add_row("Release date", album_info["release_date"] or "-")
        album_table.add_row("Genre", album_info["genre"] or "-")
        album_table.add_row("Track count", str(album_info["track_count"] or "-"))
        album_table.add_row("Cover URI", album_info["cover_uri"] or "-")

        tracks_table = Table(title="Album Tracks")
        tracks_table.add_column("#", justify="right")
        tracks_table.add_column("Disc", justify="right")
        tracks_table.add_column("ID")
        tracks_table.add_column("Title")
        tracks_table.add_column("Artists")
        tracks_table.add_column("Duration", justify="right")
        tracks_table.add_column("Available")

        for track in album_info["tracks"]:
            tracks_table.add_row(
                str(track["track_number"] or "-"),
                str(track["disc_number"] or "-"),
                str(track["id"]),
                track["title"],
                format_artists(track["artists"]),
                format_duration(track["duration_ms"]),
                str(track["available"]),
            )

        console.print(album_table)
        console.print(tracks_table)

    def test_initializes_and_gets_track_info(self) -> None:
        load_env_file()

        token = os.getenv("TOKEN")
        track_id = os.getenv("TRACK_ID")

        if not token:
            self.skipTest("TOKEN is not set")
        if not track_id:
            self.skipTest("TRACK_ID is not set")

        provider = self.create_provider(token)
        track_info = provider.get_track_info(track_id)
        self.print_track_info(track_info)

        self.assertEqual(str(track_info["id"]), str(track_id))
        self.assertIsInstance(track_info["title"], str)
        self.assertTrue(track_info["title"])
        self.assertIsInstance(track_info["artists"], list)
        self.assertTrue(track_info["artists"])
        self.assertIn("available", track_info)

    def test_initializes_and_gets_album_info(self) -> None:
        load_env_file()

        token = os.getenv("TOKEN")
        album_id = os.getenv("ALBUM_ID")

        if not token:
            self.skipTest("TOKEN is not set")
        if not album_id:
            self.skipTest("ALBUM_ID is not set")

        provider = self.create_provider(token)
        album_info = provider.get_album_info(album_id)
        self.print_album_info(album_info)

        self.assertEqual(str(album_info["id"]), str(album_id))
        self.assertIsInstance(album_info["title"], str)
        self.assertTrue(album_info["title"])
        self.assertIsInstance(album_info["artists"], list)
        self.assertTrue(album_info["artists"])
        self.assertIsInstance(album_info["tracks"], list)
        self.assertTrue(album_info["tracks"])

        first_track = album_info["tracks"][0]
        self.assertIn("id", first_track)
        self.assertIsInstance(first_track["title"], str)
        self.assertTrue(first_track["title"])
        self.assertIn("duration_ms", first_track)
        self.assertIn("track_number", first_track)
        self.assertIn("disc_number", first_track)


if __name__ == "__main__":
    unittest.main()
