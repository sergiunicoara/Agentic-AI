from __future__ import annotations

import base64
import hashlib
import io
import os

VISION_PROVIDER = os.getenv("VISION_PROVIDER", "mock")  # openai | gemini | mock

CAPTION_PROMPT = (
    "Describe this image in detail. Focus on visible text, charts, tables, diagrams, "
    "and any key information. Be specific and comprehensive — your description will be "
    "used for semantic search retrieval."
)


def caption_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Generate a text caption for an image using the configured vision provider."""
    if VISION_PROVIDER == "openai":
        return _openai_caption(image_bytes, mime_type)
    if VISION_PROVIDER == "gemini":
        return _gemini_caption(image_bytes, mime_type)
    return _mock_caption(image_bytes)


def _openai_caption(image_bytes: bytes, mime_type: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    b64 = base64.b64encode(image_bytes).decode()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                    {"type": "text", "text": CAPTION_PROMPT},
                ],
            }
        ],
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


def _gemini_caption(image_bytes: bytes, mime_type: str) -> str:
    import google.generativeai as genai
    import PIL.Image

    model = genai.GenerativeModel("gemini-1.5-flash")
    img = PIL.Image.open(io.BytesIO(image_bytes))
    response = model.generate_content([CAPTION_PROMPT, img])
    return response.text.strip()


def _mock_caption(image_bytes: bytes) -> str:
    h = hashlib.sha256(image_bytes).hexdigest()[:8]
    return (
        f"[mock caption] Visual content fingerprint={h}. "
        "Contains charts, annotated diagrams, and tabular data relevant to the document context."
    )
