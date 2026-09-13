from __future__ import annotations

import configparser
import io
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Generator, Iterable
from contextlib import closing
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

type TuneInItem = dict[str, Any]
"""One category, section, show, or station from the TuneIn API."""

type PlaylistParser = Callable[[bytes], Generator[str]]


class PlaylistError(Exception):
    pass


class cache:  # noqa: N801
    # TODO: merge this to util library (copied from mopidy-spotify)

    def __init__(self, ctl: int = 0, ttl: int = 3600) -> None:
        self.cache: dict[Any, tuple[Any, float]] = {}
        self.ctl = ctl
        self.ttl = ttl
        self._call_count = 0

    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, R]:
        def _memoized(*args: P.args, **kwargs: P.kwargs) -> R:
            now = time.time()
            key = (args, tuple(sorted(kwargs.items())))
            try:
                value, last_update = self.cache[key]
                age = now - last_update
                if self._call_count > self.ctl or age > self.ttl:
                    self._call_count = 0
                    raise AttributeError  # noqa: TRY301
                if self.ctl:
                    self._call_count += 1
            except (KeyError, AttributeError):
                value = func(*args, **kwargs)
                if value:
                    self.cache[key] = (value, now)
                return value
            except TypeError:
                return func(*args, **kwargs)
            else:
                return value

        return _memoized

    def clear(self) -> None:
        self.cache.clear()


def parse_m3u(data: bytes) -> Generator[str]:
    # Copied from mopidy.audio.playlists
    # Mopidy version expects a header but it's not always present
    for line in data.splitlines():
        if not line.strip() or line.startswith(b"#"):
            continue

        try:
            line = line.decode()
        except UnicodeDecodeError:
            continue

        yield line.strip()


def parse_pls(data: bytes) -> Generator[str]:
    # Copied from mopidy.audio.playlists
    try:
        cp = configparser.RawConfigParser(strict=False)
        cp.read_string(data.decode())
    except configparser.Error:
        return

    for section in cp.sections():
        if section.lower() != "playlist":
            continue
        for i in range(cp.getint(section, "numberofentries")):
            try:
                # TODO: Remove this horrible hack to avoid adverts
                if cp.has_option(section, f"length{i + 1}"):
                    if cp.get(section, f"length{i + 1}") == "-1":
                        yield cp.get(section, f"file{i + 1}").strip("\"'")
                else:
                    yield cp.get(section, f"file{i + 1}").strip("\"'")
            except configparser.NoOptionError:
                return


def fix_asf_uri(uri: str) -> str:
    return re.sub(r"http://(.+\?mswmext=\.asf)", r"mms://\1", uri, flags=re.IGNORECASE)


def parse_old_asx(data: bytes) -> Generator[str]:
    try:
        cp = configparser.RawConfigParser()
        cp.read_string(data.decode())
    except configparser.Error:
        return

    for section in cp.sections():
        if section.lower() != "reference":
            continue
        for option in cp.options(section):
            if option.lower().startswith("ref"):
                uri = cp.get(section, option).lower()
                yield fix_asf_uri(uri.strip())


def parse_new_asx(data: bytes) -> Generator[str]:
    # Copied from mopidy.audio.playlists
    element = None
    try:
        # Last element will be root.
        for _event, element in ET.iterparse(io.BytesIO(data)):
            element.tag = element.tag.lower()  # normalize
    except ET.ParseError:
        return
    if element is None:
        return

    for ref in element.findall("entry/ref[@href]"):
        yield fix_asf_uri(ref.get("href", "").strip())

    for entry in element.findall("entry[@href]"):
        yield fix_asf_uri(entry.get("href", "").strip())


def parse_asx(data: bytes) -> Generator[str]:
    if b"asx" in data[0:50].lower():
        return parse_new_asx(data)
    return parse_old_asx(data)


def find_playlist_parser(
    extension: str,
    content_type: str | None,
) -> PlaylistParser | None:
    extension_map: dict[str, PlaylistParser] = {
        ".asx": parse_asx,
        ".wax": parse_asx,
        ".m3u": parse_m3u,
        ".pls": parse_pls,
    }
    content_type_map: dict[str, PlaylistParser] = {
        "video/x-ms-asf": parse_asx,
        "application/x-mpegurl": parse_m3u,
        "audio/x-scpls": parse_pls,
    }

    parser = extension_map.get(extension)
    if not parser and content_type:
        # Annoying case where the url gave us no hints so try and work it out
        # from the header's content-type instead.
        # This might turn out to be server-specific...
        parser = content_type_map.get(content_type.lower())
    return parser


class TuneIn:
    """Wrapper for the TuneIn API."""

    ID_PROGRAM = "program"
    ID_STATION = "station"
    ID_GROUP = "group"
    ID_TOPIC = "topic"
    ID_CATEGORY = "category"
    ID_REGION = "region"
    ID_PODCAST = "podcast_category"
    ID_AFFILIATE = "affiliate"
    ID_STREAM = "stream"
    ID_UNKNOWN = "unknown"

    _tunein_cache = cache()
    _playlist_cache = cache()

    def __init__(
        self,
        timeout: int,
        filter_: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._base_uri = "https://opml.radiotime.com/%s"
        self._session = session or requests.Session()
        self._timeout = timeout / 1000.0
        if filter_ in [TuneIn.ID_PROGRAM, TuneIn.ID_STATION]:
            self._filter = f"&filter={filter_[0]}"
        else:
            self._filter = ""
        self._stations: dict[str, TuneInItem] = {}

    def reload(self) -> None:
        self._stations.clear()
        self._tunein_cache.clear()
        self._playlist_cache.clear()

    def _flatten(self, data: Iterable[TuneInItem]) -> list[TuneInItem]:
        results = []
        for item in data:
            if "children" in item:
                results.extend(item["children"])
            else:
                results.append(item)
        return results

    def _filter_results(
        self,
        data: Iterable[TuneInItem],
        section_name: str | None = None,
        map_func: Callable[[TuneInItem], TuneInItem] | None = None,
    ) -> list[TuneInItem]:
        results: list[TuneInItem] = []

        def grab_item(item: TuneInItem) -> None:
            if "guide_id" not in item:
                return
            if map_func:
                station = map_func(item)
            elif item.get("type", "link") == "link":
                results.append(item)
                return
            else:
                station = item
            self._stations[station["guide_id"]] = station
            results.append(station)

        for item in data:
            if section_name is not None:
                section_key = item.get("key", "").lower()
                if section_key.startswith(section_name.lower()):
                    for child in item["children"]:
                        grab_item(child)
            else:
                grab_item(item)
        return results

    def categories(self, category: str = "") -> list[TuneInItem]:
        if category == "location":
            args = "&id=r0"  # Annoying special case
        elif category == "language":
            args = "&c=lang"
            return []  # TuneIn's API is a mess here, cba
        else:
            args = "&c=" + category

        # Take a copy so we don't modify the cached data
        results = list(self._tunein("Browse.ashx", args))
        if category in ("podcast", "local"):
            # Flatten the results!
            results = self._filter_results(self._flatten(results))
        elif category == "":
            trending: TuneInItem = {
                "text": "Trending",
                "key": "trending",
                "type": "link",
                "URL": self._base_uri % "Browse.ashx?c=trending",
            }
            # Filter out the language root category for now
            results = [x for x in results if x["key"] != "language"]
            results.append(trending)
        else:
            results = self._filter_results(results)
        return results

    def locations(self, location: str) -> list[TuneInItem]:
        args = "&id=" + location
        results = self._tunein("Browse.ashx", args)
        # TODO: Support filters here
        return [x for x in results if x.get("type", "") == "link"]

    def _browse(self, section_name: str, guide_id: str) -> list[TuneInItem]:
        args = "&id=" + guide_id
        results = self._tunein("Browse.ashx", args)
        return self._filter_results(results, section_name)

    def featured(self, guide_id: str) -> list[TuneInItem]:
        return self._browse("Featured", guide_id)

    def local(self, guide_id: str) -> list[TuneInItem]:
        return self._browse("Local", guide_id)

    def stations(self, guide_id: str) -> list[TuneInItem]:
        return self._browse("Station", guide_id)

    def related(self, guide_id: str) -> list[TuneInItem]:
        return self._browse("Related", guide_id)

    def shows(self, guide_id: str) -> list[TuneInItem]:
        return self._browse("Show", guide_id)

    def episodes(self, guide_id: str) -> list[TuneInItem]:
        args = f"&c=pbrowse&id={guide_id}"
        results = self._tunein("Tune.ashx", args)
        return self._filter_results(results, "Topic")

    def _map_listing(self, listing: TuneInItem) -> TuneInItem:
        # We've already checked 'guide_id' exists
        url_args = f"Tune.ashx?id={listing['guide_id']}"
        return {
            "text": listing.get("name", "???"),
            "guide_id": listing["guide_id"],
            "type": "audio",
            "image": listing.get("logo", ""),
            "subtext": listing.get("slogan", ""),
            "URL": self._base_uri % url_args,
        }

    def _station_info(self, station_id: str) -> TuneInItem | None:
        logger.debug(f"Fetching info for station {station_id}")
        args = f"&c=composite&detail=listing&id={station_id}"
        results = self._tunein("Describe.ashx", args)
        listings = self._filter_results(results, "Listing", self._map_listing)
        if listings:
            return listings[0]
        return None

    def parse_stream_url(self, url: str) -> list[str]:
        logger.debug(f"Extracting URIs from {url!r}")
        extension = urlparse(url).path[-4:]
        if extension in [".mp3", ".wma"]:
            return [url]  # Catch these easy ones
        results: list[str] = []
        playlist_data, content_type = self._get_playlist(url)
        if playlist_data:
            parser = find_playlist_parser(extension, content_type)
            if parser:
                try:
                    results = [u for u in parser(playlist_data) if u and u != url]
                except Exception as e:
                    logger.error(f"TuneIn playlist parsing failed {e}")
                if not results:
                    playlist_str = playlist_data.decode(errors="ignore")
                    logger.debug(f"Parsing failure, malformed playlist: {playlist_str}")
        elif content_type:
            results = [url]
        logger.debug(f"Got {results}")
        return list(OrderedDict.fromkeys(results))

    def tune(self, station: TuneInItem) -> list[str]:
        logger.debug(f"Tuning station id {station['guide_id']}")
        args = f"&id={station['guide_id']}"
        stream_uris: list[str] = [
            stream["url"]
            for stream in self._tunein("Tune.ashx", args)
            if "url" in stream
        ]
        if not stream_uris:
            logger.error(f"Failed to tune station id {station['guide_id']}")
        return list(OrderedDict.fromkeys(stream_uris))

    def station(self, station_id: str) -> TuneInItem | None:
        if station_id in self._stations:
            return self._stations[station_id]
        station = self._station_info(station_id)
        if station:
            self._stations[station_id] = station
        return station

    def search(self, query: str) -> list[TuneInItem]:
        if not query:
            logger.debug("Empty search query")
            return []
        logger.debug(f"Searching TuneIn for '{query}'")
        args = f"&query={query}{self._filter}"
        search_results = self._tunein("Search.ashx", args)
        # Only return stations
        results = [
            item
            for item in self._flatten(search_results)
            if item.get("type", "") == "audio"
        ]
        for item in results:
            self._stations[item["guide_id"]] = item
        return results

    @_tunein_cache
    def _tunein(self, variant: str, args: str) -> list[TuneInItem]:
        uri = (self._base_uri % variant) + f"?render=json{args}"
        logger.debug(f"TuneIn request: {uri!r}")
        try:
            with closing(self._session.get(uri, timeout=self._timeout)) as r:
                r.raise_for_status()
                return r.json()["body"]
        except Exception as e:
            logger.info(f"TuneIn API request for {variant} failed: {e}")
        return []

    @_playlist_cache
    def _get_playlist(self, uri: str) -> tuple[bytes | None, str | None]:
        data, content_type = None, None
        try:
            # Defer downloading the body until know it's not a stream
            with closing(
                self._session.get(uri, timeout=self._timeout, stream=True)
            ) as r:
                r.raise_for_status()
                content_type = r.headers.get("content-type", "audio/mpeg")
                logger.debug(f"{uri} has content-type: {content_type}")
                if content_type != "audio/mpeg":
                    data = r.content
        except Exception as e:
            logger.info(f"TuneIn playlist request for {uri} failed: {e}")
        return (data, content_type)
