import logging
import os
import re
import signal
import shlex
import subprocess
import time

import pexpect

from settings import Settings


LOGGER = logging.getLogger(__name__)
NUMBER_FIRST_MENU_ENTRY_RE = re.compile(r"^\s*(?P<choice>\d+)\s+(?P<label>.+?)\s*$")
LABEL_FIRST_MENU_ENTRY_RE = re.compile(r"^\s*(?P<label>.+?)\s*:\s*(?P<choice>\d+)\s*$")


class CadenceCheckResult:
    def __init__(self, online, message):
        # type: (bool, str) -> None
        self.online = online
        self.message = message


class MenuSelectionError(RuntimeError):
    pass


def check_virtuoso_license(settings):
    # type: (Settings) -> CadenceCheckResult
    child = None
    existing_virtuoso_pids = _current_virtuoso_pids()

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
        _terminate_new_virtuoso_processes(existing_virtuoso_pids)


def _select_menu_entry(child, menu_name, timeout_seconds):
    menu_output = _read_until_menu_entry(child, menu_name, timeout_seconds)
    choice = _find_menu_choice(menu_output, menu_name)
    if choice is None:
        raise MenuSelectionError(f"Menu entry '{menu_name}' was not found")

    child.sendline(choice)


def _read_until_menu_entry(child, menu_name, timeout_seconds):
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


def _find_menu_choice(output, menu_name):
    expected = menu_name.casefold()
    label_first_choice = _find_label_first_menu_choice(output, menu_name)
    if label_first_choice is not None:
        return label_first_choice

    for line in output.splitlines():
        entry = _parse_menu_entry(line)
        if entry is None:
            continue

        choice, label = entry
        if _normalize_menu_label(label) == expected:
            return choice
    return None


def _find_label_first_menu_choice(output, menu_name):
    menu_name_pattern = re.escape(menu_name).replace(r"\ ", r"[\s_]+")
    pattern = re.compile(
        r"(?:^|\s)(?:No\s+)?"
        + menu_name_pattern
        + r"[_\s]*:\s*(?P<choice>\d+)",
        re.IGNORECASE,
    )
    match = pattern.search(output)
    if match:
        return match.group("choice")
    return None


def _parse_menu_entry(line):
    for pattern in (NUMBER_FIRST_MENU_ENTRY_RE, LABEL_FIRST_MENU_ENTRY_RE):
        match = pattern.match(line)
        if match:
            return match.group("choice"), match.group("label")
    return None


def _normalize_menu_label(label):
    cleaned = label.replace("_", " ").strip()
    if cleaned.casefold().startswith("no "):
        cleaned = cleaned[3:].strip()
    return " ".join(cleaned.split()).casefold()


def _wait_for_virtuoso_startup(
    child,
    settings,
):
    deadline = time.monotonic() + settings.launch_timeout_seconds
    settle_deadline = None
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


def _find_failure(output, failure_patterns):
    normalized_output = output.casefold()
    for pattern in failure_patterns:
        if pattern.casefold() in normalized_output:
            return pattern
    return None


def _read_available(child, timeout):
    try:
        return child.read_nonblocking(size=4096, timeout=timeout)
    except pexpect.TIMEOUT:
        return ""
    except pexpect.EOF:
        return child.before or ""


def _terminate_process(child):
    if not child.isalive():
        return

    LOGGER.info("Terminating Cadence launcher process")
    child.sendcontrol("c")
    time.sleep(1)

    if child.isalive():
        child.terminate(force=False)
        time.sleep(1)

    if child.isalive():
        child.terminate(force=True)


def _terminate_new_virtuoso_processes(existing_pids):
    new_pids = _current_virtuoso_pids() - existing_pids
    if not new_pids:
        return

    LOGGER.info("Terminating new Virtuoso processes: %s", sorted(new_pids))
    _signal_processes(new_pids, signal.SIGTERM)
    time.sleep(2)

    still_running = _current_virtuoso_pids() & new_pids
    if still_running:
        LOGGER.warning("Force terminating Virtuoso processes: %s", sorted(still_running))
        _signal_processes(still_running, signal.SIGKILL)


def _current_virtuoso_pids():
    try:
        result = subprocess.run(
            ["ps", "-u", str(os.getuid()), "-o", "pid=,comm=,args="],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        LOGGER.warning("Could not inspect Virtuoso processes: %s", exc)
        return set()

    pids = set()
    for line in result.stdout.splitlines():
        parsed = _parse_process_line(line)
        if parsed is None:
            continue

        pid, command_text = parsed
        if pid != os.getpid() and "virtuoso" in command_text.casefold():
            pids.add(pid)

    return pids


def _parse_process_line(line):
    parts = line.strip().split(None, 2)
    if len(parts) < 2:
        return None

    try:
        pid = int(parts[0])
    except ValueError:
        return None

    command_text = " ".join(parts[1:])
    return pid, command_text


def _signal_processes(pids, sig):
    for pid in sorted(pids):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            LOGGER.warning("Could not terminate process %s: %s", pid, exc)


def _compact_output(output, max_chars=500):
    compacted = " ".join(output.split())
    if len(compacted) <= max_chars:
        return compacted
    return compacted[-max_chars:]
