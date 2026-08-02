import re
from dataclasses import dataclass

# https://music.yandex.ru/album/42791372
# https://music.yandex.ru/album/42791372/track/123456
YANDEX_MUSIC_LINK_RE = re.compile(
    r"^(?:https?://)?music\.yandex\.[a-z]{2,}(?:\.[a-z]{2})?"
    r"/album/(?P<album_id>\d+)"
    r"(?:/track/(?P<track_id>\d+))?"
    r"/?(?:[?#].*)?$"
)


@dataclass(frozen=True)
class YandexMusicLink:
    album_id: str | None = None
    track_id: str | None = None


def parse_yandex_music_link(value: str) -> YandexMusicLink | None:
    match = YANDEX_MUSIC_LINK_RE.match(value.strip())
    if match is None:
        return None
    return YandexMusicLink(
        album_id=match.group("album_id"),
        track_id=match.group("track_id"),
    )


def extract_album_id(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value

    link = parse_yandex_music_link(value)
    if link is not None and link.album_id is not None:
        return link.album_id

    raise ValueError("Не удалось определить ID альбома из ссылки")


def extract_track_id(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value

    link = parse_yandex_music_link(value)
    if link is not None and link.track_id is not None:
        return link.track_id

    raise ValueError("Не удалось определить ID трека из ссылки")
