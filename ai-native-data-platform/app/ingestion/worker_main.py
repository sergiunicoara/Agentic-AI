from __future__ import annotations
import time
from app.worker import start_worker

if __name__ == "__main__":
    start_worker()
    print("[worker] running...")
    while True:
        time.sleep(10)
