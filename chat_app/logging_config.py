import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIRECTORY = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIRECTORY / "server.log"
MAX_LOG_SIZE = 5 * 1024 * 1024
BACKUP_COUNT = 5


def configure_logging(logger_name="chat_server", log_file=LOG_FILE, include_console=True):
    """Configure one server logger that writes to the terminal and a rotating file."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    if include_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def log_event(logger, level, event, **details):
    """Write structured event details without storing chat message content."""
    record = {"event": event, **details}
    logger.log(level, json.dumps(record, ensure_ascii=False, default=str))
