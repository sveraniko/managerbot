import importlib.util
import os

from app.config.settings import Settings


def test_app_bootstrap_module_exists() -> None:
    # environment-safe smoke: validates bootstrap entrypoint file is present even when deps are unavailable.
    assert importlib.util.find_spec("app.main") is not None


def test_settings_defaults_and_startup_logging_are_safe() -> None:
    os.environ["MANAGERBOT_BOT_TOKEN"] = "123456:TEST_TOKEN_FOR_SMOKE"
    os.environ["MANAGERBOT_CUSTOMER_BOT_TOKEN"] = "123456:TEST_TOKEN_FOR_SMOKE"
    from app.main import _log_startup_config

    settings = Settings(bot_token="123456:TEST_TOKEN_FOR_SMOKE", customer_bot_token="123456:TEST_TOKEN_FOR_SMOKE")
    assert settings.queue_page_size >= 1
    assert settings.notification_poll_seconds >= 1
    _log_startup_config(settings)
