from mopidy_tunein import Extension


def test_get_default_config() -> None:
    ext = Extension()

    config = ext.get_default_config()

    assert "[tunein]" in config
    assert "enabled = true" in config


def test_get_config_schema() -> None:
    ext = Extension()

    schema = ext.get_config_schema()

    assert "timeout" in schema
    assert "filter" in schema
