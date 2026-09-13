from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
import responses

from mopidy_tunein import tunein

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

type Parser = Callable[[bytes], Generator[str]]

BASE = "https://opml.radiotime.com/"

ROOT = [
    {"element": "outline", "type": "link", "text": "Local Radio", "key": "local"},
    {"element": "outline", "type": "link", "text": "Music", "key": "music"},
    {"element": "outline", "type": "link", "text": "By Language", "key": "language"},
]

STATION_ONE = {
    "element": "outline",
    "type": "audio",
    "text": "Beat FM 105.5",
    "URL": "http://opml.radiotime.com/Tune.ashx?id=s128641",
    "guide_id": "s128641",
    "subtext": "Mer variert musikk",
    "item": "station",
    "image": "http://cdn.example.com/s128641.png",
}
STATION_TWO = {
    "element": "outline",
    "type": "audio",
    "text": "Heart Radio",
    "URL": "http://opml.radiotime.com/Tune.ashx?id=s346757",
    "guide_id": "s346757",
    "subtext": "Non-stop feel good",
    "item": "station",
}
SECTION_LINK = {
    "element": "outline",
    "type": "link",
    "text": "Country",
    "URL": "http://opml.radiotime.com/Browse.ashx?id=c57940",
    "guide_id": "c57940",
}

STATIONS_SECTION = [
    {
        "element": "outline",
        "text": "Stations",
        "key": "stations",
        "children": [STATION_ONE, STATION_TWO],
    },
    {
        "element": "outline",
        "text": "Local Stations",
        "key": "local",
        "children": [STATION_TWO],
    },
]

DESCRIBE = [
    {
        "element": "outline",
        "text": "Listing",
        "key": "listing",
        "children": [
            {
                "element": "station",
                "guide_id": "s24791",
                "name": "WYPR",
                "slogan": "Baltimore Public Media",
                "logo": "http://cdn.example.com/s24791.png",
            }
        ],
    }
]

DUAL_FORMAT_TUNE = [
    {
        "element": "audio",
        "url": "http://a/aac-high",
        "media_type": "aac",
        "bitrate": 128,
    },
    {"element": "audio", "url": "http://a/mp3-low", "media_type": "mp3", "bitrate": 64},
    {
        "element": "audio",
        "url": "http://a/mp3-high",
        "media_type": "mp3",
        "bitrate": 192,
    },
    {"element": "audio", "url": "http://a/aac-low", "media_type": "aac", "bitrate": 48},
]

PLACEHOLDER_TUNE = [
    {
        "element": "audio",
        "url": "http://cdn-cms.tunein.com/service/Audio/notcompatible.enUS.mp3",
        "media_type": "mp3",
        "bitrate": 24,
    },
    {"element": "audio", "url": "http://a/real", "media_type": "aac", "bitrate": 64},
]

TUNE = [
    {"element": "audio", "url": "http://stream.example.com/one", "guide_id": "e1"},
    {"element": "audio", "url": "http://stream.example.com/two", "guide_id": "e2"},
    {"element": "audio", "url": "http://stream.example.com/one", "guide_id": "e3"},
]

SEARCH = [
    {"element": "outline", "type": "link", "text": "Artist: BBC", "guide_id": "m1"},
    STATION_ONE,
    {"element": "outline", "text": "Group", "children": [STATION_TWO]},
]


def api_body(body: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"head": {"status": "200"}, "body": body}


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    # The cache decorators are class attributes, so they outlive an instance.
    tunein.TuneIn._tunein_cache.clear()
    tunein.TuneIn._playlist_cache.clear()


@pytest.fixture
def api() -> tunein.TuneIn:
    return tunein.TuneIn(timeout=1000)


def add_response(variant: str, body: Any, **kwargs: Any) -> None:  # noqa: ANN401
    responses.add(responses.GET, BASE + variant, json=api_body(body), **kwargs)


def request_url(index: int = 0) -> str:
    url = responses.calls[index].request.url
    assert url is not None
    return url


def test_no_filter_by_default(api: tunein.TuneIn) -> None:
    assert api._filter == ""


@pytest.mark.parametrize(
    ("filter_", "expected"),
    [("station", "&filter=s"), ("program", "&filter=p")],
)
def test_known_filter_is_abbreviated(filter_: str, expected: str) -> None:
    assert tunein.TuneIn(1000, filter_)._filter == expected


def test_unknown_filter_is_ignored() -> None:
    assert tunein.TuneIn(1000, "nonsense")._filter == ""


@responses.activate
def test_request_returns_the_body(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", ROOT)

    assert api._tunein("Browse.ashx", "&c=music") == ROOT


@responses.activate
def test_request_sends_the_expected_query(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", ROOT)

    api._tunein("Browse.ashx", "&c=music")

    assert request_url() == BASE + "Browse.ashx?render=json&c=music"


@responses.activate
def test_request_http_error_gives_no_results(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", ROOT, status=500)

    assert api._tunein("Browse.ashx", "") == []


@responses.activate
def test_request_connection_error_gives_no_results(api: tunein.TuneIn) -> None:
    responses.add(responses.GET, BASE + "Browse.ashx", body=OSError("boom"))

    assert api._tunein("Browse.ashx", "") == []


@responses.activate
def test_request_result_is_cached(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", ROOT)

    api._tunein("Browse.ashx", "")
    api._tunein("Browse.ashx", "")

    assert len(responses.calls) == 1


@responses.activate
def test_reload_clears_the_request_cache(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", ROOT)

    api._tunein("Browse.ashx", "")
    api.reload()
    api._tunein("Browse.ashx", "")

    assert len(responses.calls) == 2


@responses.activate
def test_categories_root_appends_trending_and_drops_language(
    api: tunein.TuneIn,
) -> None:
    add_response("Browse.ashx", ROOT)

    keys = [c["key"] for c in api.categories()]

    assert keys == ["local", "music", "trending"]


@responses.activate
def test_categories_root_does_not_modify_the_cached_data(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", ROOT)

    first = api.categories()
    second = api.categories()

    assert first == second


@responses.activate
def test_categories_language_is_not_requested(api: tunein.TuneIn) -> None:
    assert api.categories("language") == []
    assert not responses.calls


@responses.activate
def test_categories_local_sends_the_configured_location() -> None:
    api = tunein.TuneIn(timeout=1000, location="51.5,-0.13")
    add_response("Browse.ashx", [])

    api.categories("local")

    assert "latlon=51.5,-0.13" in request_url()


@responses.activate
def test_categories_local_without_a_location(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", [])

    api.categories("local")

    assert "latlon=" not in request_url()


@responses.activate
def test_the_location_is_only_for_local_radio() -> None:
    api = tunein.TuneIn(timeout=1000, location="51.5,-0.13")
    add_response("Browse.ashx", [])

    api.categories("music")

    assert "latlon=" not in request_url()


@responses.activate
def test_categories_location_uses_the_root_region(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", [SECTION_LINK])

    api.categories("location")

    assert "id=r0" in request_url()


@responses.activate
def test_categories_podcast_is_flattened(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", STATIONS_SECTION)

    result = api.categories("podcast")

    assert [s["guide_id"] for s in result] == ["s128641", "s346757", "s346757"]


@responses.activate
def test_stations_returns_the_matching_section(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", STATIONS_SECTION)

    result = api.stations("c1")

    assert [s["guide_id"] for s in result] == ["s128641", "s346757"]


@responses.activate
def test_local_returns_the_matching_section(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", STATIONS_SECTION)

    assert [s["guide_id"] for s in api.local("c1")] == ["s346757"]


@responses.activate
def test_browse_unmatched_section_is_empty(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", STATIONS_SECTION)

    assert api.shows("c1") == []


@responses.activate
def test_locations_keeps_only_links(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", [SECTION_LINK, STATION_ONE])

    assert api.locations("r0") == [SECTION_LINK]


@responses.activate
def test_browse_fills_the_station_cache(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", STATIONS_SECTION)

    api.stations("c1")

    assert set(api._stations) == {"s128641", "s346757"}


def test_filter_results_drops_items_without_a_guide_id(api: tunein.TuneIn) -> None:
    assert api._filter_results([{"element": "outline", "text": "No id"}]) == []


def test_flatten_expands_children(api: tunein.TuneIn) -> None:
    result = api._flatten(STATIONS_SECTION)

    assert [s["guide_id"] for s in result] == ["s128641", "s346757", "s346757"]


def test_flatten_keeps_childless_items(api: tunein.TuneIn) -> None:
    assert api._flatten([STATION_ONE]) == [STATION_ONE]


@responses.activate
def test_station_maps_the_listing(api: tunein.TuneIn) -> None:
    add_response("Describe.ashx", DESCRIBE)

    station = api.station("s24791")

    assert station == {
        "text": "WYPR",
        "guide_id": "s24791",
        "type": "audio",
        "image": "http://cdn.example.com/s24791.png",
        "subtext": "Baltimore Public Media",
        "URL": BASE + "Tune.ashx?id=s24791",
    }


@responses.activate
def test_station_is_cached_after_the_first_lookup(api: tunein.TuneIn) -> None:
    add_response("Describe.ashx", DESCRIBE)

    api.station("s24791")
    api.reload()  # Only clears the request cache, not the station cache.
    api._stations["s24791"] = {"guide_id": "s24791", "text": "From cache"}

    station = api.station("s24791")

    assert station is not None
    assert station["text"] == "From cache"


@responses.activate
def test_unknown_station_is_none(api: tunein.TuneIn) -> None:
    add_response("Describe.ashx", [])

    assert api.station("s404") is None


@responses.activate
def test_failed_station_lookup_is_not_cached(api: tunein.TuneIn) -> None:
    add_response("Describe.ashx", [])

    api.station("s404")

    assert "s404" not in api._stations


@responses.activate
def test_tune_returns_the_stream_urls_without_duplicates(api: tunein.TuneIn) -> None:
    add_response("Tune.ashx", TUNE)

    assert api.tune({"guide_id": "s1"}) == [
        "http://stream.example.com/one",
        "http://stream.example.com/two",
    ]


@responses.activate
def test_tune_prefers_mp3_then_the_higher_bitrate() -> None:
    api = tunein.TuneIn(timeout=1000, formats=["mp3", "aac"])
    add_response("Tune.ashx", DUAL_FORMAT_TUNE)

    assert api.tune({"guide_id": "s1"}) == [
        "http://a/mp3-high",
        "http://a/mp3-low",
        "http://a/aac-high",
        "http://a/aac-low",
    ]


@responses.activate
def test_tune_keeps_an_aac_only_station(api: tunein.TuneIn) -> None:
    add_response("Tune.ashx", [DUAL_FORMAT_TUNE[0], DUAL_FORMAT_TUNE[3]])

    assert api.tune({"guide_id": "s1"}) == ["http://a/aac-high", "http://a/aac-low"]


@responses.activate
def test_tune_drops_the_not_compatible_recording(api: tunein.TuneIn) -> None:
    add_response("Tune.ashx", PLACEHOLDER_TUNE)

    assert api.tune({"guide_id": "s1"}) == ["http://a/real"]


@responses.activate
def test_tune_puts_an_unknown_format_last(api: tunein.TuneIn) -> None:
    add_response(
        "Tune.ashx",
        [
            {
                "element": "audio",
                "url": "http://a/wma",
                "media_type": "wma",
                "bitrate": 999,
            },
            {
                "element": "audio",
                "url": "http://a/aac",
                "media_type": "aac",
                "bitrate": 32,
            },
        ],
    )

    assert api.tune({"guide_id": "s1"}) == ["http://a/aac", "http://a/wma"]


@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ({"media_type": "mp3", "bitrate": 128}, (0, -128)),
        ({"media_type": "aac", "bitrate": 64}, (1, -64)),
        ({"media_type": "wma", "bitrate": 128}, (2, -128)),
        ({"media_type": "mp3", "bitrate": "96"}, (0, -96)),
        ({"media_type": "mp3"}, (0, 0)),
        ({"media_type": "mp3", "bitrate": None}, (0, 0)),
        ({"media_type": "mp3", "bitrate": "many"}, (0, 0)),
        ({}, (2, 0)),
    ],
)
def test_stream_priority(stream: dict[str, Any], expected: tuple[int, int]) -> None:
    assert tunein.stream_priority(stream) == expected


@responses.activate
def test_formats_are_sent_with_browse_search_and_tune() -> None:
    api = tunein.TuneIn(timeout=1000, formats=["mp3", "aac"])
    add_response("Browse.ashx", [])
    add_response("Search.ashx", [])
    add_response("Tune.ashx", [])

    api.stations("c1")
    api.search("bbc")
    api.tune({"guide_id": "s1"})

    assert all("formats=mp3,aac" in request_url(i) for i in range(3))


@responses.activate
def test_formats_are_not_sent_when_not_configured(api: tunein.TuneIn) -> None:
    add_response("Browse.ashx", [])

    api.stations("c1")

    assert "formats=" not in request_url()


@responses.activate
def test_formats_are_not_sent_when_describing_a_station() -> None:
    api = tunein.TuneIn(timeout=1000, formats=["mp3", "aac"])
    add_response("Describe.ashx", DESCRIBE)

    api.station("s24791")

    assert "formats=" not in request_url()


@responses.activate
def test_tune_drops_entries_without_a_url(api: tunein.TuneIn) -> None:
    add_response("Tune.ashx", [{"element": "audio", "guide_id": "e1"}])

    assert api.tune({"guide_id": "s1"}) == []


@responses.activate
def test_tune_logs_a_station_without_streams(
    api: tunein.TuneIn, caplog: pytest.LogCaptureFixture
) -> None:
    add_response("Tune.ashx", [])

    with caplog.at_level(logging.ERROR):
        api.tune({"guide_id": "s1"})

    assert "Failed to tune station id s1" in caplog.text


@responses.activate
def test_search_keeps_only_stations(api: tunein.TuneIn) -> None:
    add_response("Search.ashx", SEARCH)

    result = api.search("bbc")

    assert [s["guide_id"] for s in result] == ["s128641", "s346757"]


@responses.activate
def test_search_fills_the_station_cache(api: tunein.TuneIn) -> None:
    add_response("Search.ashx", SEARCH)

    api.search("bbc")

    assert set(api._stations) == {"s128641", "s346757"}


@responses.activate
def test_search_empty_query_is_not_requested(api: tunein.TuneIn) -> None:
    assert api.search("") == []
    assert not responses.calls


@responses.activate
def test_search_filter_is_part_of_the_query() -> None:
    add_response("Search.ashx", [])

    tunein.TuneIn(1000, "station").search("bbc")

    assert "filter=s" in request_url()


@responses.activate
@pytest.mark.parametrize("url", ["http://a/b.mp3", "http://a/b.wma"])
def test_parse_stream_url_uses_an_audio_extension_as_is(
    api: tunein.TuneIn, url: str
) -> None:
    assert api.parse_stream_url(url) == [url]
    assert not responses.calls


@responses.activate
def test_parse_stream_url_parses_a_playlist(api: tunein.TuneIn) -> None:
    responses.add(
        responses.GET,
        "http://a/b.pls",
        body=b"[playlist]\nNumberOfEntries=1\nFile1=http://a/stream\n",
        content_type="audio/x-scpls",
    )

    assert api.parse_stream_url("http://a/b.pls") == ["http://a/stream"]


@responses.activate
def test_parse_stream_url_uses_a_stream_as_is(api: tunein.TuneIn) -> None:
    responses.add(responses.GET, "http://a/stream", body=b"", content_type="audio/mpeg")

    assert api.parse_stream_url("http://a/stream") == ["http://a/stream"]


@responses.activate
def test_parse_stream_url_falls_back_to_the_content_type(api: tunein.TuneIn) -> None:
    responses.add(
        responses.GET,
        "http://a/listen",
        body=b"[playlist]\nNumberOfEntries=1\nFile1=http://a/stream\n",
        content_type="audio/x-scpls; charset=UTF-8",
    )

    assert api.parse_stream_url("http://a/listen") == ["http://a/stream"]


@responses.activate
def test_parse_stream_url_gives_no_results_for_a_malformed_playlist(
    api: tunein.TuneIn,
) -> None:
    responses.add(
        responses.GET,
        "http://a/b.pls",
        body=b"not a playlist",
        content_type="audio/x-scpls",
    )

    assert api.parse_stream_url("http://a/b.pls") == []


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("audio/x-scpls", "audio/x-scpls"),
        ("audio/x-scpls; charset=UTF-8", "audio/x-scpls"),
        ("Audio/X-SCPLS", "audio/x-scpls"),
        ("  audio/mpeg ; charset=utf-8", "audio/mpeg"),
        ("", ""),
    ],
)
def test_media_type_drops_parameters(content_type: str, expected: str) -> None:
    assert tunein.media_type(content_type) == expected


@pytest.mark.parametrize(
    ("extension", "expected"),
    [
        (".pls", tunein.parse_pls),
        (".m3u", tunein.parse_m3u),
        (".asx", tunein.parse_asx),
        (".wax", tunein.parse_asx),
        (".mp3", None),
    ],
)
def test_find_playlist_parser_uses_the_extension_first(
    extension: str, expected: Parser | None
) -> None:
    assert tunein.find_playlist_parser(extension, None) is expected


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        # These are the content types the TuneIn servers were seen to send.
        ("audio/x-scpls; charset=UTF-8", tunein.parse_pls),
        ("audio/x-scpls", tunein.parse_pls),
        ("audio/x-mpegurl", tunein.parse_m3u),
        ("application/x-mpegurl", tunein.parse_m3u),
        ("video/x-ms-asf", tunein.parse_asx),
        ("text/html", None),
        ("audio/mpeg", None),
    ],
)
def test_find_playlist_parser_falls_back_to_the_content_type(
    content_type: str, expected: Parser | None
) -> None:
    assert tunein.find_playlist_parser(".xxx", content_type) is expected


def test_find_playlist_parser_prefers_the_extension() -> None:
    parser = tunein.find_playlist_parser(".pls", "audio/x-mpegurl")

    assert parser is tunein.parse_pls


def test_find_playlist_parser_without_hints() -> None:
    assert tunein.find_playlist_parser("", None) is None


class EndlessResponse:
    """Stands in for a live stream: a body that never ends."""

    url = "http://a/stream"

    def __init__(self) -> None:
        self.chunks_read = 0

    def iter_content(self, chunk_size: int) -> Generator[bytes]:
        while True:
            self.chunks_read += 1
            yield b"x" * chunk_size


def test_read_playlist_body_gives_up_on_an_endless_body() -> None:
    response = EndlessResponse()

    result = tunein.read_playlist_body(response, timeout=30, max_bytes=1024)  # type: ignore[arg-type]

    assert result is None
    assert response.chunks_read < 10  # Stopped early, did not run away.


def test_read_playlist_body_gives_up_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([0.0, 0.0, 100.0])
    monkeypatch.setattr(tunein.time, "time", lambda: next(clock))
    response = EndlessResponse()

    result = tunein.read_playlist_body(
        response,  # type: ignore[arg-type]
        timeout=1,
        max_bytes=1024 * 1024,
    )

    assert result is None


@responses.activate
def test_get_playlist_skips_an_audio_body(api: tunein.TuneIn) -> None:
    responses.add(responses.GET, "http://a/s", body=b"audio", content_type="audio/mpeg")

    assert api._get_playlist("http://a/s") == (None, "audio/mpeg")


@responses.activate
def test_get_playlist_skips_an_audio_body_with_a_charset(api: tunein.TuneIn) -> None:
    responses.add(
        responses.GET,
        "http://a/s",
        body=b"audio",
        content_type="audio/mpeg; charset=UTF-8",
    )

    data, _ = api._get_playlist("http://a/s")

    assert data is None


@responses.activate
def test_get_playlist_reads_a_playlist_body(api: tunein.TuneIn) -> None:
    responses.add(
        responses.GET,
        "http://a/p.pls",
        body=b"[playlist]",
        content_type="audio/x-scpls",
    )

    assert api._get_playlist("http://a/p.pls") == (b"[playlist]", "audio/x-scpls")


@responses.activate
def test_get_playlist_failed_request_gives_nothing(api: tunein.TuneIn) -> None:
    responses.add(responses.GET, "http://a/p.pls", status=404)

    assert api._get_playlist("http://a/p.pls") == (None, None)


@responses.activate
def test_get_playlist_body_over_the_size_limit_is_not_a_playlist(
    api: tunein.TuneIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tunein, "PLAYLIST_MAX_BYTES", 1024)
    responses.add(
        responses.GET,
        "http://a/stream",
        body=b"x" * 4096,
        content_type="audio/aac",
    )

    assert api._get_playlist("http://a/stream") == (None, "audio/aac")


@responses.activate
def test_get_playlist_body_under_the_size_limit_is_a_playlist(
    api: tunein.TuneIn,
) -> None:
    responses.add(
        responses.GET,
        "http://a/p.pls",
        body=b"[playlist]\nFile1=http://a/s\n",
        content_type="audio/x-scpls",
    )

    data, _ = api._get_playlist("http://a/p.pls")

    assert data == b"[playlist]\nFile1=http://a/s\n"
