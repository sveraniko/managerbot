import importlib.util


def test_app_bootstrap_module_exists() -> None:
    # environment-safe smoke: validates bootstrap entrypoint file is present even when deps are unavailable.
    assert importlib.util.find_spec("app.main") is not None
