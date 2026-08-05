import filecmp
import logging
import shutil
import subprocess
from pathlib import Path

from settings import Settings


LOGGER = logging.getLogger(__name__)


def publish_status(settings):
    # type: (Settings) -> bool
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

    _run_git(settings, "add", str(destination.relative_to(settings.pages_repo)))
    _run_git(settings, "commit", "-m", "Update Cadence status")
    _run_git(settings, "push")
    return True


def _git_has_changes(repo_path, file_path):
    # type: (Path, Path) -> bool
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", str(file_path.relative_to(repo_path))],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _run_git(settings, *args):
    # type: (Settings, str) -> None
    command = [
        "git",
        "-c",
        "user.name={}".format(settings.git_author_name),
        "-c",
        "user.email={}".format(settings.git_author_email),
    ] + list(args)
    LOGGER.info("Running: %s", " ".join(command))
    subprocess.run(command, cwd=settings.pages_repo, check=True)
