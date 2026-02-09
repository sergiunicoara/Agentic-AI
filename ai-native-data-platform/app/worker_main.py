from __future__ import annotations

import time

from app.core.logging import configure_logging
from app.ingestion.pipeline import start_worker


def main() -> None:
    configure_logging()
    start_worker()
    # Keep process alive.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
