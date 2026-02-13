# app/telemetry/logging.py
import logging
import os
import sys
from typing import Optional


def configure_logging(service_name: str, level: Optional[str] = None) -> None:
    """
    Configure structured-ish logging for the service.
    Safe to call multiple times (it will just reconfigure root logger).
    """
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    logging.basicConfig(
        level=log_level,
        format=(
            "%(asctime)s | %(levelname)s | %(name)s | "
            f"service={service_name} | %(message)s"
        ),
        stream=sys.stdout,
    )

    logging.getLogger(__name__).info(
        "Logging configured for service=%s", service_name
    )
