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


def test_station_to_image_uses_https() -> None:
    station = {"image": "http://cdn-profiles.tunein.com/s1/images/logoq.jpg"}

    image = translator.station_to_image(station)

    assert image is not None
    assert image.uri == "https://cdn-profiles.tunein.com/s1/images/logoq.jpg"


def test_station_to_image_without_an_image() -> None:
    assert translator.station_to_image({"guide_id": "s1"}) is None
    assert translator.station_to_image(None) is None
