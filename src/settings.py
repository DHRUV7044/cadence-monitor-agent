import os
from pathlib import Path
from typing import Tuple


PROJECT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DATA_DIR = PROJECT_DIR / "data"
DEFAULT_STATUS_JSON = DEFAULT_DATA_DIR / "status.json"
DEFAULT_PAGES_REPO = Path("/home/u24ev057/some_github_things/cadence-monitor")
DEFAULT_PAGES_STATUS_JSON = Path("data/status.json")
DEFAULT_CDS_LOG_PATH = Path.home() / "CDS.log"
DEFAULT_GIT_PATH = "/home/u24ev057/local/bin/git" #this is for vlsi lab server account path change it with path in your machine you want to run script on
DEFAULT_GIT_AUTHOR_NAME = "dhruv7044"
DEFAULT_GIT_AUTHOR_EMAIL = "dhruve.shingala@gmail.com"
DEFAULT_VIRTUOSO_LICENSE_SUCCESS_PATTERNS = (
    "Virtuoso Framework License (111) was checked out successfully",
    "License checkout succeeded",
    "Checkout succeeded",
    "license acquired",
    "license granted",
    r"virtuoso.*licen[cs]e.*was\s+checked\s+out\s+successfully",
    r"licen[cs]e.*was\s+checked\s+out\s+successfully",
)
DEFAULT_VIRTUOSO_FAILURE_PATTERNS = (
    "License checkout failed",
    "Unable to obtain license",
    "No such feature exists",
    "Cannot connect to license server",
    "License server machine is down",
    r"licen[cs]e.*unable.*check(?:ed)?\s*out",
    r"unable.*check(?:ed)?\s*out.*licen[cs]e",
    r"licen[cs]e.*check(?:ed)?\s*out.*fail(?:ed|ure)?",
)


def _path_from_env(name, default):
    return Path(os.getenv(name, str(default))).expanduser().resolve()


def _relative_path_from_env(name, default):
    value = Path(os.getenv(name, str(default))).expanduser()
    if value.is_absolute():
        raise ValueError(f"{name} must be relative to the GitHub Pages repository")
    return value


def _int_from_env(name, default):
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


def _patterns_from_env(name, defaults):
    # type: (str, Tuple[str, ...]) -> Tuple[str, ...]
    raw_value = os.getenv(name)
    if raw_value is None:
        return defaults

    patterns = tuple(pattern.strip() for pattern in raw_value.split("|") if pattern.strip())
    if not patterns:
        raise ValueError(f"{name} must contain at least one non-empty pattern")
    return patterns


class Settings:
    def __init__(
        self,
        cadence_shell_command,
        top_menu_name,
        virtuoso_menu_name,
        status_json,
        pages_repo,
        pages_status_json,
        cds_log_path,
        monitor_name,
        monitor_host,
        git_path,
        git_author_name,
        git_author_email,
        menu_timeout_seconds,
        launch_timeout_seconds,
        license_success_patterns,
        failure_patterns,
    ):
        self.cadence_shell_command = cadence_shell_command
        self.top_menu_name = top_menu_name
        self.virtuoso_menu_name = virtuoso_menu_name
        self.status_json = status_json
        self.pages_repo = pages_repo
        self.pages_status_json = pages_status_json
        self.cds_log_path = cds_log_path
        self.monitor_name = monitor_name
        self.monitor_host = monitor_host
        self.git_path = git_path
        self.git_author_name = git_author_name
        self.git_author_email = git_author_email
        self.menu_timeout_seconds = menu_timeout_seconds
        self.launch_timeout_seconds = launch_timeout_seconds
        self.license_success_patterns = license_success_patterns
        self.failure_patterns = failure_patterns

    @property
    def published_status_json(self):
        return self.pages_repo / self.pages_status_json


def load_settings():
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
        cds_log_path=_path_from_env("CDS_LOG_PATH", DEFAULT_CDS_LOG_PATH),
        monitor_name=os.getenv("MONITOR_NAME", "Cadence Status Monitor"),
        monitor_host=os.getenv("MONITOR_HOST", "Lab Monitor"),
        git_path=os.getenv("GIT_PATH", DEFAULT_GIT_PATH),
        git_author_name=os.getenv("GIT_AUTHOR_NAME", DEFAULT_GIT_AUTHOR_NAME),
        git_author_email=os.getenv("GIT_AUTHOR_EMAIL", DEFAULT_GIT_AUTHOR_EMAIL),
        menu_timeout_seconds=_int_from_env("MENU_TIMEOUT_SECONDS", 30),
        launch_timeout_seconds=_int_from_env("LAUNCH_TIMEOUT_SECONDS", 60),
        license_success_patterns=_patterns_from_env(
            "VIRTUOSO_LICENSE_SUCCESS_PATTERNS",
            DEFAULT_VIRTUOSO_LICENSE_SUCCESS_PATTERNS,
        ),
        failure_patterns=_patterns_from_env(
            "VIRTUOSO_FAILURE_PATTERNS",
            DEFAULT_VIRTUOSO_FAILURE_PATTERNS,
        ),
    )
