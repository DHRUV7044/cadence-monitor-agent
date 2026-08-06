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
    cds_log_position = _file_position(settings.cds_log_path)

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

        result = _wait_for_virtuoso_startup(child, settings, cds_log_position)
        return result
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
    cds_log_position,
):
    deadline = time.monotonic() + settings.launch_timeout_seconds
    output = ""
    cds_log_output = ""

    while time.monotonic() < deadline:
        chunk = _read_available(child, timeout=1)
        if chunk:
            output += chunk

        log_chunk, cds_log_position = _read_file_since(settings.cds_log_path, cds_log_position)
        if log_chunk:
            cds_log_output += log_chunk

        result = _check_license_output(output, "terminal output", settings)
        if result is not None:
            if result.online:
                result = _wait_for_virtuoso_stability(
                    child,
                    settings,
                    cds_log_position,
                    output,
                    cds_log_output,
                    result,
                )
            return result

        result = _check_license_output(cds_log_output, str(settings.cds_log_path), settings)
        if result is not None:
            if result.online:
                result = _wait_for_virtuoso_stability(
                    child,
                    settings,
                    cds_log_position,
                    output,
                    cds_log_output,
                    result,
                )
            return result

        if not child.isalive():
            output += child.before or ""
            log_chunk, cds_log_position = _read_file_since(settings.cds_log_path, cds_log_position)
            cds_log_output += log_chunk

            result = _check_license_output(output, "terminal output", settings)
            if result is not None:
                if result.online:
                    result = _wait_for_virtuoso_stability(
                        child,
                        settings,
                        cds_log_position,
                        output,
                        cds_log_output,
                        result,
                    )
                return result

            result = _check_license_output(cds_log_output, str(settings.cds_log_path), settings)
            if result is not None:
                if result.online:
                    result = _wait_for_virtuoso_stability(
                        child,
                        settings,
                        cds_log_position,
                        output,
                        cds_log_output,
                        result,
                    )
                return result

            LOGGER.warning(
                "Virtuoso exited before startup completed. Last terminal output: %s. Last CDS log output: %s",
                _compact_output(output),
                _compact_output(cds_log_output),
            )
            return CadenceCheckResult(online=False, message="Virtuoso exited before startup completed")

    log_chunk, cds_log_position = _read_file_since(settings.cds_log_path, cds_log_position)
    cds_log_output += log_chunk

    result = _check_license_output(output, "terminal output", settings)
    if result is not None:
        if result.online:
            result = _wait_for_virtuoso_stability(
                child,
                settings,
                cds_log_position,
                output,
                cds_log_output,
                result,
            )
        return result

    result = _check_license_output(cds_log_output, str(settings.cds_log_path), settings)
    if result is not None:
        if result.online:
            result = _wait_for_virtuoso_stability(
                child,
                settings,
                cds_log_position,
                output,
                cds_log_output,
                result,
            )
        return result

    LOGGER.warning(
        "Timed out waiting for Virtuoso license confirmation. Last terminal output: %s. Last CDS log output: %s",
        _compact_output(output),
        _compact_output(cds_log_output),
    )
    return CadenceCheckResult(
        online=False,
        message="Timed out waiting for Virtuoso license confirmation",
    )


def _wait_for_virtuoso_stability(
    child,
    settings,
    cds_log_position,
    output,
    cds_log_output,
    success_result,
):
    stability_deadline = time.monotonic() + min(5, settings.launch_timeout_seconds)

    while time.monotonic() < stability_deadline:
        chunk = _read_available(child, timeout=1)
        if chunk:
            output += chunk

        log_chunk, cds_log_position = _read_file_since(settings.cds_log_path, cds_log_position)
        if log_chunk:
            cds_log_output += log_chunk

        failure = _find_failure(output, settings.failure_patterns)
        if failure is not None:
            return CadenceCheckResult(
                online=False,
                message=f"Virtuoso failed during stabilization in terminal output: {failure}",
            )

        failure = _find_failure(cds_log_output, settings.failure_patterns)
        if failure is not None:
            return CadenceCheckResult(
                online=False,
                message=f"Virtuoso failed during stabilization in {settings.cds_log_path}: {failure}",
            )

        if not child.isalive():
            return CadenceCheckResult(
                online=False,
                message="Virtuoso exited before it became stable",
            )

    return success_result


def _check_license_output(output, source, settings):
    # type: (str, str, Settings) -> CadenceCheckResult | None
    if not output:
        return None

    success = _find_match(output, settings.license_success_patterns)
    if success is not None:
        return CadenceCheckResult(
            online=True,
            message=f"Virtuoso license confirmed in {source}: {success}",
        )

    failure = _find_failure(output, settings.failure_patterns)
    if failure is not None:
        return CadenceCheckResult(
            online=False,
            message=f"Virtuoso failed in {source}: {failure}",
        )
    return None


def _find_failure(output, failure_patterns):
    return _find_match(output, failure_patterns)


def _find_match(output, patterns):
    normalized_output = output.casefold()
    for pattern in patterns:
        if pattern.casefold() in normalized_output:
            return pattern
        try:
            if re.search(pattern, output, re.IGNORECASE):
                return pattern
        except re.error:
            LOGGER.warning("Ignoring invalid output match pattern: %s", pattern)
    return None


def _read_available(child, timeout):
    try:
        return child.read_nonblocking(size=4096, timeout=timeout)
    except pexpect.TIMEOUT:
        return ""
    except pexpect.EOF:
        return child.before or ""


def _file_position(path):
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError as exc:
        LOGGER.warning("Could not inspect CDS log file %s: %s", path, exc)
        return 0


def _read_file_since(path, position):
    try:
        if not path.exists():
            return "", position

        current_size = path.stat().st_size
        read_from = position if current_size >= position else 0
        with path.open("rb") as handle:
            handle.seek(read_from)
            return handle.read().decode("utf-8", errors="replace"), current_size
    except OSError as exc:
        LOGGER.warning("Could not read CDS log file %s: %s", path, exc)
        return "", position


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
