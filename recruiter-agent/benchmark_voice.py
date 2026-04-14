"""
Voice pipeline latency benchmark.

Measures each stage independently:
  1. Deepgram STT  — POST a WAV file → transcript latency
  2. Agent turn    — POST to /chat   → LLM latency
  3. ElevenLabs TTS — POST text      → first-byte latency + full stream latency

Usage:
  py -3.11 benchmark_voice.py https://recruiter-agent-969006882005.europe-west1.run.app

Set env vars before running:
  $env:DEEPGRAM_API_KEY   = "..."
  $env:ELEVENLABS_API_KEY = "..."
"""

from __future__ import annotations

import json
import math
import os
import statistics
import struct
import sys
import time
import wave

import asyncio

import httpx
import websockets as ws_lib

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
CHAT_URL = f"{BASE_URL}/chat"

GCP_PROJECT = "recruiter-sergiu-260213"

def _read_secret(name: str) -> str:
    """Read latest version of a secret from Secret Manager."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        resource = f"projects/{GCP_PROJECT}/secrets/{name}/versions/latest"
        resp = client.access_secret_version(request={"name": resource})
        return resp.payload.data.decode("utf-8").strip()
    except Exception as exc:
        return os.environ.get(name, "")

DEEPGRAM_KEY = os.environ.get("DEEPGRAM_API_KEY") or _read_secret("DEEPGRAM_API_KEY")
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY") or _read_secret("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

N_RUNS = 5  # repetitions per stage

# Test phrases for agent
TEST_MESSAGES = [
    "I'm hiring a senior ML engineer who has shipped RAG systems to production",
    "Looking for an AI engineer with strong leadership and ownership",
    "What are Sergiu's main technical skills?",
]

# ---------------------------------------------------------------------------
# Generate a synthetic 2s speech-like WAV (sine sweep) for Deepgram test
# ---------------------------------------------------------------------------

def _make_test_wav(path: str, duration_s: float = 2.0, sample_rate: int = 16000) -> None:
    n = int(sample_rate * duration_s)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = []
        for i in range(n):
            # Sweep 200–2000 Hz — produces a recognisable tone Deepgram can process
            freq = 200 + 1800 * (i / n)
            sample = int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
            frames.append(struct.pack("<h", sample))
        wf.writeframes(b"".join(frames))


# ---------------------------------------------------------------------------
# Stage 1: Deepgram STT
# ---------------------------------------------------------------------------

def bench_deepgram(wav_path: str) -> list[float]:
    if not DEEPGRAM_KEY:
        print("  DEEPGRAM_API_KEY not set — skipping")
        return []

    # Use Deepgram's hosted sample audio — real speech, avoids local file issues
    # Note: batch REST latency (~500–1500ms) is NOT the streaming WebSocket latency.
    # Real pipeline uses WebSocket streaming → speech_final fires at ~150–300ms.
    url = "https://api.deepgram.com/v1/listen?model=nova-2&language=en-US&punctuate=true"
    headers = {"Authorization": f"Token {DEEPGRAM_KEY}", "Content-Type": "application/json"}
    body = {"url": "https://static.deepgram.com/examples/Bueller-Life-moves-pretty-fast.wav"}

    latencies = []
    for i in range(N_RUNS):
        t0 = time.perf_counter()
        resp = httpx.post(url, json=body, headers=headers, timeout=15)
        elapsed = (time.perf_counter() - t0) * 1000
        if resp.status_code == 200:
            data = resp.json()
            transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
            latencies.append(elapsed)
            print(f"  run {i+1}: {elapsed:.0f}ms  transcript='{transcript[:60]}'")
        else:
            print(f"  run {i+1}: ERROR {resp.status_code} {resp.text[:100]}")

    print("  NOTE: batch REST latency shown; streaming WebSocket ~150–300ms in production")
    return latencies


# ---------------------------------------------------------------------------
# Stage 2: Agent turn (/chat)
# ---------------------------------------------------------------------------


def bench_agent() -> list[float]:
    latencies = []
    for i, msg in enumerate(TEST_MESSAGES):
        t0 = time.perf_counter()
        resp = httpx.post(
            CHAT_URL,
            json={"message": msg, "session_id": f"bench-{i}", "state": None},
            timeout=20,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        if resp.status_code == 200:
            reply = resp.json().get("reply", "")[:60]
            latencies.append(elapsed)
            print(f"  msg {i+1}: {elapsed:.0f}ms  reply='{reply}'")
        else:
            print(f"  msg {i+1}: ERROR {resp.status_code}")

    return latencies


# ---------------------------------------------------------------------------
# Stage 3: ElevenLabs TTS (first-byte + full stream)
# ---------------------------------------------------------------------------

def bench_elevenlabs() -> tuple[list[float], list[float]]:
    if not ELEVENLABS_KEY:
        print("  ELEVENLABS_API_KEY not set — skipping")
        return [], []

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
    headers = {"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"}
    text = "Sergiu has strong production RAG experience and a solid ownership track record."

    first_byte_latencies = []
    full_stream_latencies = []

    for i in range(N_RUNS):
        payload = {"text": text, "model_id": "eleven_turbo_v2", "output_format": "mp3_44100_128"}
        t0 = time.perf_counter()
        first_byte_ms = None
        total_bytes = 0

        with httpx.stream("POST", url, json=payload, headers=headers, timeout=30) as resp:
            if resp.status_code != 200:
                body_bytes = resp.read()
                print(f"  run {i+1}: ERROR {resp.status_code} {body_bytes[:200]}")
                continue
            for chunk in resp.iter_bytes(4096):
                if chunk:
                    if first_byte_ms is None:
                        first_byte_ms = (time.perf_counter() - t0) * 1000
                    total_bytes += len(chunk)

        full_ms = (time.perf_counter() - t0) * 1000
        first_byte_latencies.append(first_byte_ms or 0)
        full_stream_latencies.append(full_ms)
        print(f"  run {i+1}: first_byte={first_byte_ms:.0f}ms  full={full_ms:.0f}ms  bytes={total_bytes}")

    return first_byte_latencies, full_stream_latencies


# ---------------------------------------------------------------------------
# Stage 3b: Google Cloud TTS (fallback)
# ---------------------------------------------------------------------------

def bench_google_tts() -> tuple[list[float], list[float]]:
    try:
        from google.cloud import texttospeech
    except ImportError:
        print("  google-cloud-texttospeech not installed — uv pip install google-cloud-texttospeech")
        return [], []
    try:
        from google.api_core.client_options import ClientOptions
        client = texttospeech.TextToSpeechClient(
            client_options=ClientOptions(quota_project_id=GCP_PROJECT)
        )
    except Exception as exc:
        print(f"  Google TTS client init failed: {exc}")
        return [], []

    text = "Sergiu has strong production RAG experience and a solid ownership track record."
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    first_byte_latencies = []
    full_latencies = []

    for i in range(N_RUNS):
        try:
            import concurrent.futures
            t0 = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(client.synthesize_speech,
                    input=synthesis_input, voice=voice, audio_config=audio_config)
                response = future.result(timeout=8)
            elapsed = (time.perf_counter() - t0) * 1000
            first_byte_latencies.append(elapsed)
            full_latencies.append(elapsed)
            print(f"  run {i+1}: {elapsed:.0f}ms  bytes={len(response.audio_content)}")
        except concurrent.futures.TimeoutError:
            print(f"  run {i+1}: TIMEOUT (>8s) — skipping")
        except Exception as exc:
            print(f"  run {i+1}: ERROR {exc}")

    return first_byte_latencies, full_latencies


# ---------------------------------------------------------------------------
# Stage 4: E2E WebSocket benchmark (agent + TTS)
# ---------------------------------------------------------------------------

BENCH_MESSAGES = [
    "I'm hiring a senior ML engineer who has shipped RAG systems to production",
    "Looking for an AI engineer with strong leadership and ownership mindset",
    "What are Sergiu's main technical skills?",
]

async def bench_e2e() -> list[float]:
    ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/voice/bench"
    latencies = []

    for i, msg in enumerate(BENCH_MESSAGES):
        try:
            url = ws_url + f"?session_id=bench-e2e-{i}-{int(time.time())}"
            async with ws_lib.connect(url, open_timeout=10) as sock:
                t0 = time.perf_counter()
                await sock.send(json.dumps({"transcript": msg}))

                audio_bytes = 0
                reply_text = ""
                first_audio_ms = None
                async for raw in sock:
                    if isinstance(raw, bytes):
                        if first_audio_ms is None:
                            first_audio_ms = (time.perf_counter() - t0) * 1000
                        audio_bytes += len(raw)
                    else:
                        data = json.loads(raw)
                        if data.get("type") == "reply":
                            reply_text = data.get("text", "")[:60]
                        elif data.get("type") == "audio_end":
                            total_ms = (time.perf_counter() - t0) * 1000
                            latencies.append(total_ms)
                            print(f"  msg {i+1}: first_audio={first_audio_ms:.0f}ms  total={total_ms:.0f}ms  audio={audio_bytes}b")
                            break
                        elif data.get("type") == "error":
                            print(f"  msg {i+1}: ERROR {data.get('message')}")
                            break
        except Exception as exc:
            print(f"  msg {i+1}: ERROR {exc}")

    return latencies


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _stats(label: str, values: list[float]) -> None:
    if not values:
        return
    print(f"  {label}: p50={statistics.median(values):.0f}ms  "
          f"p95={sorted(values)[int(len(values)*0.95)-1]:.0f}ms  "
          f"min={min(values):.0f}ms  max={max(values):.0f}ms")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\nBenchmark target: {BASE_URL}")
    print(f"Runs per stage:   {N_RUNS}\n")

    results: dict = {}

    # --- Deepgram ---
    print("=" * 50)
    print("Stage 1: Deepgram STT (batch REST, nova-2)")
    wav_path = os.path.join(os.environ.get("TEMP", "."), "bench_test.wav")
    _make_test_wav(wav_path)
    dg_latencies = bench_deepgram(wav_path)
    results["deepgram_stt_ms"] = dg_latencies
    _stats("Deepgram", dg_latencies)

    # --- Agent ---
    print("\n" + "=" * 50)
    print("Stage 2: Agent turn (POST /chat)")
    agent_latencies = bench_agent()
    results["agent_turn_ms"] = agent_latencies
    _stats("Agent  ", agent_latencies)

    # --- ElevenLabs ---
    print("\n" + "=" * 50)
    print("Stage 3: ElevenLabs TTS stream (eleven_turbo_v2)")
    fb_latencies, full_latencies = bench_elevenlabs()
    results["tts_first_byte_ms"] = fb_latencies
    results["tts_full_stream_ms"] = full_latencies
    _stats("TTS first-byte", fb_latencies)
    _stats("TTS full      ", full_latencies)

    # --- End-to-end estimate ---
    print("\n" + "=" * 50)
    print("End-to-end estimate (STT + Agent + TTS first-byte)")
    if dg_latencies and agent_latencies and fb_latencies:
        e2e = [
            statistics.median(dg_latencies) +
            statistics.median(agent_latencies) +
            statistics.median(fb_latencies)
        ]
        print(f"  estimated P50 end-to-end: {e2e[0]:.0f}ms")

    # --- Google Cloud TTS (fallback if ElevenLabs blocked) ---
    if not fb_latencies:
        print("\n" + "=" * 50)
        print("Stage 3b: Google Cloud TTS (fallback)")
        fb_latencies, full_latencies = bench_google_tts()
        results["tts_first_byte_ms"] = fb_latencies
        results["tts_full_stream_ms"] = full_latencies
        _stats("TTS first-byte", fb_latencies)
        _stats("TTS full      ", full_latencies)

    # --- E2E WebSocket (agent + TTS, real deployed stack) ---
    print("\n" + "=" * 50)
    print("Stage 4: E2E WebSocket — agent + TTS (Deepgram excluded)")
    e2e_latencies = asyncio.run(bench_e2e())
    results["e2e_agent_tts_ms"] = e2e_latencies
    _stats("E2E (agent+TTS)", e2e_latencies)
    if e2e_latencies:
        full_e2e = statistics.median(e2e_latencies) + 200  # +200ms Deepgram streaming estimate
        print(f"  Full E2E estimate (incl. ~200ms Deepgram streaming): {full_e2e:.0f}ms")

    # Save results
    out_path = "benchmark_voice_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")
