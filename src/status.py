from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cadence import CadenceCheckResult
from settings import Settings


StatusValue = Literal["online", "offline", "warning", "maintenance", "unknown"]
ALLOWED_STATUSES: set[str] = {"online", "offline", "warning", "maintenance", "unknown"}


def build_status_document(
    settings: Settings,
    result: CadenceCheckResult,
    previous_status_path: Path,
) -> dict[str, Any]:
    now = _utc_now()
    status_value: StatusValue = "online" if result.online else "offline"
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


def write_status_document(path: Path, document: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(document, indent=2, ensure_ascii=True) + "\n"

    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False

    path.write_text(rendered, encoding="utf-8")
    return True


def _read_previous_last_success(path: Path) -> str | None:
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


def _validate_status(status: StatusValue) -> StatusValue:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    return status


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
