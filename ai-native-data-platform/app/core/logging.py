from __future__ import annotations

import logging

try:
    import structlog  # type: ignore
except Exception:  # pragma: no cover
    structlog = None


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if structlog is None:
        return

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
