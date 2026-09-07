import logging
import tempfile
import unittest
import uuid
from pathlib import Path

from chat_app.logging_config import BACKUP_COUNT, MAX_LOG_SIZE, configure_logging, log_event


class LoggingTests(unittest.TestCase):
    def test_log_event_writes_structured_metadata(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "server.log"
            logger = configure_logging(
                logger_name=f"test_logger_{uuid.uuid4().hex}",
                log_file=log_file,
                include_console=False,
            )

            try:
                log_event(
                    logger,
                    logging.INFO,
                    "MESSAGE_RECEIVED",
                    username="alice",
                    message_length=20,
                )
                for handler in logger.handlers:
                    handler.flush()

                log_text = log_file.read_text(encoding="utf-8")
                self.assertIn('"event": "MESSAGE_RECEIVED"', log_text)
                self.assertIn('"username": "alice"', log_text)
                self.assertIn('"message_length": 20', log_text)
            finally:
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)

    def test_file_handler_has_bounded_rotation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            logger = configure_logging(
                logger_name=f"test_logger_{uuid.uuid4().hex}",
                log_file=Path(temporary_directory) / "server.log",
                include_console=False,
            )

            try:
                handler = logger.handlers[0]
                self.assertEqual(handler.maxBytes, MAX_LOG_SIZE)
                self.assertEqual(handler.backupCount, BACKUP_COUNT)
            finally:
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
