import logging
import sys


def setup_logging():
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    for noisy_logger in ("httpx", "httpcore", "urllib3", "asyncio", "playwright"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
