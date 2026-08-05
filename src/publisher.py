from __future__ import annotations

import filecmp
import logging
import shutil
import subprocess
from pathlib import Path

from settings import Settings


LOGGER = logging.getLogger(__name__)


def publish_status(settings: Settings) -> bool:
    source = settings.status_json
    destination = settings.published_status_json

    if not source.exists():
        raise FileNotFoundError(f"Status file does not exist: {source}")
    if not settings.pages_repo.exists():
        raise FileNotFoundError(f"GitHub Pages repository does not exist: {settings.pages_repo}")
    if not (settings.pages_repo / ".git").exists():
        raise FileNotFoundError(f"Not a git repository: {settings.pages_repo}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    same_file = source.resolve() == destination.resolve()

    if not same_file and destination.exists() and filecmp.cmp(source, destination, shallow=False):
        LOGGER.info("Published status file is unchanged")
        return False

    if not same_file:
        shutil.copy2(source, destination)

    if not _git_has_changes(settings.pages_repo, destination):
        LOGGER.info("No git changes after copying status file")
        return False

    _run_git(settings.pages_repo, "add", str(destination.relative_to(settings.pages_repo)))
    _run_git(settings.pages_repo, "commit", "-m", "Update Cadence status")
    _run_git(settings.pages_repo, "push")
    return True


def _git_has_changes(repo_path: Path, file_path: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", str(file_path.relative_to(repo_path))],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _run_git(repo_path: Path, *args: str) -> None:
    command = ["git", *args]
    LOGGER.info("Running: %s", " ".join(command))
    subprocess.run(command, cwd=repo_path, check=True)
