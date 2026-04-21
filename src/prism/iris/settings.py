"""User settings stored in the platform-standard user config directory.

Settings.json has the lowest precedence — env vars and .env override it.
Resolved path (via platformdirs):
- Linux:   ``~/.config/prism/settings.json`` (honors ``XDG_CONFIG_HOME``)
- Windows: ``%LOCALAPPDATA%/prism/settings.json``
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from platformdirs import user_config_path

SETTING_TO_ENV: dict[str, str] = {
    "url": "IRIS_BASE_URL",
    "username": "IRIS_USERNAME",
    "password": "IRIS_PASSWORD",
    "namespace": "IRIS_NAMESPACE",
    "superserver_port": "IRIS_SUPERSERVER_PORT",
}


def settings_path() -> Path:
    """Return the platform-appropriate settings.json path."""
    return user_config_path("prism") / "settings.json"


def load_settings() -> dict[str, Any]:
    """Load settings.json. Returns ``{}`` if missing, unreadable, or malformed."""
    path = settings_path()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: dict[str, Any]) -> Path:
    """Atomically write settings.json, chmod 600 on POSIX. Returns the path."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)
    if os.name == "posix":
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return path


def inject_settings() -> None:
    """Populate os.environ from settings.json without overwriting existing vars.

    Ensures precedence: real env > .env (via python-dotenv) > settings.json.
    """
    data = load_settings()
    if not data:
        return
    for key, env_name in SETTING_TO_ENV.items():
        if env_name in os.environ:
            continue
        value = data.get(key)
        if value is None:
            continue
        os.environ[env_name] = str(value)
