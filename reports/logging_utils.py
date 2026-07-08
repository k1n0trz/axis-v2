"""Logging centralizado para Axis."""
import logging
import sys
from typing import Any, Optional

from django.conf import settings


class AxisFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.extra = getattr(record, "extra", {})
        return super().format(record)


def get_logger(name: str, extra: Optional[dict] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = AxisFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    if settings.DEBUG:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if extra:
        extra_record = logging.makeLogRecord({"extra": extra})
        for key, value in extra.items():
            setattr(extra_record, key, value)

    return logger


app_logger = get_logger("axis")
analytics_logger = get_logger("axis.analytics")
import_logger = get_logger("axis.import")
export_logger = get_logger("axis.export")
api_logger = get_logger("axis.api")


def log_query(logger: logging.Logger, query: str, params: Optional[list] = None):
    logger.debug("SQL: %s | params: %s", query, params)


def log_view_request(logger: logging.Logger, view: str, user: Any, get_params: dict):
    logger.info("VIEW: %s | user: %s | params: %s", view, getattr(user, "username", "anonymous"), get_params)


def log_import_start(logger: logging.Logger, filename: str, sheet: str, row_count: int):
    logger.info("IMPORT START: %s | sheet: %s | rows: %s", filename, sheet, row_count)


def log_import_end(logger: logging.Logger, filename: str, created: int, updated: int, errors: int):
    logger.info("IMPORT END: %s | created: %s, updated: %s, errors: %s", filename, created, updated, errors)


def log_export(logger: logging.Logger, name: str, filters: dict, row_count: int):
    logger.info("EXPORT: %s | filters: %s | rows: %s", name, filters, row_count)


def log_error(logger: logging.Logger, error: Exception, context: dict):
    logger.exception("ERROR: %s | %s | %s", type(error).__name__, str(error), context)