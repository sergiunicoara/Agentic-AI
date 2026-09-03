"""Render the two-minute recruiter-agent walkthrough video."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from textwrap import wrap

from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "two-minute-project-walkthrough.mp4"
WORK = ROOT / "docs" / "walkthrough-render"
WIDTH, HEIGHT = 1920, 1080

SCENES = [
    (
        "01  THE PRODUCT",
        "AI RECRUITER",
        "A voice-first agent that represents a candidate portfolio in a live recruiter conversation.",
        "Ask a question by voice. Get a grounded project recommendation.",
        "This AI recruiter represents a candidate's portfolio in a live conversation. A recruiter asks by voice, and the system finds the best projects and explains the evidence.",
    ),
    (
        "02  THE FLOW",
        "FROM VOICE TO EVIDENCE",
        "voice input  ->  transcript  ->  role extraction  ->  criteria parsing  ->  project ranking  ->  CV Q&A  ->  spoken answer",
        "Each stage is explicit, traceable, and independently measurable.",
        "Audio enters a persistent WebSocket. Deepgram Nova-2 creates the transcript. A deterministic pipeline extracts the role, normalizes criteria, ranks projects, and routes CV questions to RAG. The answer streams back as audio.",
    ),
    (
        "03  THE STACK",
        "PRODUCTION ARCHITECTURE",
        "FastAPI + Python       Google Cloud Run       Deepgram Nova-2       Gemini       Neural2-D TTS       Redis",
        "Langfuse traces agent and judge calls. OpenTelemetry sends spans to Cloud Trace.",
        "The backend is Python and FastAPI on Google Cloud Run. Deepgram handles STT, Gemini handles CV retrieval and generation, and Google Neural2-D handles TTS. Redis stores sessions, with SQLite fallback. Langfuse and OpenTelemetry provide tracing.",
    ),
    (
        "04  RANKING + MEMORY",
        "PREDICTABLE MATCHING",
        "Role: Production Voice AI Engineer\n\nMatched evidence\n[voice_ai]  [low_latency]  [observability]  [production_rag]",
        "Session IDs preserve context across turns. Trajectory logs preserve the decision path.",
        "Ranking is predictable: normalized role criteria are compared with project tags and summaries. A session ID preserves context, while trajectory logs capture the message, routing decision, evidence, answer, timings, and validation result.",
    ),
    (
        "05  QUALITY CONTROL",
        "RECRUITER AGENT  ->  MCP  ->  CRITIC AGENT",
        "LLM judge scores:  faithfulness  |  relevancy  |  factuality\n\nGolden dataset: expected role + criteria + answer quality",
        "A2A describes the handoff. MCP provides the structured tool contract.",
        "After each response, the recruiter hands the turn to a critic through A2A. MCP defines the tool call to the judge, which scores faithfulness, relevancy, and factuality. Golden cases verify routing and answer quality before deployment.",
    ),
    (
        "06  PRODUCTION INCIDENT",
        "WHAT BROKE",
        "Deepgram rejected DEEPGRAM_API_KEY\nHTTP 401\n\nWebSocket closed: code 1006",
        "The variable existed, but the active Cloud Run secret value was malformed.",
        "One production issue caused HTTP 401 and WebSocket code 1006. The variable existed, but the active Cloud Run secret was malformed. I created a correct secret version, redeployed, and verified the live voice endpoint.",
    ),
    (
        "07  MEASUREMENT",
        "MEASURED, NOT ESTIMATED",
        "~241 ms   first audio (p50)\n~441 ms   full E2E estimate\n\n67 tests passed",
        "Measured on the live /voice/bench transcript-to-audio path. Deepgram batch STT is measured separately.",
        "The result is a measured voice pipeline with memory, traceable decisions, and automated quality checks.",
    ),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"
    return ImageFont.truetype(name, size)


def draw_scene(index: int, scene: tuple[str, str, str, str, str]) -> Path:
    label, title, body, footer, _ = scene
    image = Image.new("RGB", (WIDTH, HEIGHT), (10, 18, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 18), fill=(44, 204, 167))
    draw.ellipse((1450, -280, 2150, 420), fill=(22, 67, 91))
    draw.ellipse((-280, 800, 450, 1450), fill=(18, 49, 70))

    draw.text((120, 100), label, font=font(30, True), fill=(96, 223, 190))
    draw.text((120, 190), title, font=font(76, True), fill=(240, 246, 250))
    draw.line((120, 320, 1800, 320), fill=(51, 82, 101), width=2)

    y = 410
    for paragraph in body.split("\n"):
        if not paragraph:
            y += 30
            continue
        lines = wrap(paragraph, width=54 if len(paragraph) > 90 else 46)
        for line in lines:
            draw.text((150, y), line, font=font(48, True), fill=(240, 246, 250))
            y += 67

    draw.rounded_rectangle((120, 860, 1800, 970), radius=20, fill=(17, 37, 52), outline=(44, 204, 167), width=2)
    for i, line in enumerate(wrap(footer, width=92)):
        draw.text((155, 885 + i * 34), line, font=font(26), fill=(190, 210, 218))

    path = WORK / f"scene-{index:02d}.png"
    image.save(path)
    return path


def run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("scene-*.mp4"):
        old.unlink()
    for old in WORK.glob("scene-*.mp3"):
        old.unlink()

    clips: list[Path] = []
    for index, scene in enumerate(SCENES, start=1):
        image = draw_scene(index, scene)
        audio = WORK / f"scene-{index:02d}.mp3"
        gTTS(scene[4], lang="en", slow=False).save(str(audio))
        clip = WORK / f"scene-{index:02d}.mp4"
        run("ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio), "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", "-shortest", str(clip))
        clips.append(clip)

    concat = WORK / "concat.txt"
    concat.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
    raw = WORK / "walkthrough-raw.mp4"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(raw))
    # Keep the finished narration close to the requested two-minute runtime.
    run(
        "ffmpeg", "-y", "-i", str(raw),
        "-filter_complex", "[0:v]setpts=PTS/1.18[v];[0:a]atempo=1.18[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(OUT),
    )
    raw.unlink(missing_ok=True)
    print(f"Created {OUT}")


if __name__ == "__main__":
    main()
