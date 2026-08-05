from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DATA_DIR = PROJECT_DIR / "data"
DEFAULT_STATUS_JSON = DEFAULT_DATA_DIR / "status.json"
DEFAULT_PAGES_REPO = PROJECT_DIR
DEFAULT_PAGES_STATUS_JSON = Path("data/status.json")


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


def _relative_path_from_env(name: str, default: Path) -> Path:
    value = Path(os.getenv(name, str(default))).expanduser()
    if value.is_absolute():
        raise ValueError(f"{name} must be relative to the GitHub Pages repository")
    return value


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _patterns_from_env(name: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return defaults

    patterns = tuple(pattern.strip() for pattern in raw_value.split("|") if pattern.strip())
    if not patterns:
        raise ValueError(f"{name} must contain at least one non-empty pattern")
    return patterns


@dataclass(frozen=True)
class Settings:
    cadence_shell_command: str
    top_menu_name: str
    virtuoso_menu_name: str
    status_json: Path
    pages_repo: Path
    pages_status_json: Path
    monitor_name: str
    monitor_host: str
    menu_timeout_seconds: int
    launch_timeout_seconds: int
    successful_launch_settle_seconds: int
    failure_patterns: tuple[str, ...]

    @property
    def published_status_json(self) -> Path:
        return self.pages_repo / self.pages_status_json


def load_settings() -> Settings:
    return Settings(
        cadence_shell_command=os.getenv("CADENCE_SHELL_COMMAND", "csh"),
        top_menu_name=os.getenv("CADENCE_TOP_MENU_NAME", "Cadence"),
        virtuoso_menu_name=os.getenv("VIRTUOSO_MENU_NAME", "Virtuoso"),
        status_json=_path_from_env("STATUS_JSON", DEFAULT_STATUS_JSON),
        pages_repo=_path_from_env("PAGES_REPO", DEFAULT_PAGES_REPO),
        pages_status_json=_relative_path_from_env(
            "PAGES_STATUS_JSON",
            DEFAULT_PAGES_STATUS_JSON,
        ),
        monitor_name=os.getenv("MONITOR_NAME", "Cadence Status Monitor"),
        monitor_host=os.getenv("MONITOR_HOST", "Lab Monitor"),
        menu_timeout_seconds=_int_from_env("MENU_TIMEOUT_SECONDS", 30),
        launch_timeout_seconds=_int_from_env("LAUNCH_TIMEOUT_SECONDS", 60),
        successful_launch_settle_seconds=_int_from_env("SUCCESSFUL_LAUNCH_SETTLE_SECONDS", 10),
        failure_patterns=_patterns_from_env(
            "VIRTUOSO_FAILURE_PATTERNS",
            (
                "License checkout failed",
                "Unable to obtain license",
                "No such feature exists",
                "Cannot connect to license server",
                "License server machine is down",
            ),
        ),
    )
