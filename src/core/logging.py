import sys
from contextvars import ContextVar

from loguru import logger as _loguru_logger

from core.settings import LogFormat, settings

logger_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level> | {extra}"
)

_loguru_logger.remove()
if settings.LOGGING.FORMAT == LogFormat.JSON:
    _loguru_logger.add(
        sys.stdout,
        serialize=True,
        level="INFO",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )
else:
    _loguru_logger.add(
        sys.stdout,
        format=logger_format,
        level="INFO",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class LoggerProxy:
    def __getattr__(self, item):
        return getattr(_loguru_logger.bind(request_id=request_id_var.get()), item)


logger = LoggerProxy()
