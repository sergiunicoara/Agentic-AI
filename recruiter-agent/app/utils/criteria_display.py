# app/utils/criteria_display.py

import re

def humanize_criteria(criteria: list[str]) -> list[str]:
    """
    Convert internal normalized criteria (e.g., 'production_rag')
    into human-friendly strings for UI display.
    """
    friendly = []

    for c in criteria:
        if not c:
            continue

        # Special explicit mappings
        if c == "production_rag":
            friendly.append("Production RAG")
            continue
        if c == "llm":
            friendly.append("LLM")
            continue

        # Generic transformation
        text = c.replace("_", " ").title()

        # Fix common acronyms broken by .title()
        text = re.sub(r"\bAi\b", "AI", text)
        text = re.sub(r"\bMl\b", "ML", text)
        text = re.sub(r"\bNlp\b", "NLP", text)

        friendly.append(text)

    return friendly
