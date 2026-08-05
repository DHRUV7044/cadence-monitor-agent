from __future__ import annotations

import logging
import os
import re
import signal
import shlex
import time
from dataclasses import dataclass

import pexpect

from settings import Settings


LOGGER = logging.getLogger(__name__)
MENU_ENTRY_RE = re.compile(r"^\s*(?P<choice>\d+)\s+(?P<label>.+?)\s*$")


@dataclass(frozen=True)
class CadenceCheckResult:
    online: bool
    message: str


class MenuSelectionError(RuntimeError):
    pass


def check_virtuoso_license(settings: Settings) -> CadenceCheckResult:
    child: pexpect.spawn | None = None

    try:
        command = shlex.split(settings.cadence_shell_command)
        if not command:
            raise ValueError("CADENCE_SHELL_COMMAND cannot be empty")

        LOGGER.info("Starting Cadence shell command: %s", settings.cadence_shell_command)
        child = pexpect.spawn(
            command[0],
            command[1:],
            encoding="utf-8",
            codec_errors="replace",
            timeout=1,
            preexec_fn=os.setsid,
        )

        _select_menu_entry(child, settings.top_menu_name, settings.menu_timeout_seconds)
        LOGGER.info("Selected top-level menu entry: %s", settings.top_menu_name)

        _select_menu_entry(child, settings.virtuoso_menu_name, settings.menu_timeout_seconds)
        LOGGER.info("Selected tool menu entry: %s", settings.virtuoso_menu_name)

        return _wait_for_virtuoso_startup(child, settings)
    except MenuSelectionError as exc:
        LOGGER.warning("Menu selection failed: %s", exc)
        return CadenceCheckResult(online=False, message=str(exc))
    except pexpect.ExceptionPexpect as exc:
        LOGGER.exception("Cadence terminal automation failed")
        return CadenceCheckResult(online=False, message=f"Cadence automation failed: {exc}")
    except Exception as exc:
        LOGGER.exception("Unexpected Virtuoso check failure")
        return CadenceCheckResult(online=False, message=f"Virtuoso check failed: {exc}")
    finally:
        if child is not None:
            _terminate_process(child)


def _select_menu_entry(child: pexpect.spawn, menu_name: str, timeout_seconds: int) -> None:
    menu_output = _read_until_menu_entry(child, menu_name, timeout_seconds)
    choice = _find_menu_choice(menu_output, menu_name)
    if choice is None:
        raise MenuSelectionError(f"Menu entry '{menu_name}' was not found")

    child.sendline(choice)


def _read_until_menu_entry(child: pexpect.spawn, menu_name: str, timeout_seconds: int) -> str:
    deadline = time.monotonic() + timeout_seconds
    output = ""

    while time.monotonic() < deadline:
        output += _read_available(child, timeout=1)
        if _find_menu_choice(output, menu_name) is not None:
            return output
        if not child.isalive():
            output += child.before or ""
            break

    raise MenuSelectionError(
        f"Timed out waiting for menu entry '{menu_name}'. Last output: {_compact_output(output)}"
    )


def _find_menu_choice(output: str, menu_name: str) -> str | None:
    expected = menu_name.casefold()
    for line in output.splitlines():
        match = MENU_ENTRY_RE.match(line)
        if match and match.group("label").strip().casefold() == expected:
            return match.group("choice")
    return None


def _wait_for_virtuoso_startup(
    child: pexpect.spawn,
    settings: Settings,
) -> CadenceCheckResult:
    deadline = time.monotonic() + settings.launch_timeout_seconds
    settle_deadline: float | None = None
    output = ""

    while time.monotonic() < deadline:
        chunk = _read_available(child, timeout=1)
        if chunk:
            output += chunk
            failure = _find_failure(output, settings.failure_patterns)
            if failure is not None:
                return CadenceCheckResult(online=False, message=f"Virtuoso failed: {failure}")

        if not child.isalive():
            output += child.before or ""
            failure = _find_failure(output, settings.failure_patterns)
            if failure is not None:
                return CadenceCheckResult(online=False, message=f"Virtuoso failed: {failure}")
            return CadenceCheckResult(online=False, message="Virtuoso exited before startup completed")

        if settle_deadline is None:
            settle_deadline = time.monotonic() + settings.successful_launch_settle_seconds
        elif time.monotonic() >= settle_deadline:
            return CadenceCheckResult(online=True, message="Virtuoso started successfully")

    failure = _find_failure(output, settings.failure_patterns)
    if failure is not None:
        return CadenceCheckResult(online=False, message=f"Virtuoso failed: {failure}")
    return CadenceCheckResult(online=False, message="Timed out waiting for Virtuoso startup")


def _find_failure(output: str, failure_patterns: tuple[str, ...]) -> str | None:
    normalized_output = output.casefold()
    for pattern in failure_patterns:
        if pattern.casefold() in normalized_output:
            return pattern
    return None


def _read_available(child: pexpect.spawn, timeout: int) -> str:
    try:
        return child.read_nonblocking(size=4096, timeout=timeout)
    except pexpect.TIMEOUT:
        return ""
    except pexpect.EOF:
        return child.before or ""


def _terminate_process(child: pexpect.spawn) -> None:
    if not child.isalive():
        return

    LOGGER.info("Terminating Cadence/Virtuoso process tree")
    child.sendcontrol("c")
    time.sleep(1)

    if child.isalive():
        _signal_process_group(child.pid, signal.SIGTERM)
        time.sleep(1)

    if child.isalive():
        _signal_process_group(child.pid, signal.SIGKILL)


def _signal_process_group(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except ProcessLookupError:
        return


def _compact_output(output: str, max_chars: int = 500) -> str:
    compacted = " ".join(output.split())
    if len(compacted) <= max_chars:
        return compacted
    return compacted[-max_chars:]
