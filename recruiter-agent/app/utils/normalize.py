from __future__ import annotations
from typing import List
import re

# Canonical criteria & synonyms
VALID_CRITERIA = {
    "leadership": ["leadership", "leadershi", "leader", "leading"],
    "communication": ["communication", "comms", "communication skills"],
    "ownership": ["ownership", "owner", "takes ownership", "end-to-end", "end to end"],
    "production_rag": ["production rag", "rag", "retrieval", "prod rag", "embeddings", "ranking", "vector search", "graphrag"],
    "deep_learning": ["deep learning", "transformer", "transformers", "fine-tuning", "fine-tune", "finetuning", "bert", "llm fine-tuning"],
    "voice_ai": [
        "voice ai", "voice", "stt", "tts", "speech", "asr",
        "deepgram", "telephony", "speech-to-text", "text-to-speech",
        "phone bot", "phonebot", "voicebot", "voice bot", "phone assistant",
        "elevenlabs", "eleven labs", "whisper", "asr/stt", "audio",
    ],
    "observability": [
        "observability", "langsmith", "langfuse", "otel", "opentelemetry",
        "tracing", "monitoring", "evaluation", "evals", "llm evaluation",
    ],
    "low_latency": [
        "low latency", "low-latency", "latency", "real-time", "realtime",
        "streaming", "real time", "sub-200ms", "fast response",
    ],
}

def slugify(text: str) -> str:
    """Turn unknown criteria into safe internal identifiers."""
    text = text.lower()
    text = re.sub(r"[^\w]+", "_", text)
    return text.strip("_")

def normalize_criteria(raw_list: List[str] | None) -> List[str]:
    if not raw_list:
        return []

    cleaned: List[str] = []

    for c in raw_list:
        if not c:
            continue

        x = c.strip().lower().strip(" .;:,!?")

        matched = False
        for canon, variants in VALID_CRITERIA.items():
            if x == canon or x in variants:
                cleaned.append(canon)
                matched = True
                break

        if matched:
            continue

        # If not a known criterion → keep it but normalize safely
        slug = slugify(x)
        if slug:
            cleaned.append(slug)

    # Deduplicate while preserving order
    seen = set()
    result: List[str] = []
    for c in cleaned:
        if c not in seen:
            seen.add(c)
            result.append(c)

    # Keep max 4 (JD pastes can legitimately have 4 criteria)
    return result[:4]
