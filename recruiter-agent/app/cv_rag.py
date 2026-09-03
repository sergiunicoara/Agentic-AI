# app/cv_rag.py – improved CV RAG with safe fallbacks & direct extractors

from __future__ import annotations

import asyncio
import threading
import time
from typing import AsyncGenerator, List, Optional
import os
import re

import numpy as np
from google import genai
from google.genai import types

EMBED_MODEL = "models/text-embedding-004"
GEN_MODEL = "gemini-2.5-flash"          # works for both AI Studio and Vertex AI

# Single source of truth for the "not found" sentinel — streaming and
# non-streaming paths used to emit three different spellings of this string,
# which meant string-matching tests/checks could pass on one path and fail
# on the other. Every caller must go through this constant.
NOT_FOUND_MSG = "I couldn't find this information in Sergiu's CV."

# Failed-embedding cooldown: if embedding calls fail (bad key, quota, network),
# don't retry on every single query — that pays a full failed round-trip each
# time. Wait this long before trying again.
_EMBED_RETRY_COOLDOWN_SECS = 60.0

_client: "genai.Client | None" = None
_rag: Optional["CVRAG"] = None


# ------------------------------------------------------------
# Low-level helpers: Gemini client
# ------------------------------------------------------------

def _try_configure_client() -> bool:
    """Create Gemini client once; return True if successful, else False.

    Tries AI Studio key first; falls back to Vertex AI ADC when the key is
    absent or fails a smoke-test (e.g. wrong service, quota exhausted, bad
    value) — same pattern as app/judge.py and app/session_summary.py.
    """
    global _client

    if _client is not None:
        return True

    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").lstrip("﻿").strip()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "recruiter-sergiu-260213").strip()

    if key and key.startswith("AIza"):
        try:
            candidate = genai.Client(api_key=key)
            candidate.models.get(model="gemini-2.5-flash")
            _client = candidate
            return True
        except Exception:
            pass  # fall through to Vertex ADC

    try:
        _client = genai.Client(vertexai=True, project=project, location="us-central1")
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


def _chunk_text(text: str, max_chars: int = 900, overlap_lines: int = 2) -> List[str]:
    """
    Chunk CV into ~max_chars segments, preserving line structure (bullets,
    section headers) instead of flattening everything with .split().
    Adjacent chunks share `overlap_lines` lines of context so a fact sitting
    near a chunk boundary is still retrievable.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        current.append(line)
        current_len += len(line) + 1
        if current_len >= max_chars:
            chunks.append("\n".join(current))
            # start next chunk with the last `overlap_lines` lines repeated
            current = current[-overlap_lines:] if overlap_lines else []
            current_len = sum(len(ln) + 1 for ln in current)
        i += 1

    if current:
        chunks.append("\n".join(current))

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
    """
    "Location:" can legitimately appear more than once (header contact info,
    plus e.g. an "Additional Information" footer note). Prefer the one in
    the header block (first ~10 non-empty lines) since that's the candidate's
    actual base — a later mention is more likely to be a remote-work note.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()][:10]
    header_block = "\n".join(lines)

    m = re.search(r"Location:\s*(.+)", header_block)
    if m:
        return m.group(1).strip()

    # Fall back to the first mention anywhere in the document
    m = re.search(r"Location:\s*(.+)", text)
    return m.group(1).strip() if m else None


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


# Standalone section-header lines that bound a certifications block. Matched
# by EXACT line equality (after stripping/lowering), never by substring —
# a real cert line like "Google Cloud Skills Boost — Generative AI" contains
# "skills" as a substring but is not a section header, so substring matching
# would truncate the list right there.
_CERT_BOUNDARY_HEADERS = {
    "education", "experience", "employment", "work history",
    "languages", "skills", "technical skills", "interests", "additional",
    "additional information", "projects", "summary", "profile", "objective",
    "professional objective", "references", "professional experience",
}

# Date range at START of line = training entry label (e.g. "2005-2010: ...")
# Date range in middle = job title (e.g. "Homeschooling Teacher (2016 - 2024)")
_DATE_RANGE_MIDDLE = re.compile(r"\(?(19|20)\d{2}\s*[-–]\s*((19|20)\d{2}|present)\)?", re.I)

# Bare sub-header lines that should be skipped (not added as items)
_CERT_SKIP_EXACT = {
    "certifications", "recent certifications", "recent certifications (2025)",
    "previous trainings & certifications", "certifications & professional development",
}


def _is_cert_section_boundary(line: str) -> bool:
    low = line.lower().strip()
    # Job/education entry: date range in the middle of the line
    if _DATE_RANGE_MIDDLE.search(line):
        return True
    # Exact-match only — substring matching here would truncate real cert
    # lines that happen to contain a header word (e.g. "... Skills Boost ...")
    if low in _CERT_BOUNDARY_HEADERS:
        return True
    return False


def _extract_certifications(text: str) -> List[str]:
    """
    Look for lines under "Certifications" or bullet-like lists that mention
    certificates or trainings.

    Stops collecting when it hits:
    - a blank line
    - a line with a date range (job/education entry)
    - a standalone section-header line (exact match, not substring)
    - more than 20 items (safety cap)
    """
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
                if _is_cert_section_boundary(item):
                    break
                # Skip bare sub-header lines
                if item.lower().strip() in _CERT_SKIP_EXACT:
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


# Common stopwords excluded from the lexical keyword boost below. Without
# this, "what does he have experience with" boosts on "what"/"does"/"have"
# just as much as "Kubernetes" — pure noise weighted like signal.
_STOPWORDS = {
    "what", "does", "have", "with", "this", "that", "would", "could",
    "should", "about", "which", "when", "where", "there", "their",
    "them", "then", "than", "into", "your", "some", "much", "many",
    "tell", "know", "like", "just", "also", "been", "being", "were",
    "will", "years", "year",
}

# Minimum score (cosine sim + boost) a chunk must clear to be returned.
# Without a floor, off-topic questions still get k "least irrelevant"
# chunks handed to Gemini as if they were relevant context.
_MIN_RETRIEVAL_SCORE = 0.35

# Keyword-boost weight per matched non-stopword token, capped in total so a
# question with many matched tokens can't out-weigh the semantic signal
# (cosine sim is bounded in [-1, 1], mostly [0, 1] for related text).
_BOOST_PER_TOKEN = 0.08
_BOOST_CAP = 0.3


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
        self._embed_failed_at: Optional[float] = None  # cooldown tracking

    def _ensure_embeddings(self) -> bool:
        """Compute embeddings once on first query.

        On failure, remember the timestamp and don't retry until the
        cooldown elapses — otherwise a persistent failure (bad key, quota
        exhaustion) pays a full failed round-trip on every single query.
        """
        if self._embeddings is not None:
            return True

        if not self.chunks:
            return False

        if self._embed_failed_at is not None:
            if time.monotonic() - self._embed_failed_at < _EMBED_RETRY_COOLDOWN_SECS:
                return False  # still in cooldown, don't retry yet

        embs = _embed_texts(self.chunks)
        if embs is None:
            self._embed_failed_at = time.monotonic()
            return False

        self._embeddings = embs
        self._embed_failed_at = None
        return True

    def _retrieve_top_k(self, question: str, k: int = 3) -> List[str]:
        """
        Retrieve top-k chunks using cosine similarity + a bounded, stopword-
        filtered lexical boost. Chunks below _MIN_RETRIEVAL_SCORE are dropped
        entirely rather than padding out to k with irrelevant context.
        """
        if not self.chunks:
            return []

        if not self._ensure_embeddings():
            # No embeddings available
            return []

        q_vec = _embed_text(question, task_type="retrieval_query")
        if q_vec is None:
            return []

        if self._embeddings is None:
            return []
        sims = _cosine_sim_matrix(q_vec, self._embeddings)
        if sims.size == 0:
            return []

        # Keyword boosting: favor chunks that contain important question
        # tokens, excluding stopwords, capped so lexical noise can't drown
        # out the semantic score.
        tokens = [
            t for t in re.findall(r"\w+", question.lower())
            if len(t) > 3 and t not in _STOPWORDS
        ]
        boosts = np.zeros_like(sims)

        for idx, ch in enumerate(self.chunks):
            lower = ch.lower()
            matches = sum(1 for t in tokens if t in lower)
            if matches:
                boosts[idx] = min(_BOOST_CAP, matches * _BOOST_PER_TOKEN)

        scores = sims + boosts
        order = np.argsort(scores)[::-1]
        top = [int(i) for i in order[:k] if scores[i] >= _MIN_RETRIEVAL_SCORE]
        return [self.chunks[i] for i in top]

    def _direct_facts_answer(self, question: str) -> Optional[str]:
        """
        Handle common recruiter questions without calling the LLM,
        using regex-based extraction over the full CV text.

        Deliberately narrow: each trigger matches an explicit, unambiguous
        phrasing. A bare "experience" or "technical" substring used to match
        almost any recruiter question ("does he have experience with X?",
        "what technical challenges has he solved?") and silently swallow it
        into a canned answer that never reached semantic retrieval — see
        tasks/lessons.md. Anything not matched here falls through to
        embeddings + Gemini.
        """
        q = question.lower()

        # Phone / contact
        if any(w in q for w in ["phone", "phone number", "contact number"]):
            phone = _extract_phone(self.cv_text)
            if phone:
                return f"Sergiu's phone number is {phone}."
            return "I couldn't find a phone number in Sergiu's CV."

        # Email
        if any(w in q for w in ["email", "e-mail"]):
            email = _extract_email(self.cv_text)
            if email:
                return f"Sergiu's email is {email}."
            return "I couldn't find an email address in Sergiu's CV."

        # Location / where based
        if any(w in q for w in ["location", "based", "city", "country"]):
            loc = _extract_location(self.cv_text)
            if loc:
                return f"Sergiu is based in {loc}."
            return "I couldn't find a clear location in Sergiu's CV."

        # Years of experience — narrow, explicit phrasing only. "experience"
        # alone is NOT a trigger; open-ended experience questions ("does he
        # have experience with RAG?") need semantic retrieval, not this
        # canned fallback.
        if re.search(r"\byears?\s+of\s+experience\b", q) or re.search(r"\bhow\s+(?:many\s+)?years\b", q):
            y = _extract_years_experience(self.cv_text)
            if y:
                return f"Sergiu has {y} of experience."
            return None  # no explicit figure in the CV — let retrieval try

        # Education
        if "education" in q or "degree" in q or "university" in q:
            edu = _extract_education(self.cv_text)
            if edu:
                bullets = "\n".join(f"- {e}" for e in edu)
                return "Here is what I found about Sergiu's education:\n\n" + bullets
            return "I couldn't find detailed education information in Sergiu's CV."

        # Skills / tech stack — narrow triggers only. "technical" alone used
        # to also match "what technical challenges has he solved?" and dump
        # the raw skills list instead of answering the actual question.
        if any(w in q for w in ["skill", "skills", "tech stack", "technologies", "technical skills"]):
            skills = _extract_skills(self.cv_text)
            if skills:
                bullets = "\n".join(f"- {s}" for s in skills)
                return "Here are Sergiu's technical skills:\n\n" + bullets
            return "I couldn't find technical skills information in Sergiu's CV."

        # Certifications
        if "certification" in q or "certifications" in q or "certificate" in q:
            certs = _extract_certifications(self.cv_text)
            if certs:
                bullets = "\n".join(f"- {c}" for c in certs)
                return "Sergiu holds the following certifications:\n\n" + bullets
            return "I couldn't find certifications in Sergiu's CV."

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
            return NOT_FOUND_MSG

        context = "\n\n---\n\n".join(relevant_chunks)

        # 3) If Gemini isn't configured, avoid dumping raw context; be conservative.
        if not _try_configure_client():
            return NOT_FOUND_MSG

        prompt = f"""
You are helping a recruiter understand a candidate's fit based ONLY on their CV.

CV content:
{context}

Question:
{question}

Instructions:
- Answer concisely and directly.
- Use ONLY facts from the CV content above.
- If the CV does not contain the answer, say: "{NOT_FOUND_MSG}"
""".strip()

        try:
            resp = _client.models.generate_content(model=GEN_MODEL, contents=prompt)  # type: ignore[union-attr]
            text = getattr(resp, "text", None)
            if text:
                return text.strip()
            # Fallback if no text field but call succeeded
            return NOT_FOUND_MSG
        except Exception:
            # Strict fallback: do not leak raw CV chunks
            return NOT_FOUND_MSG

    async def query_stream(self, question: str) -> AsyncGenerator[str, None]:
        """
        Async generator version of query().

        For direct-fact questions (phone, email, certs…): yields the full answer
        as a single chunk immediately (no Gemini call needed, no streaming benefit).

        For open questions backed by Gemini: streams token chunks as they arrive
        from generate_content_stream(), enabling sentence-level parallel TTS to
        fire before the full answer is assembled.

        Yields raw answer text (no "Here's what I found…" prefix — the caller
        adds that framing so cv_rag stays format-agnostic).

        Cancellation: if the caller stops iterating early (e.g. barge-in),
        the background thread's cancel_event is set so it stops relaying
        further Gemini stream chunks instead of running the stream to
        completion in the background regardless.
        """
        # 1) Direct fact extraction — yield immediately, no streaming
        direct = self._direct_facts_answer(question)
        if direct is not None:
            yield direct
            return

        # 2) Vector retrieval
        relevant_chunks = self._retrieve_top_k(question, k=3)
        if not relevant_chunks:
            yield NOT_FOUND_MSG
            return

        if not _try_configure_client():
            yield NOT_FOUND_MSG
            return

        context = "\n\n---\n\n".join(relevant_chunks)
        prompt = f"""You are helping a recruiter understand a candidate's fit based ONLY on their CV.

CV content:
{context}

Question:
{question}

Instructions:
- Answer concisely and directly.
- Use ONLY facts from the CV content above.
- If the CV does not contain the answer, say: "{NOT_FOUND_MSG}"
""".strip()

        # 3) Stream Gemini tokens via a thread-safe Queue bridge
        #    (google-genai SDK's generate_content_stream is sync-only)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        cancel_event = threading.Event()

        def _stream_worker() -> None:
            try:
                for chunk in _client.models.generate_content_stream(  # type: ignore[union-attr]
                    model=GEN_MODEL, contents=prompt
                ):
                    if cancel_event.is_set():
                        break
                    text = getattr(chunk, "text", None)
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
            except Exception:
                pass
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        threading.Thread(target=_stream_worker, daemon=True).start()

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            # Fires on normal completion AND on early close (GeneratorExit
            # when the caller stops iterating, e.g. barge-in) — stops the
            # background thread from continuing to consume/relay the Gemini
            # stream after nobody is listening.
            cancel_event.set()


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

                async def query_stream(self, q: str) -> AsyncGenerator[str, None]:
                    # Mirrors query() so the voice path (which only calls
                    # query_stream) degrades the same way as the text path
                    # instead of raising AttributeError mid-turn.
                    yield "CV RAG unavailable. Ensure cv.txt and GOOGLE_API_KEY are correctly configured."
            _rag = Dummy()  # type: ignore[assignment]
    return _rag
