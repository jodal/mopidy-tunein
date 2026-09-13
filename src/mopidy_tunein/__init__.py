import pathlib
from importlib.metadata import version

from mopidy import config, ext

__version__ = version("mopidy-tunein")


class Extension(ext.Extension):

    dist_name = "mopidy-tunein"
    ext_name = "tunein"
    version = __version__

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()
        schema["timeout"] = config.Integer(minimum=0)
        schema["filter"] = config.String(
            optional=True, choices=("station", "program")
        )
        return schema

    def setup(self, registry):
        from .actor import TuneInBackend

        registry.add("backend", TuneInBackend)
