from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from opentelemetry import trace
from pydantic import BaseModel

from .agent import agent_turn
from .guardrails import check_topic, redact_pii
from .outbound import get_campaign_manager, outbound_callback_handler, outbound_twiml_handler
from .phone import phone_stream_handler, phone_twiml_handler
from .voice import voice_bench_handler, voice_handler
from .webrtc import webrtc_cleanup_handler, webrtc_offer_handler
from .critic_agent import get_critic_session_summary, validate_turn
from .mcp import call_mcp_tool, list_mcp_tools
from .models import ChatRequest, ChatResponse, State
from .quality import StepKind, Trajectory
from .session_store import load_session, save_session, session_store_info
from .telemetry.langfuse_setup import flush as langfuse_flush, init_langfuse
from .telemetry.logging import configure_logging
from .telemetry.tracing import configure_tracer

logger = logging.getLogger(__name__)

SERVICE_NAME = "recruiter-agent"

app = FastAPI(title="Recruiter Agent API", version="1.0.0")

# CORS — allow_credentials requires explicit origins; keep open for this public demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Startup: wire OpenTelemetry tracing + structured logging
# ------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    configure_logging(SERVICE_NAME)
    configure_tracer(
        SERVICE_NAME,
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )
    init_langfuse()  # initialise early so first request isn't slow
    logger.info("Recruiter Agent started | service=%s", SERVICE_NAME)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    langfuse_flush()  # flush any pending Langfuse events


# ------------------------------------------------------------------
# Frontend serving
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@app.get("/", include_in_schema=False)
async def serve_frontend_root():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise RuntimeError(f"Frontend index.html not found at {index_path}")
    return FileResponse(index_path)


# NOTE: the frontend catch-all GET route is registered at the BOTTOM of this
# file — Starlette matches routes in registration order, so registering
# /{path:path} here would shadow every GET API route defined below it
# (/health, /mcp/tools, /session/{id}/summary, ...), silently returning
# index.html instead of JSON.


# ------------------------------------------------------------------
# /chat — main recruiter agent entrypoint
# ------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint with full trajectory logging and OTel tracing.

    Every turn emits:
    - An OTel span with session/role/criteria attributes
    - A structured trajectory log (user step + agent step with timestamps)
    """
    session_id = req.session_id or "default-session"
    tracer = trace.get_tracer(SERVICE_NAME)

    with tracer.start_as_current_span("chat.turn") as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("source", req.source or "")
        span.set_attribute("message_length", len(req.message))

        # P4 — Topic enforcement: deflect off-topic messages before they reach the agent
        is_on_topic, deflection = check_topic(req.message)
        if not is_on_topic:
            return ChatResponse(
                reply=deflection,
                state=req.state or {},
                session_id=session_id,
            )

        # Restore state — client payload takes priority; SQLite is the fallback.
        # This means a page-refresh or lost client state never resets the session.
        if req.state:
            incoming = req.state if isinstance(req.state, dict) else dict(req.state)
            state = State(
                source=incoming.get("source"),
                role=incoming.get("role"),
                criteria=incoming.get("criteria", []),
                memory=incoming.get("memory", []),
                extra=incoming.get("extra", {}),
            )
        else:
            state = load_session(session_id) or State(source=req.source)

        # Trajectory: log user turn — PII redacted before writing to traces/logs
        safe_message = redact_pii(req.message)
        trajectory = Trajectory(session_id=session_id)
        trajectory.add(
            StepKind.user,
            safe_message,
            meta={"source": req.source, "session_id": session_id},
        )

        with tracer.start_as_current_span("agent.turn"):
            result = agent_turn(state, req.message)

        if result is None:
            raise RuntimeError("agent_turn returned None")

        reply = result.get("reply")
        new_state = result.get("state")

        if reply is None:
            raise RuntimeError("agent_turn returned dict without 'reply'")

        span.set_attribute("role", new_state.role or "")
        span.set_attribute("reply_length", len(reply))

        # Trajectory: log agent turn
        trajectory.add(
            StepKind.agent,
            reply,
            meta={
                "role": new_state.role,
                "criteria": new_state.criteria,
                "memory_events": len(new_state.memory),
            },
        )

        # Emit full trajectory to structured logs
        logger.info(
            "agent_trajectory | session=%s role=%s turns=%d",
            session_id,
            new_state.role or "unknown",
            trajectory.to_dict()["turn_count"],
            extra={"json_fields": trajectory.to_dict()},
        )

    # Persist to SQLite so voice and future turns can recover even if client loses state
    try:
        save_session(session_id, new_state)
    except Exception as exc:
        logger.warning("session save failed session=%s error=%s", session_id, exc)

    # Strip project objects from client payload — they're large and cause the
    # round-trip state to bloat / get dropped, resetting deep_dive_index to 0.
    # The index is preserved; projects are reloaded from cache on the next turn.
    # SQLite gets the full state (projects included) for voice session recovery.
    client_extra = {k: v for k, v in new_state.extra.items() if k != "projects"}
    safe_state = {
        "source": new_state.source,
        "role": new_state.role,
        "criteria": new_state.criteria,
        "memory": new_state.memory,
        "extra": client_extra,
    }

    return ChatResponse(
        reply=reply,
        state=safe_state,
        session_id=session_id,
    )


# ------------------------------------------------------------------
# /mcp/tools — discover available MCP tools
# ------------------------------------------------------------------

@app.get("/mcp/tools")
async def mcp_list_tools_endpoint() -> Dict[str, Any]:
    """
    Returns the registry of MCP-style tools with JSON input/output schemas.
    External agents use this for tool discovery before making /mcp/call requests.
    """
    return {"tools": list_mcp_tools()}


# ------------------------------------------------------------------
# /mcp/call — dispatch a named tool call
# ------------------------------------------------------------------

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


@app.post("/mcp/call")
async def mcp_call_endpoint(req: MCPCallRequest) -> Dict[str, Any]:
    """
    MCP-inspired Agent-to-Agent dispatch endpoint.

    Accepts a named tool call with JSON arguments and returns a structured result.
    Used by the eval runner and critic agent for automated validation.
    """
    tracer = trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span("mcp.call") as span:
        span.set_attribute("tool", req.tool)
        try:
            result = call_mcp_tool(req.tool, req.arguments)
            return {"tool": req.tool, "result": result}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            logger.exception("MCP tool call failed: tool=%s error=%s", req.tool, exc)
            raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# /a2a/validate — Critic Agent A2A validation endpoint
# ------------------------------------------------------------------

class A2AValidateRequest(BaseModel):
    user_message: str
    agent_reply: str
    role: Optional[str] = None
    criteria: List[str] = []
    session_id: str = "default"


@app.post("/a2a/validate")
async def a2a_validate_endpoint(req: A2AValidateRequest) -> Dict[str, Any]:
    """
    Agent-to-Agent validation endpoint.

    Invokes the Critic Agent, which calls the LLM judge via the MCP tool
    interface and returns a structured verdict (PASS/FAIL) with:
    - Multi-metric scores (faithfulness, relevancy, factuality)
    - Concrete recommended actions
    - Running session aggregate metrics
    """
    tracer = trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span("a2a.validate") as span:
        span.set_attribute("session_id", req.session_id)
        span.set_attribute("role", req.role or "")

        result = validate_turn(
            user_message=req.user_message,
            agent_reply=req.agent_reply,
            role=req.role,
            criteria=req.criteria,
            session_id=req.session_id,
        )

        span.set_attribute("verdict", result.get("verdict", ""))
        span.set_attribute("score", result.get("score", 0.0))

    return result


# ------------------------------------------------------------------
# /a2a/summary — Critic session aggregate metrics
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# /webrtc — Direct browser WebRTC (no Twilio, SDP/ICE negotiation via aiortc)
# ------------------------------------------------------------------

class WebRTCOfferRequest(BaseModel):
    sdp: str
    type: str           # "offer"
    session_id: str = "default"


@app.post("/webrtc/offer")
async def webrtc_offer_endpoint(req: WebRTCOfferRequest) -> Dict[str, Any]:
    """
    WebRTC SDP offer → answer (full ICE, non-trickle).

    Browser flow:
      const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      pc.addTrack(stream.getAudioTracks()[0], stream);
      const dc = pc.createDataChannel('agent');
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const res = await fetch('/webrtc/offer', { method: 'POST',
        body: JSON.stringify({ sdp: pc.localDescription.sdp,
                               type: pc.localDescription.type, session_id: 'xyz' }) });
      const answer = await res.json();
      await pc.setRemoteDescription(answer);
      // data channel 'agent' carries JSON events + binary TTS MP3 chunks
    """
    return await webrtc_offer_handler(req.sdp, req.type, req.session_id)


@app.delete("/webrtc/{pc_id}")
async def webrtc_cleanup_endpoint(pc_id: str) -> Dict[str, Any]:
    """Explicit peer connection cleanup. Call on page unload / session end."""
    return await webrtc_cleanup_handler(pc_id)


# ------------------------------------------------------------------
# /outbound — Outbound call campaign manager (PSTN via Twilio)
# ------------------------------------------------------------------

class CampaignCreateRequest(BaseModel):
    name: str
    numbers: List[str]
    role: str
    criteria: List[str] = []
    max_concurrent: int = 3


@app.post("/outbound/campaign")
async def create_campaign_endpoint(req: CampaignCreateRequest) -> Dict[str, Any]:
    """
    Create an outbound call campaign.
    Numbers must be E.164 format (e.g. +12125551234).
    Compliance: opt-out list and TCPA calling hours enforced automatically.
    """
    mgr = get_campaign_manager()
    campaign = mgr.create_campaign(
        name=req.name,
        numbers=req.numbers,
        role=req.role,
        criteria=req.criteria,
        max_concurrent=req.max_concurrent,
    )
    return campaign.aggregate()


@app.post("/outbound/campaign/{campaign_id}/start")
async def start_campaign_endpoint(campaign_id: str) -> Dict[str, Any]:
    """Start dialing — respects max_concurrent gate and calling-hours compliance."""
    return await get_campaign_manager().start_campaign(campaign_id)


@app.post("/outbound/campaign/{campaign_id}/pause")
async def pause_campaign_endpoint(campaign_id: str) -> Dict[str, Any]:
    ok = get_campaign_manager().pause_campaign(campaign_id)
    return {"paused": ok, "campaign_id": campaign_id}


@app.get("/outbound/campaign/{campaign_id}")
async def get_campaign_endpoint(campaign_id: str) -> Dict[str, Any]:
    mgr = get_campaign_manager()
    campaign = mgr.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id!r} not found")
    return campaign.aggregate()


@app.post("/outbound/opt-out")
async def opt_out_endpoint(phone_number: str) -> Dict[str, Any]:
    """Add a number to the permanent opt-out list. No further calls will be attempted."""
    get_campaign_manager().add_opt_out(phone_number)
    return {"opted_out": True, "phone_number": phone_number}


@app.post("/outbound/callback")
async def outbound_callback_endpoint(request: Request) -> Dict[str, Any]:
    """
    Twilio status callback — updates call records (ringing/answered/completed/failed).
    Configure in Twilio: status_callback_url = https://your-service/outbound/callback
    """
    form = await request.form()
    return await outbound_callback_handler(dict(form))


@app.post("/phone/twiml/outbound")
async def outbound_twiml_endpoint(request: Request, session_id: str = "outbound") -> Response:
    """
    TwiML for outbound calls — includes GDPR/TCPA compliance disclosure
    before connecting to the Media Streams agent WebSocket.
    """
    xml = await outbound_twiml_handler(request, session_id)
    return Response(content=xml, media_type="application/xml")


@app.get("/outbound/status")
async def outbound_status_endpoint() -> Dict[str, Any]:
    """Live concurrency stats + per-campaign aggregates."""
    return get_campaign_manager().status()


# ------------------------------------------------------------------
# /phone/twiml  — Twilio webhook: returns TwiML directing call to /phone/stream
# /phone/stream — Twilio Media Streams WebSocket: PSTN → mulaw → Deepgram → TTS
# ------------------------------------------------------------------

@app.post("/phone/twiml", include_in_schema=True)
async def phone_twiml_endpoint(request: Request) -> Response:
    """
    Twilio calls this when an inbound call is received.
    Configure in Twilio Console: Phone Number → Voice → A CALL COMES IN → Webhook (POST).
    Returns TwiML that connects the call to the Media Streams WebSocket.
    """
    xml = await phone_twiml_handler(request)
    return Response(content=xml, media_type="application/xml")


@app.websocket("/phone/stream")
async def phone_stream_endpoint(ws: WebSocket, session_id: str = "phone-default") -> None:
    """
    Twilio Media Streams WebSocket.
    Receives mulaw 8 kHz audio frames, transcribes via Deepgram, runs agent_turn(),
    synthesises reply as mulaw 8 kHz via Google Neural2-D, streams back to Twilio.
    Supports barge-in via Deepgram SpeechStarted + Twilio 'clear' event.
    """
    await phone_stream_handler(ws, session_id)


@app.websocket("/voice")
async def voice_endpoint(ws: WebSocket, session_id: str = "default", sample_rate: int = 48000):
    await voice_handler(ws, session_id, sample_rate)


@app.websocket("/voice/bench")
async def voice_bench_endpoint(ws: WebSocket, session_id: str = "bench"):
    await voice_bench_handler(ws, session_id)


@app.get("/a2a/summary/{session_id}")
async def a2a_summary_endpoint(session_id: str) -> Dict[str, Any]:
    """
    Returns aggregate validation metrics for a given critic session.
    Useful for tracking quality trends across a full recruiter conversation.
    """
    return get_critic_session_summary(session_id)


# ------------------------------------------------------------------
# /session/{session_id}/summary — P2: post-call interview summary
# ------------------------------------------------------------------

@app.get("/session/{session_id}/summary")
async def session_summary_endpoint(session_id: str) -> Dict[str, Any]:
    """
    Post-call structured interview summary for a completed voice session.

    Automatically generated at session end and cached in session state.
    If not yet generated (e.g. session ended before this was deployed),
    generates on-demand and caches the result.

    Returns:
      role_fit_score    int 1-5 | null
      strengths         list[str]
      concerns          list[str]
      recommendation    "Strong Yes" | "Yes" | "Maybe" | "No"
      summary           str  (2-3 sentences for the recruiter)
      generated         bool (False = Gemini unavailable, used fallback)
    """
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    # Return cached summary if available
    cached = state.extra.get("session_summary")
    if cached:
        return cached

    # Generate on-demand and persist
    from .session_summary import generate_session_summary
    summary = generate_session_summary(
        session_id=session_id,
        memory=state.memory,
        role=state.role,
        criteria=state.criteria,
    )
    state.extra["session_summary"] = summary
    try:
        save_session(session_id, state)
    except Exception as exc:
        logger.warning("session_summary: could not persist for %s: %s", session_id, exc)

    return summary


# ------------------------------------------------------------------
# /health — liveness + backend info
# ------------------------------------------------------------------

@app.get("/health")
async def health_endpoint() -> Dict[str, Any]:
    """Service health check with session store backend info."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "session_store": session_store_info(),
    }


# ------------------------------------------------------------------
# Frontend catch-all — MUST stay the last registered route (it would
# shadow every GET API route registered after it; see note at top).
# ------------------------------------------------------------------

@app.get("/{path:path}", include_in_schema=False)
async def serve_frontend_assets(path: str):
    # Resolve fully and verify the result stays inside FRONTEND_DIR to prevent
    # path-traversal requests such as /../app/cv.txt from escaping the frontend.
    resolved_base = FRONTEND_DIR.resolve()
    file_path = (FRONTEND_DIR / path).resolve()
    if resolved_base in file_path.parents and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")
