# app/cv_rag.py – improved CV RAG with safe fallbacks & direct extractors

from __future__ import annotations

from typing import List, Optional
import os
import re

import numpy as np
import google.generativeai as genai

EMBED_MODEL = "models/text-embedding-004"
GEN_MODEL = "gemini-1.5-flash"

_client_configured: bool = False
_rag: Optional["CVRAG"] = None


# ------------------------------------------------------------
# Low-level helpers: Gemini client
# ------------------------------------------------------------

def _try_configure_client() -> bool:
    """Configure Gemini client once; return True if successful, else False."""
    global _client_configured

    if _client_configured:
        return True

    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return False

    try:
        genai.configure(api_key=key)
        _client_configured = True
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

    with open(cv_path, "r", encoding="utf-8") as f:
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


def _extract_education(text: str) -> List[str]:
    """
    Look for an 'Education' section and collect bullet points or lines until
    the next blank line or header-like text.
    """
    lines = text.splitlines()
    edu: List[str] = []
    n = len(lines)
    i = 0

    while i < n:
        if "education" in lines[i].strip().lower():
            i += 1
            while i < n and lines[i].strip():
                edu.append(lines[i].strip())
                i += 1
            break
        i += 1

    return edu


def _extract_certifications(text: str) -> List[str]:
    """
    Look for lines under "Certifications" or bullet-like lists that mention
    certificates or trainings.
    """
    lines = text.splitlines()
    certs: List[str] = []
    n = len(lines)
    i = 0

    while i < n:
        line = lines[i].strip()
        lower = line.lower()

        # "Certifications" header
        if "certification" in lower or "certifications" in lower:
            i += 1
            # Gather consecutive bullets or lines
            while i < n and lines[i].strip():
                item = lines[i].strip().lstrip("-• ").strip()
                if item:
                    certs.append(item)
                i += 1
            continue

        # "Previous Trainings & Certifications"
        if "previous trainings & certifications" in lower:
            i += 1
            while i < n and lines[i].strip().startswith("-"):
                item = lines[i].strip().lstrip("-• ").strip()
                if item:
                    certs.append(item)
                i += 1
            continue

        i += 1

    # Deduplicate while preserving order
    seen = set()
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
        response = genai.embed_content(
            model=EMBED_MODEL,
            content=texts,
            task_type="retrieval_document",
        )
        # Older / newer SDKs structure this slightly differently
        if isinstance(response, dict) and "embeddings" in response:
            embs = response["embeddings"]
        else:
            embs = getattr(response, "embeddings", None)

        if not embs:
            return None

        arr = np.array([e["values"] for e in embs], dtype=float)
        return arr
    except Exception:
        return None


def _embed_text(text: str, task_type: str = "retrieval_query") -> Optional[np.ndarray]:
    """Embed a single text with Gemini, or return None."""
    if not _try_configure_client():
        return None

    try:
        response = genai.embed_content(
            model=EMBED_MODEL,
            content=text,
            task_type=task_type,
        )
        vec = getattr(response, "embedding", None) or response.get("embedding")
        if not vec:
            return None
        return np.array(vec["values"], dtype=float)
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

        # Certifications
        if "certification" in q or "certifications" in q or "certificate" in q:
            certs = _extract_certifications(self.cv_text)
            if certs:
                bullets = "\n".join(f"- {c}" for c in certs)
                return "Sergiu holds the following certifications:\n\n" + bullets
            return "I couldn't find certifications in Sergiu’s CV."

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
            model = genai.GenerativeModel(GEN_MODEL)
            resp = model.generate_content(prompt)
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
