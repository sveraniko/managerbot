from pathlib import Path

from app.config.settings import Settings


def test_env_example_covers_settings_contract() -> None:
    env_example_path = Path(__file__).resolve().parents[2] / ".env.example"
    assert env_example_path.exists(), ".env.example must exist at repository root"

    keys: set[str] = set()
    for raw_line in env_example_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())

    expected_keys = {
        f"MANAGERBOT_{field_name.upper()}" for field_name in Settings.model_fields.keys()
    }

    missing = expected_keys - keys
    assert not missing, f".env.example is missing settings keys: {sorted(missing)}"
