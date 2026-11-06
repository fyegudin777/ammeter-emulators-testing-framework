import logging
import os
from datetime import datetime


class TestLogger:
    """Thin wrapper around :mod:`logging` that writes both to a timestamped
    log file (under ``results/logs``) and to the console for a single named
    test run.
    """

    def __init__(self, test_name: str):
        self._test_name = test_name
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Create (or reuse) a logger configured with a file + console handler.

        Guards against adding duplicate handlers if a ``TestLogger`` for the
        same ``test_name`` is instantiated more than once in the same
        process (e.g. one run per ammeter type).
        """
        log_dir = "results/logs"
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"{log_dir}/{timestamp}_{self._test_name}.log"

        logger = logging.getLogger(f"test_{self._test_name}_{timestamp}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        if not logger.handlers:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    def info(self, message: str):
        self.logger.info(message)

    def error(self, message: str):
        self.logger.error(message)

    def debug(self, message: str):
        self.logger.debug(message)

    def warning(self, message: str):
        self.logger.warning(message)