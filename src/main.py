from __future__ import annotations

import logging
import sys

from cadence import check_virtuoso_license
from publisher import publish_status
from settings import load_settings
from status import build_status_document, write_status_document


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    configure_logging()
    logger = logging.getLogger(__name__)

    settings = load_settings()
    result = check_virtuoso_license(settings)
    document = build_status_document(settings, result, settings.status_json)

    status_changed = write_status_document(settings.status_json, document)
    if status_changed:
        logger.info("Updated status file: %s", settings.status_json)
    else:
        logger.info("Status file is unchanged: %s", settings.status_json)

    published = publish_status(settings)
    if published:
        logger.info("Published status update")
    else:
        logger.info("No publish needed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
