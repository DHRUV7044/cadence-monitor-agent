import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

from cadence import CadenceCheckResult
from settings import Settings


ALLOWED_STATUSES = {"online", "offline", "warning", "maintenance", "unknown"}  # type: Set[str]


def build_status_document(
    settings,
    result,
    previous_status_path,
):
    # type: (Settings, CadenceCheckResult, Path) -> Dict[str, Any]
    now = _india_now()
    status_value = "online" if result.online else "offline"
    last_success = now if result.online else _read_previous_last_success(previous_status_path)

    return {
        "schema_version": 1,
        "generated_at": now,
        "monitor": {
            "name": settings.monitor_name,
            "host": settings.monitor_host,
        },
        "services": [
            {
                "id": "virtuoso",
                "name": "Virtuoso",
                "status": _validate_status(status_value),
                "message": result.message,
                "last_success": last_success,
            }
        ],
    }


def write_status_document(path, document):
    # type: (Path, Dict[str, Any]) -> bool
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(document, indent=2, ensure_ascii=True) + "\n"

    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False

    path.write_text(rendered, encoding="utf-8")
    return True


def _read_previous_last_success(path):
    # type: (Path) -> Optional[str]
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    services = data.get("services")
    if not isinstance(services, list):
        return None

    for service in services:
        if isinstance(service, dict) and service.get("id") == "virtuoso":
            last_success = service.get("last_success")
            return last_success if isinstance(last_success, str) else None

    return None


def _validate_status(status):
    # type: (str) -> str
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    return status


def _india_now():
    # type: () -> str
    india_timezone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(india_timezone).replace(microsecond=0).isoformat()
