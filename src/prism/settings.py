"""Prism configuration via pydantic-settings.

Sources, highest precedence first:

1. Environment variables (e.g. ``IRIS_BASE_URL``)
2. ``.env`` in the current working directory (loaded into ``os.environ``)
3. ``config.json`` in the platform user data directory

User data directory (resolved via ``platformdirs.user_data_path("prism",
appauthor=False)``):

- Linux:   ``~/.local/share/prism/config.json`` (honours ``XDG_DATA_HOME``)
- macOS:   ``~/Library/Application Support/prism/config.json``
- Windows: ``%LOCALAPPDATA%\\prism\\config.json``

``appauthor=False`` keeps Windows from creating a ``prism\\prism`` nested folder.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from platformdirs import user_data_path
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

load_dotenv()


def config_path() -> Path:
    """Return the platform-appropriate ``config.json`` path."""
    return user_data_path("prism", appauthor=False) / "config.json"


class _TolerantJsonSource(JsonConfigSettingsSource):
    """JSON source that treats unreadable / malformed files as empty.

    A corrupt ``config.json`` should not lock the user out — fall back to
    env vars and field defaults instead of raising at import time.
    """

    def _read_file(self, file_path: Path) -> dict[str, Any]:
        try:
            return super()._read_file(file_path)
        except (OSError, json.JSONDecodeError):
            return {}


class Settings(BaseSettings):
    """Prism settings loaded from env vars, ``.env``, and ``config.json``."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # IRIS connection
    iris_base_url: str = "http://localhost:52773"
    iris_username: str = "_SYSTEM"
    iris_password: str = "SYS"
    iris_namespace: str = "USER"
    iris_workspace: str = ""
    iris_api_prefix: str = "api/atelier/v8"
    iris_compile_flags: str = "cuk"
    iris_superserver_port: int = 1972
    iris_terminal_method: str = "native"
    iris_terminal_max_output_chars: int = 100_000

    # Testing
    iris_test_runner_class: str = "MCP.TestRunner"
    iris_test_runner_method: str = "RunTests"
    iris_test_manager_class: str = "%UnitTest.Manager"
    iris_test_auto_deploy: bool = True

    # Output
    prism_output_format: str = "json"

    # Debugging
    iris_debug_enabled: bool = False
    iris_debug_step_granularity: str = "line"
    iris_debug_max_data: int = 8192
    iris_debug_max_children: int = 32
    iris_debug_max_depth: int = 2
    iris_debug_idle_timeout: int = 300

    # Chatbot agent
    chatbot_api_url: str = ""
    chatbot_api_key: str = ""
    chatbot_skills_path: str = ""
    chatbot_model: str = "gpt-4o"

    # GUI SQL editor
    gui_query_autosave: bool = True
    gui_autosave_delay_ms: int = 3000
    gui_saved_queries: str = "[]"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            _TolerantJsonSource(settings_cls, json_file=config_path()),
        )


settings = Settings()


def _read_existing(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
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


def save_config(updates: dict[str, Any]) -> Path:
    """Merge *updates* into ``config.json`` and atomically write it.

    Existing keys not in *updates* are preserved. Returns the resolved path.
    On POSIX the file is chmod 600 to protect the password.
    """
    path = config_path()
    merged = {**_read_existing(path), **updates}
    _write_atomic(path, merged)
    return path


def reset_keys(keys: list[str]) -> Path:
    """Remove *keys* from ``config.json`` so their defaults take over."""
    path = config_path()
    data = _read_existing(path)
    if not data:
        return path
    removed = False
    for key in keys:
        if key in data:
            del data[key]
            removed = True
    if removed:
        _write_atomic(path, data)
    return path


def clear_config() -> Path:
    """Delete ``config.json`` so all settings revert to env vars / defaults."""
    path = config_path()
    if path.is_file():
        path.unlink()
    return path
