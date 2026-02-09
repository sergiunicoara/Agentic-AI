from __future__ import annotations
import os
from app.connectors.folder_watcher import run

if __name__ == "__main__":
    folder = os.getenv("WATCH_FOLDER", "./incoming")
    workspace_id = os.getenv("WATCH_WORKSPACE", "demo")
    api_key = os.getenv("WATCH_API_KEY", "demo-key-123")
    run(folder, workspace_id, api_key)
