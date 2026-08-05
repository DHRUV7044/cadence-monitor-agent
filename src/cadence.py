from __future__ import annotations

import pexpect

from logger import setup_logger

logger = setup_logger(__name__)


class VirtuosoChecker:
    """
    Launches Virtuoso through the interactive Cadence menu.
    """

    def __init__(self) -> None:
        self.process: pexpect.spawn | None = None

    def check(self) -> tuple[str, str]:
        """
        Returns:
            (status, message)

        status:
            online
            offline
            warning
            unknown
        """

        try:
            self.process = pexpect.spawn(
                "/bin/csh",
                encoding="utf-8",
                timeout=60,
            )

            #
            # Wait for first menu
            #
            self.process.expect("Cadence tools Suite")

            logger.info("Main menu detected.")

            #
            # Select Cadence
            #
            self.process.sendline("1")

            #
            # Wait for second menu
            #
            self.process.expect("Virtuoso")

            logger.info("Cadence menu detected.")

            #
            # Select Virtuoso
            #
            self.process.sendline("101")

            #
            # Read output for 20 seconds
            #
            index = self.process.expect(
                [
                    "License checkout failed",
                    "Unable to obtain license",
                    "Segmentation fault",
                    "DISPLAY",
                    pexpect.TIMEOUT,
                    pexpect.EOF,
                ],
                timeout=20,
            )

            if index == 0:
                return (
                    "offline",
                    "License checkout failed",
                )

            if index == 1:
                return (
                    "offline",
                    "Unable to obtain license",
                )

            if index == 2:
                return (
                    "offline",
                    "Virtuoso crashed",
                )

            if index == 3:
                return (
                    "warning",
                    "DISPLAY problem",
                )

            #
            # If nothing failed in timeout,
            # assume Virtuoso started.
            #
            return (
                "online",
                "Virtuoso started successfully",
            )

        except pexpect.TIMEOUT:

            logger.exception("Timeout while launching Virtuoso.")

            return (
                "unknown",
                "Timeout",
            )

        except Exception as exc:

            logger.exception(exc)

            return (
                "unknown",
                str(exc),
            )

        finally:

            if self.process is not None:

                try:
                    self.process.close(force=True)
                except Exception:
                    pass