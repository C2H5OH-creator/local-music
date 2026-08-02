import unittest

from connectors.yandex_links import (
    extract_album_id,
    extract_track_id,
    parse_yandex_music_link,
)


class ParseYandexMusicLinkTests(unittest.TestCase):
    def test_album_link(self):
        link = parse_yandex_music_link("https://music.yandex.ru/album/42791372")
        self.assertIsNotNone(link)
        self.assertEqual(link.album_id, "42791372")
        self.assertIsNone(link.track_id)

    def test_track_link(self):
        link = parse_yandex_music_link(
            "https://music.yandex.ru/album/42791372/track/123456"
        )
        self.assertIsNotNone(link)
        self.assertEqual(link.album_id, "42791372")
        self.assertEqual(link.track_id, "123456")

    def test_trailing_slash_and_query(self):
        link = parse_yandex_music_link(
            "https://music.yandex.ru/album/42791372/?utm_source=web#anchor"
        )
        self.assertIsNotNone(link)
        self.assertEqual(link.album_id, "42791372")

    def test_other_domains(self):
        for domain in ("com", "kz", "by", "com.tr"):
            with self.subTest(domain=domain):
                link = parse_yandex_music_link(
                    f"https://music.yandex.{domain}/album/42"
                )
                self.assertIsNotNone(link)
                self.assertEqual(link.album_id, "42")

    def test_without_scheme(self):
        link = parse_yandex_music_link("music.yandex.ru/album/42")
        self.assertIsNotNone(link)
        self.assertEqual(link.album_id, "42")

    def test_non_matching_links(self):
        for value in (
            "https://music.yandex.ru/artist/123",
            "https://music.yandex.ru/album/abc",
            "https://example.com/album/42",
            "https://music.yandex.ru/",
        ):
            with self.subTest(value=value):
                self.assertIsNone(parse_yandex_music_link(value))


class ExtractAlbumIdTests(unittest.TestCase):
    def test_plain_id_passes_through(self):
        self.assertEqual(extract_album_id(" 42791372 "), "42791372")

    def test_album_link(self):
        self.assertEqual(
            extract_album_id("https://music.yandex.ru/album/42791372"),
            "42791372",
        )

    def test_track_link_gives_album_id(self):
        self.assertEqual(
            extract_album_id("https://music.yandex.ru/album/42791372/track/123456"),
            "42791372",
        )

    def test_invalid_value_raises(self):
        with self.assertRaises(ValueError):
            extract_album_id("https://music.yandex.ru/artist/123")


class ExtractTrackIdTests(unittest.TestCase):
    def test_plain_id_passes_through(self):
        self.assertEqual(extract_track_id("123456"), "123456")

    def test_track_link(self):
        self.assertEqual(
            extract_track_id("https://music.yandex.ru/album/42791372/track/123456"),
            "123456",
        )

    def test_album_link_has_no_track_id(self):
        with self.assertRaises(ValueError):
            extract_track_id("https://music.yandex.ru/album/42791372")


if __name__ == "__main__":
    unittest.main()
