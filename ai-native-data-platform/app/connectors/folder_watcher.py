from __future__ import annotations
import json
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import httpx

API_URL = "http://localhost:8000/ingest/transcript"

class Handler(FileSystemEventHandler):
    def __init__(self, workspace_id: str, api_key: str):
        self.workspace_id = workspace_id
        self.api_key = api_key

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".json":
            return
        time.sleep(0.2)

        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("workspace_id", self.workspace_id)
        payload.setdefault("source", "folder")

        headers = {"X-Workspace-Id": self.workspace_id, "X-API-Key": self.api_key}
        with httpx.Client(timeout=20) as client:
            r = client.post(API_URL, json=payload, headers=headers)
            r.raise_for_status()
            print("[folder_watcher] ingested:", path.name, r.json())

def run(folder: str, workspace_id: str, api_key: str):
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)

    handler = Handler(workspace_id, api_key)
    observer = Observer()
    observer.schedule(handler, str(folder_path), recursive=False)
    observer.start()

    print(f"[folder_watcher] watching: {folder_path} (workspace={workspace_id})")
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
