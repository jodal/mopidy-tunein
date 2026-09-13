# mopidy-tunein

[![Latest PyPI version](https://img.shields.io/pypi/v/mopidy-tunein)](https://pypi.org/p/mopidy-tunein)
[![CI build status](https://img.shields.io/github/actions/workflow/status/mopidy/mopidy-tunein/ci.yml)](https://github.com/mopidy/mopidy-tunein/actions/workflows/ci.yml)
[![Test coverage](https://img.shields.io/codecov/c/gh/mopidy/mopidy-tunein)](https://codecov.io/gh/mopidy/mopidy-tunein)

[Mopidy](https://mopidy.com/) extension for playing music from
[TuneIn](https://tunein.com). Listen to the world's radio with 70,000 stations
of music, sports and news streaming from every continent.

Acknowledgement and thanks to Marius Wyss for his original version of this
extension, and to Brian Hornsby's [XBMC
plugin](https://github.com/brianhornsby/plugin.audio.tuneinradio) that it was
based on.

This product uses TuneIn but is not endorsed, certified or otherwise approved
in any way by TuneIn. TuneIn is the registered trade mark of TuneIn Inc.

## Installation

Install by running:

```sh
python3 -m pip install mopidy-tunein
```

See https://mopidy.com/ext/tunein/ for alternative installation methods.

Some radio streams need additional audio plugins. You find these in the
GStreamer plugin packages for your system:

- `gstreamer1.0-plugins-ugly`
- `gstreamer1.0-plugins-bad`
- `gstreamer1.0-libav`

## Configuration

The extension is enabled by default when it is installed. Configuration is not
required, but you can add this to your Mopidy configuration file:

```ini
[tunein]
timeout = 5000
```

The following configuration values are available:

- `tunein/enabled`: If the TuneIn extension should be enabled or not. Defaults
  to `true`.
- `tunein/filter`: Limit the search results to `station` or `program`. Leave it
  blank to turn off filtering. Defaults to blank.
- `tunein/timeout`: Milliseconds before giving up waiting for results. Defaults
  to `5000`.

## Known issues

The following functionality is not implemented yet:

- Playback of podcasts and shows.
- User login and access to saved stations.

## Project resources

- [Source code](https://github.com/mopidy/mopidy-tunein)
- [Issues](https://github.com/mopidy/mopidy-tunein/issues)
- [Releases](https://github.com/mopidy/mopidy-tunein/releases)

## Development

### Set up development environment

Clone the repo using, e.g. using [gh](https://cli.github.com/):

```sh
gh repo clone mopidy/mopidy-tunein
```

Enter the directory, and install dependencies using [uv](https://docs.astral.sh/uv/):

```sh
cd mopidy-tunein/
uv sync
```

### Running tests

To run all tests and linters in isolated environments, use
[tox](https://tox.wiki/):

```sh
tox
```

To only run tests, use [pytest](https://pytest.org/):

```sh
pytest
```

To format the code, use [ruff](https://docs.astral.sh/ruff/):

```sh
ruff format .
```

To check for lints with ruff, run:

```sh
ruff check .
```

To check for type errors, use [pyright](https://microsoft.github.io/pyright/):

```sh
pyright .
```

### Making a release

To make a release to PyPI, go to the project's [GitHub releases
page](https://github.com/mopidy/mopidy-tunein/releases)
and click the "Draft a new release" button.

In the "choose a tag" dropdown, select the tag you want to release or create a
new tag, e.g. `v0.1.0`. Add a title, e.g. `v0.1.0`, and a description of the changes.

Decide if the release is a pre-release (alpha, beta, or release candidate) or
should be marked as the latest release, and click "Publish release".

Once the release is created, the `release.yml` GitHub Action will automatically
build and publish the release to
[PyPI](https://pypi.org/project/mopidy-tunein/).

## Credits

- Original author: [Nick Steel](https://github.com/kingosticks)
- Current maintainer: [Nick Steel](https://github.com/kingosticks)
- [Contributors](https://github.com/mopidy/mopidy-tunein/graphs/contributors)
