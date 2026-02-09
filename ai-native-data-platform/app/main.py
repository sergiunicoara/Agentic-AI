"""Compatibility entrypoint.

The rewritten scaffold uses app.api.main:app as the canonical FastAPI app.
This shim keeps existing deployment commands working (uvicorn app.main:app).
"""

from app.api.main import app  # noqa: F401
