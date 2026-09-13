import pathlib
from importlib.metadata import version
from typing import override

from mopidy import config, ext

__version__ = version("mopidy-tunein")


class Extension(ext.Extension):
    dist_name = "mopidy-tunein"
    ext_name = "tunein"
    version = __version__

    @override
    def get_default_config(self) -> str:
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    @override
    def get_config_schema(self) -> config.ConfigSchema:
        schema = super().get_config_schema()
        schema["timeout"] = config.Integer(minimum=0)
        schema["filter"] = config.String(optional=True, choices=("station", "program"))
        schema["formats"] = config.List(optional=True)
        schema["location"] = config.String(optional=True)
        return schema

    @override
    def setup(self, registry: ext.Registry) -> None:
        from .actor import TuneInBackend  # noqa: PLC0415

        registry.add("backend", TuneInBackend)
