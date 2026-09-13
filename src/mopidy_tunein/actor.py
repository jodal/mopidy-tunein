from __future__ import annotations

import logging
import time
import urllib.parse
from typing import TYPE_CHECKING, ClassVar, override

import pykka
from mopidy import backend, exceptions
from mopidy.audio import scan
from mopidy.models import Ref, SearchResult
from mopidy.types import Uri, UriScheme

from mopidy_tunein import Extension, http, parsers, translator, tunein

if TYPE_CHECKING:
    from collections.abc import Iterable

    import requests
    from mopidy.audio import AudioProxy
    from mopidy.config import Config, ProxyConfig
    from mopidy.models import Image, Track
    from mopidy.types import Query, SearchField

logger = logging.getLogger(__name__)


def get_requests_session(proxy_config: ProxyConfig) -> requests.Session:
    user_agent = f"{Extension.dist_name}/{Extension.version}"
    return http.get_requests_session(proxy_config=proxy_config, user_agent=user_agent)


class TuneInBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes: ClassVar[list[UriScheme]] = [UriScheme("tunein")]

    def __init__(self, config: Config, audio: AudioProxy) -> None:
        super().__init__()

        self._session = get_requests_session(config["proxy"])
        self._timeout = config["tunein"]["timeout"]
        self._filter = config["tunein"]["filter"]

        self._scanner = scan.Scanner(
            timeout=config["tunein"]["timeout"], proxy_config=config["proxy"]
        )
        self.tunein = tunein.TuneIn(
            timeout=config["tunein"]["timeout"],
            filter_=config["tunein"]["filter"],
            formats=config["tunein"]["formats"],
            session=self._session,
        )
        self.library = TuneInLibrary(self)
        self.playback = TuneInPlayback(audio=audio, backend=self)


class TuneInLibrary(backend.LibraryProvider):
    backend: TuneInBackend
    root_directory = Ref.directory(uri=Uri("tunein:root"), name="TuneIn")

    def __init__(self, backend: TuneInBackend) -> None:
        super().__init__(backend)

    @override
    def browse(self, uri: Uri) -> list[Ref]:
        result: list[Ref] = []
        variant, identifier = translator.parse_uri(uri)
        logger.debug(f"Browsing {uri!r}")
        if variant == "root":
            result.extend(
                translator.category_to_ref(category)
                for category in self.backend.tunein.categories()
            )
        elif variant == "category" and identifier:
            result.extend(
                translator.section_to_ref(section, identifier)
                for section in self.backend.tunein.categories(identifier)
            )
        elif variant == "location" and identifier:
            result.extend(
                translator.section_to_ref(location, "local")
                for location in self.backend.tunein.locations(identifier)
            )
            result.extend(
                translator.station_to_ref(station)
                for station in self.backend.tunein.stations(identifier)
            )
        elif variant == "section" and identifier:
            if self.backend.tunein.related(identifier):
                result.append(
                    Ref.directory(
                        uri=Uri(f"tunein:related:{identifier}"), name="Related"
                    )
                )
            if self.backend.tunein.shows(identifier):
                result.append(
                    Ref.directory(uri=Uri(f"tunein:shows:{identifier}"), name="Shows")
                )
            result.extend(
                translator.section_to_ref(station)
                for station in self.backend.tunein.featured(identifier)
            )
            result.extend(
                translator.station_to_ref(station)
                for station in self.backend.tunein.local(identifier)
            )
            result.extend(
                translator.station_to_ref(station)
                for station in self.backend.tunein.stations(identifier)
            )
        elif variant == "related" and identifier:
            result.extend(
                translator.section_to_ref(section)
                for section in self.backend.tunein.related(identifier)
            )
        elif variant == "shows" and identifier:
            result.extend(
                translator.show_to_ref(show)
                for show in self.backend.tunein.shows(identifier)
            )
        elif variant == "episodes" and identifier:
            result.extend(
                translator.station_to_ref(episode)
                for episode in self.backend.tunein.episodes(identifier)
            )
        else:
            logger.debug(f"Unknown URI: {uri!r}")

        return result

    @override
    def refresh(self, uri: Uri | None = None) -> None:
        self.backend.tunein.reload()

    @override
    def lookup(self, uri: Uri) -> list[Track]:
        variant, identifier = translator.parse_uri(uri)
        if variant != "station" or identifier is None:
            return []
        station = self.backend.tunein.station(identifier)
        if not station:
            return []

        track = translator.station_to_track(station)
        return [track]

    @override
    def get_images(self, uris: Iterable[Uri]) -> dict[Uri, list[Image]]:
        results: dict[Uri, list[Image]] = {}
        for uri in uris:
            variant, identifier = translator.parse_uri(uri)
            if variant != "station" or identifier is None:
                continue
            station = self.backend.tunein.station(identifier)
            image = translator.station_to_image(station)
            if image is not None:
                results[uri] = [image]
        return results

    @override
    def search(
        self,
        query: Query[SearchField] | None = None,
        uris: Iterable[Uri] | None = None,
        exact: bool = False,
    ) -> SearchResult | None:
        if query is None or not query:
            return None
        tunein_query = translator.mopidy_to_tunein_query(query)
        tracks = [
            translator.station_to_track(station)
            for station in self.backend.tunein.search(tunein_query)
        ]
        return SearchResult(uri=Uri("tunein:search"), tracks=tuple(tracks))


class TuneInPlayback(backend.PlaybackProvider):
    backend: TuneInBackend

    def __init__(self, audio: AudioProxy, backend: TuneInBackend) -> None:
        super().__init__(audio, backend)
        self._stream_info: scan._Result | None = None

    @override
    def translate_uri(self, uri: Uri) -> Uri | None:
        _variant, identifier = translator.parse_uri(uri)
        if identifier is None:
            return None
        station = self.backend.tunein.station(identifier)
        if not station:
            return None
        stream_uris = self.backend.tunein.tune(station)
        while stream_uris:
            stream_uri = Uri(stream_uris.pop(0))
            logger.debug(f"Looking up URI: {stream_uri!r}")
            new_uri = self.unwrap_stream(stream_uri)
            if new_uri:
                return new_uri
            logger.debug("Mopidy translate_uri failed.")
            new_uris = self.backend.tunein.parse_stream_url(stream_uri)
            if new_uris == [stream_uri]:
                logger.debug(f"Last attempt, play stream anyway: {stream_uri!r}")
                return stream_uri
            stream_uris.extend(new_uris)
        logger.debug("TuneIn lookup failed.")
        return None

    def unwrap_stream(self, uri: Uri) -> Uri | None:
        unwrapped_uri, self._stream_info = _unwrap_stream(
            uri,
            timeout=self.backend._timeout,
            scanner=self.backend._scanner,
            requests_session=self.backend._session,
        )
        return unwrapped_uri

    @override
    def is_live(self, uri: Uri) -> bool:
        return (
            self._stream_info is not None
            and self._stream_info.uri == uri
            and self._stream_info.playable
            and not self._stream_info.seekable
        )


# Shamelessly taken from mopidy.stream.actor
def _unwrap_stream(  # noqa: PLR0911
    uri: Uri,
    timeout: int,
    scanner: scan.Scanner,
    requests_session: requests.Session,
) -> tuple[Uri | None, scan._Result | None]:
    """
    Get a stream URI from a playlist URI, ``uri``.

    Unwraps nested playlists until something that's not a playlist is found or
    the ``timeout`` is reached.
    """

    original_uri = uri
    seen_uris: set[Uri] = set()
    deadline = time.time() + timeout

    while time.time() < deadline:
        if uri in seen_uris:
            logger.info(
                f"Unwrapping stream from URI ({uri!r}) failed: "
                "playlist referenced itself",
            )
            return None, None
        seen_uris.add(uri)

        logger.debug(f"Unwrapping stream from URI: {uri!r}")

        try:
            scan_timeout = deadline - time.time()
            if scan_timeout < 0:
                logger.info(
                    f"Unwrapping stream from URI ({uri!r}) failed: "
                    f"timed out in {timeout}ms",
                )
                return None, None
            scan_result = scanner.scan(uri, timeout=scan_timeout)
        except exceptions.ScannerError as exc:
            logger.debug(f"GStreamer failed scanning URI ({uri!r}): {exc}")
            scan_result = None

        if scan_result is not None:
            has_interesting_mime = (
                scan_result.mime is not None
                and not scan_result.mime.startswith("text/")
                and not scan_result.mime.startswith("application/")
            )
            if scan_result.playable or has_interesting_mime:
                logger.debug(f"Unwrapped potential {scan_result.mime} stream: {uri!r}")
                return uri, scan_result

        download_timeout = deadline - time.time()
        if download_timeout < 0:
            logger.info(
                f"Unwrapping stream from URI ({uri!r}) failed: timed out in {timeout}ms"
            )
            return None, None
        content = http.download(requests_session, uri, timeout=download_timeout / 1000)

        if content is None:
            logger.info(
                f"Unwrapping stream from URI ({original_uri!r}) failed: "
                f"error downloading URI {uri!r}",
            )
            return None, None

        uris = parsers.parse_playlist(content)
        if not uris:
            logger.debug(
                f"Failed parsing URI ({uri!r}) as playlist; found potential stream.",
            )
            return uri, None

        # TODO: Test streams and return first that seems to be playable
        logger.debug(f"Parsed playlist ({uri!r}) and found new URI: {uris[0]!r}")
        uri = Uri(urllib.parse.urljoin(uri, uris[0]))

    return None, None
