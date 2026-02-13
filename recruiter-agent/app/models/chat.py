# app/models/chat.py

from pydantic import BaseModel
from typing import Optional, Any


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    source: Optional[str] = None   # e.g. "github", "linkedin", "demo"
    state: Optional[Any] = None    # <-- added for stateful chat


class ChatResponse(BaseModel):
    reply: str
    state: Any                     # serialized State object
    session_id: Optional[str] = None  # <-- added so frontend can track it
