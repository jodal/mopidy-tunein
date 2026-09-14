from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from mopidy_tunein import tunein

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from pytest_httpx import HTTPXMock

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

NEXT_STATIONS = {
    "element": "outline",
    "type": "link",
    "text": "More Stations",
    "URL": "http://opml.radiotime.com/Browse.ashx?offset=26&id=c1&filter=s",
    "key": "nextStations",
}

PAGED_SECTION = [
    {
        "element": "outline",
        "text": "Stations",
        "key": "stations",
        "children": [STATION_ONE, STATION_TWO, NEXT_STATIONS],
    }
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


def api_url(variant: str) -> re.Pattern[str]:
    """Match an API request whatever query string it carries."""
    return re.compile(rf"^{re.escape(BASE + variant)}\?")


def add_response(
    httpx_mock: HTTPXMock,
    variant: str,
    body: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> None:
    httpx_mock.add_response(
        url=api_url(variant),
        json=api_body(body),
        **kwargs,
    )


def request_url(httpx_mock: HTTPXMock, index: int = 0) -> str:
    return str(httpx_mock.get_requests()[index].url)


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


def test_request_returns_the_body(api: tunein.TuneIn, httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT)

    assert api._tunein("Browse.ashx", "&c=music") == ROOT


def test_request_sends_the_expected_query(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT)

    api._tunein("Browse.ashx", "&c=music")

    assert request_url(httpx_mock) == BASE + "Browse.ashx?render=json&c=music"


def test_request_http_error_gives_no_results(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT, status_code=500)

    assert api._tunein("Browse.ashx", "") == []


def test_request_connection_error_gives_no_results(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("boom"), url=api_url("Browse.ashx"))

    assert api._tunein("Browse.ashx", "") == []


def test_request_result_is_cached(api: tunein.TuneIn, httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT)

    api._tunein("Browse.ashx", "")
    api._tunein("Browse.ashx", "")

    assert len(httpx_mock.get_requests()) == 1


def test_reload_clears_the_request_cache(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT, is_reusable=True)

    api._tunein("Browse.ashx", "")
    api.reload()
    api._tunein("Browse.ashx", "")

    assert len(httpx_mock.get_requests()) == 2


def test_categories_root_appends_trending_and_drops_language(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT)

    keys = [c["key"] for c in api.categories()]

    assert keys == ["local", "music", "trending"]


def test_categories_root_does_not_modify_the_cached_data(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", ROOT)

    first = api.categories()
    second = api.categories()

    assert first == second


def test_categories_language_is_not_requested(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    assert api.categories("language") == []
    assert not httpx_mock.get_requests()


def test_categories_local_sends_the_configured_location(httpx_mock: HTTPXMock) -> None:
    api = tunein.TuneIn(timeout=1000, location="51.5,-0.13")
    add_response(httpx_mock, "Browse.ashx", [])

    api.categories("local")

    assert "latlon=51.5,-0.13" in request_url(httpx_mock)


def test_categories_local_without_a_location(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", [])

    api.categories("local")

    assert "latlon=" not in request_url(httpx_mock)


def test_the_location_is_only_for_local_radio(httpx_mock: HTTPXMock) -> None:
    api = tunein.TuneIn(timeout=1000, location="51.5,-0.13")
    add_response(httpx_mock, "Browse.ashx", [])

    api.categories("music")

    assert "latlon=" not in request_url(httpx_mock)


def test_categories_location_uses_the_root_region(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", [SECTION_LINK])

    api.categories("location")

    assert "id=r0" in request_url(httpx_mock)


def test_categories_podcast_is_flattened(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", STATIONS_SECTION)

    result = api.categories("podcast")

    assert [s["guide_id"] for s in result] == ["s128641", "s346757", "s346757"]


def test_stations_returns_the_matching_section(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", STATIONS_SECTION)

    result = api.stations("c1")

    assert [s["guide_id"] for s in result] == ["s128641", "s346757"]


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("http://a/Browse.ashx?offset=26&id=c1", 26),
        ("http://a/Browse.ashx?id=c1&offset=51&filter=s", 51),
        ("http://a/Browse.ashx?id=c1", None),
        ("http://a/Browse.ashx?offset=lots", None),
        ("", None),
    ],
)
def test_page_offset(uri: str, expected: int | None) -> None:
    assert tunein.page_offset(uri) == expected


def test_next_stations_offset_finds_the_link(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", PAGED_SECTION)

    assert api.next_stations_offset("c1") == 26


def test_next_stations_offset_without_a_link(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", STATIONS_SECTION)

    assert api.next_stations_offset("c1") is None


def test_the_next_page_link_is_not_a_station(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", PAGED_SECTION)

    assert [s["guide_id"] for s in api.stations("c1")] == ["s128641", "s346757"]


def test_stations_asks_for_the_given_page(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", PAGED_SECTION)

    api.stations("c1", offset=26)

    assert "offset=26" in request_url(httpx_mock)


def test_stations_asks_for_no_offset_on_the_first_page(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", PAGED_SECTION)

    api.stations("c1")

    assert "offset=" not in request_url(httpx_mock)


def test_local_returns_the_matching_section(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", STATIONS_SECTION)

    assert [s["guide_id"] for s in api.local("c1")] == ["s346757"]


def test_browse_unmatched_section_is_empty(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", STATIONS_SECTION)

    assert api.shows("c1") == []


def test_locations_keeps_only_links(api: tunein.TuneIn, httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Browse.ashx", [SECTION_LINK, STATION_ONE])

    assert api.locations("r0") == [SECTION_LINK]


def test_browse_fills_the_station_cache(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", STATIONS_SECTION)

    api.stations("c1")

    assert set(api._stations) == {"s128641", "s346757"}


def test_filter_results_drops_items_without_a_guide_id(api: tunein.TuneIn) -> None:
    assert api._filter_results([{"element": "outline", "text": "No id"}]) == []


def test_flatten_expands_children(api: tunein.TuneIn) -> None:
    result = api._flatten(STATIONS_SECTION)

    assert [s["guide_id"] for s in result] == ["s128641", "s346757", "s346757"]


def test_flatten_keeps_childless_items(api: tunein.TuneIn) -> None:
    assert api._flatten([STATION_ONE]) == [STATION_ONE]


def test_station_maps_the_listing(api: tunein.TuneIn, httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Describe.ashx", DESCRIBE)

    station = api.station("s24791")

    assert station == {
        "text": "WYPR",
        "guide_id": "s24791",
        "type": "audio",
        "image": "http://cdn.example.com/s24791.png",
        "subtext": "Baltimore Public Media",
        "URL": BASE + "Tune.ashx?id=s24791",
    }


def test_station_is_cached_after_the_first_lookup(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Describe.ashx", DESCRIBE)

    api.station("s24791")
    api.reload()  # Only clears the request cache, not the station cache.
    api._stations["s24791"] = {"guide_id": "s24791", "text": "From cache"}

    station = api.station("s24791")

    assert station is not None
    assert station["text"] == "From cache"


def test_unknown_station_is_none(api: tunein.TuneIn, httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Describe.ashx", [])

    assert api.station("s404") is None


def test_failed_station_lookup_is_not_cached(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Describe.ashx", [])

    api.station("s404")

    assert "s404" not in api._stations


def test_tune_returns_the_stream_urls_without_duplicates(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Tune.ashx", TUNE)

    assert api.tune({"guide_id": "s1"}) == [
        "http://stream.example.com/one",
        "http://stream.example.com/two",
    ]


def test_tune_prefers_mp3_then_the_higher_bitrate(httpx_mock: HTTPXMock) -> None:
    api = tunein.TuneIn(timeout=1000, formats=["mp3", "aac"])
    add_response(httpx_mock, "Tune.ashx", DUAL_FORMAT_TUNE)

    assert api.tune({"guide_id": "s1"}) == [
        "http://a/mp3-high",
        "http://a/mp3-low",
        "http://a/aac-high",
        "http://a/aac-low",
    ]


def test_tune_keeps_an_aac_only_station(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Tune.ashx", [DUAL_FORMAT_TUNE[0], DUAL_FORMAT_TUNE[3]])

    assert api.tune({"guide_id": "s1"}) == ["http://a/aac-high", "http://a/aac-low"]


def test_tune_drops_the_not_compatible_recording(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Tune.ashx", PLACEHOLDER_TUNE)

    assert api.tune({"guide_id": "s1"}) == ["http://a/real"]


def test_tune_puts_an_unknown_format_last(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(
        httpx_mock,
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


def test_formats_are_sent_with_browse_search_and_tune(httpx_mock: HTTPXMock) -> None:
    api = tunein.TuneIn(timeout=1000, formats=["mp3", "aac"])
    add_response(httpx_mock, "Browse.ashx", [])
    add_response(httpx_mock, "Search.ashx", [])
    add_response(httpx_mock, "Tune.ashx", [])

    api.stations("c1")
    api.search("bbc")
    api.tune({"guide_id": "s1"})

    assert all("formats=mp3,aac" in request_url(httpx_mock, i) for i in range(3))


def test_formats_are_not_sent_when_not_configured(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Browse.ashx", [])

    api.stations("c1")

    assert "formats=" not in request_url(httpx_mock)


def test_formats_are_not_sent_when_describing_a_station(httpx_mock: HTTPXMock) -> None:
    api = tunein.TuneIn(timeout=1000, formats=["mp3", "aac"])
    add_response(httpx_mock, "Describe.ashx", DESCRIBE)

    api.station("s24791")

    assert "formats=" not in request_url(httpx_mock)


def test_tune_drops_entries_without_a_url(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Tune.ashx", [{"element": "audio", "guide_id": "e1"}])

    assert api.tune({"guide_id": "s1"}) == []


def test_tune_logs_a_station_without_streams(
    api: tunein.TuneIn, caplog: pytest.LogCaptureFixture, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Tune.ashx", [])

    with caplog.at_level(logging.ERROR):
        api.tune({"guide_id": "s1"})

    assert "Failed to tune station id s1" in caplog.text


def test_search_keeps_only_stations(api: tunein.TuneIn, httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Search.ashx", SEARCH)

    result = api.search("bbc")

    assert [s["guide_id"] for s in result] == ["s128641", "s346757"]


def test_search_fills_the_station_cache(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    add_response(httpx_mock, "Search.ashx", SEARCH)

    api.search("bbc")

    assert set(api._stations) == {"s128641", "s346757"}


def test_search_empty_query_is_not_requested(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    assert api.search("") == []
    assert not httpx_mock.get_requests()


def test_search_filter_is_part_of_the_query(httpx_mock: HTTPXMock) -> None:
    add_response(httpx_mock, "Search.ashx", [])

    tunein.TuneIn(1000, "station").search("bbc")

    assert "filter=s" in request_url(httpx_mock)


@pytest.mark.parametrize("url", ["http://a/b.mp3", "http://a/b.wma"])
def test_parse_stream_url_uses_an_audio_extension_as_is(
    api: tunein.TuneIn, url: str, httpx_mock: HTTPXMock
) -> None:
    assert api.parse_stream_url(url) == [url]
    assert not httpx_mock.get_requests()


def test_parse_stream_url_parses_a_playlist(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/b.pls",
        content=b"[playlist]\nNumberOfEntries=1\nFile1=http://a/stream\n",
        headers={"content-type": "audio/x-scpls"},
    )

    assert api.parse_stream_url("http://a/b.pls") == ["http://a/stream"]


def test_parse_stream_url_uses_a_stream_as_is(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/stream", content=b"", headers={"content-type": "audio/mpeg"}
    )

    assert api.parse_stream_url("http://a/stream") == ["http://a/stream"]


def test_parse_stream_url_falls_back_to_the_content_type(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/listen",
        content=b"[playlist]\nNumberOfEntries=1\nFile1=http://a/stream\n",
        headers={"content-type": "audio/x-scpls; charset=UTF-8"},
    )

    assert api.parse_stream_url("http://a/listen") == ["http://a/stream"]


def test_parse_stream_url_gives_no_results_for_a_malformed_playlist(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/b.pls",
        content=b"not a playlist",
        headers={"content-type": "audio/x-scpls"},
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

    def iter_bytes(self, chunk_size: int) -> Generator[bytes]:
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


def test_get_playlist_skips_an_audio_body(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/s", content=b"audio", headers={"content-type": "audio/mpeg"}
    )

    assert api._get_playlist("http://a/s") == (None, "audio/mpeg")


def test_get_playlist_skips_an_audio_body_with_a_charset(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/s",
        content=b"audio",
        headers={"content-type": "audio/mpeg; charset=UTF-8"},
    )

    result = api._get_playlist("http://a/s")

    assert result == (None, "audio/mpeg; charset=UTF-8")


def test_get_playlist_reads_a_playlist_body(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/p.pls",
        content=b"[playlist]",
        headers={"content-type": "audio/x-scpls"},
    )

    assert api._get_playlist("http://a/p.pls") == (b"[playlist]", "audio/x-scpls")


def test_get_playlist_failed_request_gives_nothing(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url="http://a/p.pls", status_code=404)

    assert api._get_playlist("http://a/p.pls") is None


def test_get_playlist_does_not_keep_a_failed_request(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url="http://a/p.pls", status_code=503)
    httpx_mock.add_response(
        url="http://a/p.pls",
        content=b"[playlist]",
        headers={"content-type": "audio/x-scpls"},
    )

    first = api._get_playlist("http://a/p.pls")
    second = api._get_playlist("http://a/p.pls")

    assert first is None
    assert second == (b"[playlist]", "audio/x-scpls")


def test_get_playlist_keeps_a_result_that_worked(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/p.pls",
        content=b"[playlist]",
        headers={"content-type": "audio/x-scpls"},
    )

    api._get_playlist("http://a/p.pls")
    api._get_playlist("http://a/p.pls")

    assert len(httpx_mock.get_requests()) == 1


def test_parse_stream_url_after_a_failed_request(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url="http://a/p.pls", status_code=503)
    httpx_mock.add_response(
        url="http://a/p.pls",
        content=b"[playlist]\nNumberOfEntries=1\nFile1=http://a/stream\n",
        headers={"content-type": "audio/x-scpls"},
    )

    assert api.parse_stream_url("http://a/p.pls") == []
    assert api.parse_stream_url("http://a/p.pls") == ["http://a/stream"]


def test_get_playlist_body_over_the_size_limit_is_not_a_playlist(
    api: tunein.TuneIn, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    monkeypatch.setattr(tunein, "PLAYLIST_MAX_BYTES", 1024)
    httpx_mock.add_response(
        url="http://a/stream",
        content=b"x" * 4096,
        headers={"content-type": "audio/aac"},
    )

    assert api._get_playlist("http://a/stream") == (None, "audio/aac")


def test_get_playlist_body_under_the_size_limit_is_a_playlist(
    api: tunein.TuneIn, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://a/p.pls",
        content=b"[playlist]\nFile1=http://a/s\n",
        headers={"content-type": "audio/x-scpls"},
    )

    result = api._get_playlist("http://a/p.pls")

    assert result is not None
    assert result[0] == b"[playlist]\nFile1=http://a/s\n"
