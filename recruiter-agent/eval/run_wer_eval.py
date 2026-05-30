"""
eval/run_wer_eval.py — Word Error Rate (WER) evaluation for the STT pipeline.

Measures how accurately Deepgram nova-2 transcribes text that has been
synthesised by Google Neural2-D TTS — i.e. the round-trip accuracy of
the voice pipeline under ideal conditions.

Pipeline
--------
  Reference text
      → Google Cloud TTS (Neural2-D, MP3)
      → Deepgram nova-2 prerecorded REST API
      → Hypothesis transcript
      → WER = word-level Levenshtein distance / reference word count

Test phrases
------------
  Covers the range of inputs the recruiter agent handles:
  - Short STT commands ("next", "ats summary")
  - Role/criteria descriptions (technical vocabulary)
  - Recruiter questions (contact details, experience)
  - Numbers and mixed alphanumeric (latency figures)

Usage
-----
  # Requires env vars:
  #   GOOGLE_APPLICATION_CREDENTIALS or gcloud auth application-default login
  #   DEEPGRAM_API_KEY
  python eval/run_wer_eval.py

Output
------
  Color-coded table:
    GREEN  WER < 5%   (excellent)
    YELLOW WER 5-15%  (acceptable)
    RED    WER > 15%  (poor)
  Summary line: average WER + pass rate (<5% threshold)
"""
from __future__ import annotations

import os
import sys
import time

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Test corpus
# ---------------------------------------------------------------------------

TEST_PHRASES = [
    # Short nav commands — most prone to Deepgram punctuation / homophone errors
    ("next project please", "short_command"),
    ("another one", "short_command"),
    ("ats summary", "short_command"),
    # Role + criteria descriptions
    ("I am hiring for a senior machine learning engineer", "role"),
    ("We need someone with production RAG and ownership experience", "criteria"),
    ("Lead AI engineer with voice AI and low latency requirements", "role_with_criteria"),
    # Recruiter factual questions
    ("What is his phone number and email address", "cv_question"),
    ("How many years of experience does he have", "cv_question"),
    ("Does he have any certifications or degrees", "cv_question"),
    # Technical vocabulary
    ("Deepgram nova two STT with endpointing 150 milliseconds", "technical"),
    ("OpenTelemetry tracing with Langfuse observability", "technical"),
    ("context precision 1.0 and context recall 1.0 on RAGAS", "technical"),
    # Numbers + mixed
    ("600 milliseconds time to first audio on Cloud Run", "numbers"),
    ("approximately 35 milliseconds agent latency", "numbers"),
]

# ---------------------------------------------------------------------------
# WER calculation — word-level Levenshtein distance
# ---------------------------------------------------------------------------

def _normalise(text: str) -> list[str]:
    """Lowercase, strip punctuation, split to words."""
    import re
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """
    Standard WER = (S + D + I) / N
    where S=substitutions, D=deletions, I=insertions, N=reference word count.
    Returns 0.0 for empty reference.
    """
    ref = _normalise(reference)
    hyp = _normalise(hypothesis)

    if not ref:
        return 0.0

    n_ref = len(ref)
    n_hyp = len(hyp)

    # DP table: d[i][j] = edit distance between ref[:i] and hyp[:j]
    d = [[0] * (n_hyp + 1) for _ in range(n_ref + 1)]
    for i in range(n_ref + 1):
        d[i][0] = i
    for j in range(n_hyp + 1):
        d[0][j] = j

    for i in range(1, n_ref + 1):
        for j in range(1, n_hyp + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,       # deletion
                d[i][j - 1] + 1,       # insertion
                d[i - 1][j - 1] + cost, # substitution
            )

    return d[n_ref][n_hyp] / n_ref


# ---------------------------------------------------------------------------
# TTS — Google Neural2-D MP3
# ---------------------------------------------------------------------------

def _tts_phrase(text: str) -> bytes:
    """Synthesise *text* to MP3 bytes via Google Neural2-D TTS."""
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-D",
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.05,
        ),
    )
    return response.audio_content


# ---------------------------------------------------------------------------
# STT — Deepgram nova-2 prerecorded REST
# ---------------------------------------------------------------------------

def _stt_audio(audio_bytes: bytes) -> str:
    """Transcribe MP3 bytes via Deepgram nova-2 prerecorded API."""
    from deepgram import DeepgramClient, PrerecordedOptions

    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY not set")

    client = DeepgramClient(api_key)
    options = PrerecordedOptions(
        model="nova-2",
        language="en-US",
        smart_format=True,
        punctuate=True,
    )

    source = {"buffer": audio_bytes, "mimetype": "audio/mpeg"}
    response = client.listen.rest.v("1").transcribe_file(source, options)

    try:
        return response.results.channels[0].alternatives[0].transcript
    except (AttributeError, IndexError, TypeError):
        # Fallback for different SDK response shapes
        try:
            return response["results"]["channels"][0]["alternatives"][0]["transcript"]
        except (KeyError, TypeError, IndexError):
            return ""


# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"


def _colour_wer(wer: float) -> str:
    pct = f"{wer * 100:.1f}%"
    if wer < 0.05:
        return f"{_GREEN}{pct}{_RESET}"
    if wer < 0.15:
        return f"{_YELLOW}{pct}{_RESET}"
    return f"{_RED}{pct}{_RESET}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_wer_eval() -> None:
    print(f"\n{_BOLD}WER Evaluation — Google Neural2-D TTS → Deepgram nova-2 STT{_RESET}")
    print(f"{'Phrase':<50} {'Category':<18} {'WER':>6}  Hypothesis\n" + "-" * 110)

    results = []
    for reference, category in TEST_PHRASES:
        try:
            t0 = time.time()
            audio = _tts_phrase(reference)
            tts_ms = (time.time() - t0) * 1000

            t1 = time.time()
            hypothesis = _stt_audio(audio)
            stt_ms = (time.time() - t1) * 1000

            wer = word_error_rate(reference, hypothesis)
            results.append({"reference": reference, "hypothesis": hypothesis,
                             "wer": wer, "category": category,
                             "tts_ms": tts_ms, "stt_ms": stt_ms})

            ref_display = reference if len(reference) <= 48 else reference[:45] + "..."
            hyp_display = hypothesis if len(hypothesis) <= 40 else hypothesis[:37] + "..."
            print(
                f"{ref_display:<50} {category:<18} {_colour_wer(wer):>6+7}  {hyp_display}"
            )

        except Exception as exc:
            print(f"{reference[:48]:<50} {category:<18} {'ERROR':>6}  {exc}")
            results.append({"reference": reference, "hypothesis": "", "wer": 1.0,
                             "category": category, "tts_ms": 0, "stt_ms": 0})

    # Summary
    if results:
        avg_wer  = sum(r["wer"] for r in results) / len(results)
        pass_cnt = sum(1 for r in results if r["wer"] < 0.05)
        pass_rate = pass_cnt / len(results) * 100
        avg_tts  = sum(r["tts_ms"] for r in results) / len(results)
        avg_stt  = sum(r["stt_ms"] for r in results) / len(results)

        print("\n" + "-" * 110)
        print(
            f"{_BOLD}Summary{_RESET}  "
            f"avg WER: {_colour_wer(avg_wer)}  "
            f"pass rate (<5%): {_GREEN if pass_rate >= 90 else _YELLOW}"
            f"{pass_cnt}/{len(results)} ({pass_rate:.0f}%){_RESET}  "
            f"avg TTS: {avg_tts:.0f}ms  avg STT: {avg_stt:.0f}ms"
        )
        print()


if __name__ == "__main__":
    run_wer_eval()
