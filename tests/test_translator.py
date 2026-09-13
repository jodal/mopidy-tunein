from __future__ import annotations

import pytest

from mopidy_tunein import translator


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (
            "http://cdn-profiles.tunein.com/s1/images/logoq.jpg",
            "https://cdn-profiles.tunein.com/s1/images/logoq.jpg",
        ),
        (
            "http://cdn-radiotime-logos.tunein.com/s1q.png",
            "https://cdn-radiotime-logos.tunein.com/s1q.png",
        ),
        ("http://tunein.com/logo.png", "https://tunein.com/logo.png"),
        # Keep the query and the port.
        (
            "http://cdn-profiles.tunein.com:80/s1.png?t=2",
            "https://cdn-profiles.tunein.com:80/s1.png?t=2",
        ),
        # Leave what is already secure, and what is not TuneIn's, alone.
        (
            "https://cdn-profiles.tunein.com/s1.png",
            "https://cdn-profiles.tunein.com/s1.png",
        ),
        ("http://example.com/s1.png", "http://example.com/s1.png"),
        ("http://nottunein.com/s1.png", "http://nottunein.com/s1.png"),
        (
            "http://tunein.com.evil.example/s1.png",
            "http://tunein.com.evil.example/s1.png",
        ),
    ],
)
def test_secure_image_uri(uri: str, expected: str) -> None:
    assert translator.secure_image_uri(uri) == expected


def test_unparse_page_uri() -> None:
    assert translator.unparse_page_uri("c57943", 26) == "tunein:stations:c57943_26"


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("c57943_26", ("c57943", 26)),
        ("c57943", ("c57943", 0)),
        ("c57943_", ("c57943", 0)),
        ("c57943_lots", ("c57943", 0)),
    ],
)
def test_parse_page(identifier: str, expected: tuple[str, int]) -> None:
    assert translator.parse_page(identifier) == expected


def test_a_page_uri_can_be_parsed_back() -> None:
    uri = translator.unparse_page_uri("c57943", 26)

    variant, identifier = translator.parse_uri(uri)

    assert variant == "stations"
    assert identifier is not None
    assert translator.parse_page(identifier) == ("c57943", 26)


def test_station_to_image_uses_https() -> None:
    station = {"image": "http://cdn-profiles.tunein.com/s1/images/logoq.jpg"}

    image = translator.station_to_image(station)

    assert image is not None
    assert image.uri == "https://cdn-profiles.tunein.com/s1/images/logoq.jpg"


def test_station_to_image_without_an_image() -> None:
    assert translator.station_to_image({"guide_id": "s1"}) is None
    assert translator.station_to_image(None) is None
