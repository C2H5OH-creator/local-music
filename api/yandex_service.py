from connectors.yandex_music import YandexMusicProvider
from api.settings import get_settings


_yandex_music_provider: YandexMusicProvider | None = None
_yandex_music_token: str | None = None


def create_yandex_music_provider(token: str) -> YandexMusicProvider:
    settings = get_settings()
    return YandexMusicProvider(
        token=token,
        timeout=settings.yandex_music_timeout,
        max_try_count=settings.yandex_music_max_try_count,
        retry_delay=settings.yandex_music_retry_delay,
    )


def get_yandex_music_provider() -> YandexMusicProvider:
    global _yandex_music_provider

    if _yandex_music_provider is not None:
        return _yandex_music_provider

    settings = get_settings()
    token = _yandex_music_token or settings.yandex_music_token
    if not token:
        raise RuntimeError("Yandex Music token is not configured")

    _yandex_music_provider = create_yandex_music_provider(token)
    return _yandex_music_provider


def set_yandex_music_provider(token: str) -> None:
    set_yandex_music_token(token)


def set_yandex_music_token(token: str) -> None:
    global _yandex_music_token
    global _yandex_music_provider

    token = token.strip()
    if not token:
        raise ValueError("Yandex Music token is empty")

    _yandex_music_token = token
    _yandex_music_provider = None
