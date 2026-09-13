import pytest

from mopidy_tunein import tunein

ASX = b"""<ASX version="3.0">
  <TITLE>Example</TITLE>
  <ENTRY>
    <TITLE>Sample Title</TITLE>
    <REF href="file:///tmp/foo" />
  </ENTRY>
  <ENTRY>
    <TITLE>Example title</TITLE>
    <REF href="file:///tmp/bar" />
  </ENTRY>
  <ENTRY>
    <TITLE>Other title</TITLE>
    <REF href="file:///tmp/baz" />
  </ENTRY>
</ASX>
"""

SIMPLE_ASX = b"""<ASX version="3.0">
  <ENTRY href="file:///tmp/foo" />
  <ENTRY href="file:///tmp/bar" />
  <ENTRY href="file:///tmp/baz" />
</ASX>
"""

OLD_ASX = b"""[Reference]
Ref1=file:///tmp/foo
Ref2=file:///tmp/bar
Ref3=file:///tmp/baz
"""

ASF_ASX = b"""[Reference]
Ref1=http://tmp.com/foo-mbr?MSWMExt=.asf
Ref2=mms://tmp.com:80/bar-mbr?mswmext=.asf
Ref3=http://tmp.com/baz
"""


EXPECTED = ["file:///tmp/foo", "file:///tmp/bar", "file:///tmp/baz"]


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(ASX, id="asx"),
        pytest.param(SIMPLE_ASX, id="simple-asx"),
        pytest.param(OLD_ASX, id="old-asx"),
    ],
)
def test_parse_valid_playlist(data: bytes) -> None:
    assert list(tunein.parse_asx(data)) == EXPECTED


def test_parse_asf_playlist() -> None:
    assert list(tunein.parse_asx(ASF_ASX)) == [
        "mms://tmp.com/foo-mbr?mswmext=.asf",
        "mms://tmp.com:80/bar-mbr?mswmext=.asf",
        "http://tmp.com/baz",
    ]
