# app/cv_rag.py – improved CV RAG with safe fallbacks & direct extractors

from __future__ import annotations

from typing import List, Optional
import os
import re

import numpy as np
from google import genai
from google.genai import types

EMBED_MODEL = "models/text-embedding-004"
GEN_MODEL = "gemini-2.5-flash"

_client: "genai.Client | None" = None
_rag: Optional["CVRAG"] = None


# ------------------------------------------------------------
# Low-level helpers: Gemini client
# ------------------------------------------------------------

def _try_configure_client() -> bool:
    """Create Gemini client once; return True if successful, else False."""
    global _client

    if _client is not None:
        return True

    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").lstrip("\ufeff").strip() or None
    if not key:
        return False

    try:
        _client = genai.Client(api_key=key)
        return True
    except Exception:
        return False


# ------------------------------------------------------------
# CV loading + chunking
# ------------------------------------------------------------

def _load_cv_text() -> str:
    base_dir = os.path.dirname(__file__)
    cv_path = os.path.join(base_dir, "cv.txt")

    if not os.path.exists(cv_path):
        raise FileNotFoundError(f"cv.txt not found at {cv_path}")

    with open(cv_path, "r", encoding="utf-8-sig") as f:
        return f.read()


def _chunk_text(text: str, max_chars: int = 900) -> List[str]:
    """Chunk CV into ~max_chars segments without breaking too badly."""
    words = text.split()
    chunks: List[str] = []
    current: List[str] = []

    for w in words:
        current.append(w)
        if len(" ".join(current)) >= max_chars:
            chunks.append(" ".join(current))
            current = []

    if current:
        chunks.append(" ".join(current))

    return chunks


# ------------------------------------------------------------
# Regex-based direct field extractors
# ------------------------------------------------------------

def _extract_phone(text: str) -> Optional[str]:
    # Prefer explicit "Phone:" label if present
    m = re.search(r"Phone:\s*([+0-9][0-9\s\-]+)", text)
    if m:
        return m.group(1).strip()

    # Generic phone pattern fallback
    m = re.search(r"\+?\d[\d\s\-]{7,}", text)
    return m.group(0).strip() if m else None


def _extract_email(text: str) -> Optional[str]:
    # Prefer explicit "Email:" label if present
    m = re.search(r"Email:\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    if m:
        return m.group(1).strip()

    # Generic email fallback
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0).strip() if m else None


def _extract_location(text: str) -> Optional[str]:
    # e.g. "Location: Timisoara, Romania"
    m = re.search(r"Location:\s*(.+)", text)
    if m:
        return m.group(1).strip()
    return None


def _extract_years_experience(text: str) -> Optional[str]:
    # e.g. "Years of experience: 5+"
    m = re.search(r"Years of experience:\s*(.+)", text)
    if m:
        return m.group(1).strip()
    return None


_SECTION_HEADERS = {
    "professional objective", "technical skills", "professional experience",
    "education", "certifications & professional development", "certifications",
    "languages", "additional information", "summary", "profile",
}


def _is_section_header(line: str) -> bool:
    """Return True if line is a standalone CV section header (not a phrase containing a keyword)."""
    stripped = line.strip().lower()
    return stripped in _SECTION_HEADERS


def _extract_education(text: str) -> List[str]:
    """
    Look for a standalone 'Education' section header and collect degree lines
    until the next section header.
    """
    lines = text.splitlines()
    edu: List[str] = []
    n = len(lines)
    i = 0

    # Find the standalone "Education" header
    while i < n:
        if lines[i].strip().lower() == "education":
            i += 1
            break
        i += 1

    # Collect until next section header
    while i < n:
        line = lines[i].strip()
        if _is_section_header(line):
            break
        if line:
            edu.append(line)
        i += 1

    return edu


def _extract_skills(text: str) -> List[str]:
    """
    Extract the Technical Skills section (table rows or key-value lines)
    until the next section header.
    """
    lines = text.splitlines()
    skills: List[str] = []
    n = len(lines)
    i = 0

    # Find "Technical Skills" header
    while i < n:
        stripped = lines[i].strip().lower()
        if "technical skills" in stripped or stripped == "skills":
            i += 1
            break
        i += 1

    # Collect raw lines until next section header
    raw: List[str] = []
    while i < n:
        line = lines[i].strip()
        if _is_section_header(line):
            break
        if line and line.lower() not in ("category technologies", "category", "technologies"):
            raw.append(line)
        i += 1

    # Merge wrapped lines:
    # 1. If a line ends with ',' the next line is a continuation (e.g. "Pandas,\nNumPy")
    # 2. If a line is 1 word and the previous line is ≤3 words it's a wrapped fragment
    #    (e.g. "Cloud computing\nplatforms\nAWS")
    merged: List[str] = []
    for line in raw:
        if merged and merged[-1].endswith(","):
            merged[-1] = merged[-1] + " " + line
        elif merged and len(line.split()) == 1 and len(merged[-1].split()) <= 3:
            merged[-1] = merged[-1] + " " + line
        else:
            merged.append(line)

    return merged


def _extract_certifications(text: str) -> List[str]:
    """
    Look for lines under "Certifications" or bullet-like lists that mention
    certificates or trainings.

    Stops collecting when it hits:
    - a blank line
    - a line with a date range (job/education entry)
    - a known section header keyword
    - more than 20 items (safety cap)
    """
    _SECTION_HEADERS = {
        "education", "experience", "employment", "work history",
        "languages", "skills", "interests", "additional", "projects",
        "summary", "profile", "objective", "references",
    }
    # Date range at START of line = training entry label (e.g. "2005-2010: ...")
    # Date range in middle = job title (e.g. "Homeschooling Teacher (2016 - 2024)")
    _DATE_RANGE_MIDDLE = re.compile(r"\(?(19|20)\d{2}\s*[-–]\s*((19|20)\d{2}|present)\)?", re.I)

    # Bare sub-header lines that should be skipped (not added as items)
    _SKIP_EXACT = {
        "certifications", "recent certifications", "recent certifications (2025)",
        "previous trainings & certifications", "certifications & professional development",
    }

    def _is_section_boundary(line: str) -> bool:
        low = line.lower().strip()
        # Job/education entry: date range in the middle of the line
        if _DATE_RANGE_MIDDLE.search(line):
            return True
        if any(h in low for h in _SECTION_HEADERS):
            return True
        return False

    lines = text.splitlines()
    certs: List[str] = []
    n = len(lines)
    i = 0

    while i < n:
        line = lines[i].strip()
        lower = line.lower()

        if "certification" in lower or "certifications" in lower or \
                "previous trainings" in lower:
            i += 1
            while i < n and lines[i].strip() and len(certs) < 20:
                item = lines[i].strip().lstrip("-• ").strip()
                if _is_section_boundary(item):
                    break
                # Skip bare sub-header lines
                if item.lower().strip() in _SKIP_EXACT:
                    i += 1
                    continue
                if item:
                    certs.append(item)
                i += 1
            continue

        i += 1

    # Deduplicate while preserving order
    seen: set = set()
    result: List[str] = []
    for c in certs:
        if c not in seen:
            seen.add(c)
            result.append(c)

    return result


# ------------------------------------------------------------
# Embedding helpers
# ------------------------------------------------------------

def _embed_texts(texts: List[str]) -> Optional[np.ndarray]:
    """Embed a list of texts with Gemini, or return None if not available."""
    if not _try_configure_client():
        return None

    try:
        response = _client.models.embed_content(  # type: ignore[union-attr]
            model=EMBED_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        embs = response.embeddings
        if not embs:
            return None
        arr = np.array([e.values for e in embs], dtype=float)
        return arr
    except Exception:
        return None


def _embed_text(text: str, task_type: str = "retrieval_query") -> Optional[np.ndarray]:
    """Embed a single text with Gemini, or return None."""
    if not _try_configure_client():
        return None

    try:
        response = _client.models.embed_content(  # type: ignore[union-attr]
            model=EMBED_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type=task_type.upper()),
        )
        embs = response.embeddings
        if not embs:
            return None
        return np.array(embs[0].values, dtype=float)
    except Exception:
        return None


def _cosine_sim_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between:
    - a: shape (d,) query
    - b: shape (N, d) documents
    """
    if a.ndim == 1:
        a = a[None, :]
    # normalize
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return np.dot(a_norm, b_norm.T).flatten()


# ------------------------------------------------------------
# Main CVRAG class
# ------------------------------------------------------------

class CVRAG:
    """RAG over Sergiu's CV with Gemini embeddings and safe fallbacks."""

    def __init__(self) -> None:
        # Load + chunk CV once
        cv_text = _load_cv_text()
        self.cv_text: str = cv_text
        self.chunks: List[str] = _chunk_text(cv_text)
        self._embeddings: Optional[np.ndarray] = None  # lazy

    def _ensure_embeddings(self) -> bool:
        """Compute embeddings once on first query."""
        if self._embeddings is not None:
            return True

        if not self.chunks:
            return False

        embs = _embed_texts(self.chunks)
        if embs is None:
            # We couldn't embed; we still allow direct regex Q&A
            return False

        self._embeddings = embs
        return True

    def _retrieve_top_k(self, question: str, k: int = 3) -> List[str]:
        """
        Retrieve top-k chunks using cosine similarity + simple token boosts.
        """
        if not self.chunks:
            return []

        if not self._ensure_embeddings():
            # No embeddings available
            return []

        q_vec = _embed_text(question, task_type="retrieval_query")
        if q_vec is None:
            return []

        assert self._embeddings is not None
        sims = _cosine_sim_matrix(q_vec, self._embeddings)
        if sims.size == 0:
            return []

        # Keyword boosting: favor chunks that contain important question tokens
        tokens = [t for t in re.findall(r"\w+", question.lower()) if len(t) > 3]
        boosts = np.zeros_like(sims)

        for idx, ch in enumerate(self.chunks):
            lower = ch.lower()
            for t in tokens:
                if t in lower:
                    boosts[idx] += 0.2

        scores = sims + boosts
        top_k_idx = np.argsort(scores)[-k:][::-1]
        return [self.chunks[int(i)] for i in top_k_idx]

    def _direct_facts_answer(self, question: str) -> Optional[str]:
        """
        Handle common recruiter questions without calling the LLM,
        using regex-based extraction over the full CV text.
        """
        q = question.lower()

        # Phone / contact
        if any(w in q for w in ["phone", "phone number", "contact number"]):
            phone = _extract_phone(self.cv_text)
            if phone:
                return f"Sergiu’s phone number is {phone}."
            return "I couldn't find a phone number in Sergiu’s CV."

        # Email
        if any(w in q for w in ["email", "e-mail"]):
            email = _extract_email(self.cv_text)
            if email:
                return f"Sergiu’s email is {email}."
            return "I couldn't find an email address in Sergiu’s CV."

        # Location / where based
        if any(w in q for w in ["location", "based", "city", "country"]):
            loc = _extract_location(self.cv_text)
            if loc:
                return f"Sergiu is based in {loc}."
            return "I couldn't find a clear location in Sergiu’s CV."

        # Years of experience
        if "years of experience" in q or "experience" in q:
            y = _extract_years_experience(self.cv_text)
            if y:
                return f"Sergiu has {y} of experience."
            # fallback: just mention general experience
            return "Sergiu has multiple years of experience in software engineering and ML/LLM systems."

        # Education
        if "education" in q or "degree" in q or "university" in q:
            edu = _extract_education(self.cv_text)
            if edu:
                bullets = "\n".join(f"- {e}" for e in edu)
                return "Here is what I found about Sergiu’s education:\n\n" + bullets
            return "I couldn't find detailed education information in Sergiu’s CV."

        # Skills / tech stack
        if any(w in q for w in ["skill", "skills", "tech stack", "technologies", "technical"]):
            skills = _extract_skills(self.cv_text)
            if skills:
                bullets = "\n".join(f"- {s}" for s in skills)
                return "Here are Sergiu’s technical skills:\n\n" + bullets
            return "I couldn’t find technical skills information in Sergiu’s CV."

        # Certifications
        if "certification" in q or "certifications" in q or "certificate" in q:
            certs = _extract_certifications(self.cv_text)
            if certs:
                bullets = "\n".join(f"- {c}" for c in certs)
                return "Sergiu holds the following certifications:\n\n" + bullets
            return "I couldn’t find certifications in Sergiu’s CV."

        return None

    def query(self, question: str) -> str:
        """Return an answer grounded only in the CV."""

        # 1) Try direct factual extraction first (no LLM, no embeddings).
        direct = self._direct_facts_answer(question)
        if direct is not None:
            return direct

        # 2) Retrieve relevant snippets for general questions.
        relevant_chunks = self._retrieve_top_k(question, k=3)
        if not relevant_chunks:
            return "I couldn't find this information in Sergiu’s CV."

        context = "\n\n---\n\n".join(relevant_chunks)

        # 3) If Gemini isn't configured, avoid dumping raw context; be conservative.
        if not _try_configure_client():
            return "I couldn't find this information in Sergiu’s CV."

        prompt = f"""
You are helping a recruiter understand a candidate's fit based ONLY on their CV.

CV content:
{context}

Question:
{question}

Instructions:
- Answer concisely and directly.
- Use ONLY facts from the CV content above.
- If the CV does not contain the answer, say: "I couldn't find this information in Sergiu's CV."
""".strip()

        try:
            resp = _client.models.generate_content(model=GEN_MODEL, contents=prompt)  # type: ignore[union-attr]
            text = getattr(resp, "text", None)
            if text:
                return text.strip()
            # Fallback if no text field but call succeeded
            return "I couldn't find this information in Sergiu’s CV."
        except Exception:
            # Strict fallback: do not leak raw CV chunks
            return "I couldn't find this information in Sergiu’s CV."


# ---------------------------
# Singleton accessor
# ---------------------------

def get_cv_rag():
    """
    Return a singleton CVRAG instance, or a safe dummy if init fails.
    """
    global _rag
    if _rag is None:
        try:
            _rag = CVRAG()
        except Exception:
            class Dummy:
                def query(self, q: str) -> str:
                    return "CV RAG unavailable. Ensure cv.txt and GOOGLE_API_KEY are correctly configured."
            _rag = Dummy()  # type: ignore[assignment]
    return _rag
