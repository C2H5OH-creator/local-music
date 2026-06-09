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
    yandex_music_token: str | None
    yandex_music_timeout: int
    yandex_music_max_try_count: int
    yandex_music_retry_delay: int
    yandex_music_request_timeout: int


def get_settings() -> Settings:
    load_env_file()

    return Settings(
        yandex_music_token=os.getenv("TOKEN"),
        yandex_music_timeout=int(os.getenv("YANDEX_MUSIC_TIMEOUT", "10")),
        yandex_music_max_try_count=int(os.getenv("YANDEX_MUSIC_MAX_TRY_COUNT", "2")),
        yandex_music_retry_delay=int(os.getenv("YANDEX_MUSIC_RETRY_DELAY", "1")),
        yandex_music_request_timeout=int(os.getenv("YANDEX_MUSIC_REQUEST_TIMEOUT", "30")),
    )
