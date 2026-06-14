import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    app_secret_key: str
    database_url: str | None
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: str
    yandex_music_token: str | None
    yandex_music_timeout: int
    yandex_music_max_try_count: int
    yandex_music_retry_delay: int
    yandex_music_request_timeout: int
    yandex_music_album_request_timeout: int
    server_music_base_path: Path


def get_settings() -> Settings:
    load_env_file()

    return Settings(
        app_secret_key=os.getenv("APP_SECRET_KEY", "local-music-dev-secret-change-me"),
        database_url=os.getenv("DATABASE_URL") or None,
        database_host=os.getenv("DATABASE_HOST", "127.0.0.1"),
        database_port=int(os.getenv("DATABASE_PORT", "4501")),
        database_name=os.getenv("DATABASE_NAME", "local_music"),
        database_user=os.getenv("DATABASE_USER", "local_music"),
        database_password=os.getenv("DATABASE_PASSWORD", "local_music"),
        yandex_music_token=os.getenv("TOKEN"),
        yandex_music_timeout=int(os.getenv("YANDEX_MUSIC_TIMEOUT", "10")),
        yandex_music_max_try_count=int(os.getenv("YANDEX_MUSIC_MAX_TRY_COUNT", "2")),
        yandex_music_retry_delay=int(os.getenv("YANDEX_MUSIC_RETRY_DELAY", "1")),
        yandex_music_request_timeout=int(os.getenv("YANDEX_MUSIC_REQUEST_TIMEOUT", "30")),
        yandex_music_album_request_timeout=int(
            os.getenv("YANDEX_MUSIC_ALBUM_REQUEST_TIMEOUT", "120")
        ),
        server_music_base_path=Path(os.getenv("SERVER_MUSIC_BASE_PATH", "/music")),
    )
