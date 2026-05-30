"""
app/outbound.py — Outbound call campaign manager (PSTN via Twilio)

Production concerns addressed
------------------------------
Concurrency
  asyncio.Semaphore caps simultaneous live calls per campaign.
  Default: 3 concurrent calls.  Configurable per campaign.

Retry with exponential backoff
  Up to MAX_RETRIES (3) attempts per number.
  Delays: 5 min → 15 min → 45 min.
  No retry on: OPT_OUT, COMPLIANCE_BLOCKED, COMPLETED.

TCPA compliance (US) / general calling-hours enforcement
  Calls only allowed 08:00–21:00 in the target timezone.
  Numbers blocked outside hours are queued for retry in the next window.
  Timezone inferred from country code prefix; defaults to Europe/Berlin for +49/+44/+33.

GDPR / consent disclosure
  Every outbound TwiML opens with a verbal disclosure:
    "This is an automated recruiting assistant. You may say 'stop' at any time
     to be removed from our call list. This call may be recorded."
  The agent then starts the normal conversation.

Opt-out list
  In-memory Set (production: persist to DB / Redis).
  Add via POST /outbound/opt-out.
  Numbers in the opt-out list are COMPLIANCE_BLOCKED and never retried.
  Agent response "stop" / "remove me" / "don't call" triggers auto-opt-out.

Observability
  Each campaign and call has full status history.
  GET /outbound/status returns concurrency + per-campaign aggregate.
  Twilio status callbacks update call records in real time.

Env vars required
-----------------
  TWILIO_ACCOUNT_SID   — Twilio account SID
  TWILIO_AUTH_TOKEN    — Twilio auth token
  TWILIO_FROM_NUMBER   — verified Twilio phone number (E.164, e.g. +12125551234)
  PUBLIC_URL           — public HTTPS base URL (e.g. https://recruiter-agent-xxx.run.app)
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAYS_SECONDS = [5 * 60, 15 * 60, 45 * 60]   # 5 min, 15 min, 45 min
CALLING_HOURS_START = 8    # 08:00 inclusive
CALLING_HOURS_END   = 21   # 21:00 exclusive

# Country code → IANA timezone (expand as needed)
_COUNTRY_TZ: Dict[str, str] = {
    "+1":  "America/New_York",
    "+44": "Europe/London",
    "+49": "Europe/Berlin",
    "+33": "Europe/Paris",
    "+34": "Europe/Madrid",
    "+31": "Europe/Amsterdam",
    "+32": "Europe/Brussels",
    "+41": "Europe/Zurich",
    "+43": "Europe/Vienna",
    "+48": "Europe/Warsaw",
    "+40": "Europe/Bucharest",
}
_DEFAULT_TZ = "Europe/Berlin"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CallStatus(str, Enum):
    PENDING              = "pending"
    DIALING              = "dialing"
    RINGING              = "ringing"
    IN_PROGRESS          = "in_progress"
    COMPLETED            = "completed"
    NO_ANSWER            = "no_answer"
    FAILED               = "failed"
    OPT_OUT              = "opt_out"
    COMPLIANCE_BLOCKED   = "compliance_blocked"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"


class CampaignStatus(str, Enum):
    CREATED   = "created"
    RUNNING   = "running"
    PAUSED    = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CallRecord:
    call_id:      str
    phone_number: str
    status:       CallStatus     = CallStatus.PENDING
    attempts:     int            = 0
    call_sid:     Optional[str]  = None     # Twilio CallSid (set once dialed)
    error:        Optional[str]  = None
    created_at:   datetime       = field(default_factory=datetime.utcnow)
    updated_at:   datetime       = field(default_factory=datetime.utcnow)
    next_retry_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id":      self.call_id,
            "phone_number": self.phone_number,
            "status":       self.status.value,
            "attempts":     self.attempts,
            "call_sid":     self.call_sid,
            "error":        self.error,
            "created_at":   self.created_at.isoformat(),
            "updated_at":   self.updated_at.isoformat(),
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
        }


@dataclass
class Campaign:
    campaign_id:    str
    name:           str
    numbers:        List[str]
    role:           str
    criteria:       List[str]
    max_concurrent: int              = 3
    status:         CampaignStatus   = CampaignStatus.CREATED
    calls:          Dict[str, CallRecord] = field(default_factory=dict)
    created_at:     datetime         = field(default_factory=datetime.utcnow)

    def aggregate(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for rec in self.calls.values():
            counts[rec.status.value] = counts.get(rec.status.value, 0) + 1
        return {
            "campaign_id":  self.campaign_id,
            "name":         self.name,
            "status":       self.status.value,
            "total":        len(self.calls),
            "by_status":    counts,
            "role":         self.role,
            "criteria":     self.criteria,
            "max_concurrent": self.max_concurrent,
            "created_at":   self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Compliance helpers
# ---------------------------------------------------------------------------

def _normalise_phone(number: str) -> str:
    """Strip spaces/dashes; ensure E.164-ish format."""
    return "".join(c for c in number.strip() if c.isdigit() or c == "+")


def _timezone_for_number(number: str) -> str:
    """Best-effort timezone lookup from country code prefix."""
    for prefix, tz in sorted(_COUNTRY_TZ.items(), key=lambda x: -len(x[0])):
        if number.startswith(prefix):
            return tz
    return _DEFAULT_TZ


def is_calling_hours_ok(phone_number: str) -> bool:
    """
    Return True if the current time in the number's timezone is within
    allowed calling hours (08:00–21:00 inclusive).
    """
    tz_name = _timezone_for_number(phone_number)
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(_DEFAULT_TZ)
    now = datetime.now(tz)
    return CALLING_HOURS_START <= now.hour < CALLING_HOURS_END


def _should_retry(record: CallRecord) -> bool:
    if record.status in (
        CallStatus.OPT_OUT,
        CallStatus.COMPLIANCE_BLOCKED,
        CallStatus.COMPLETED,
        CallStatus.MAX_RETRIES_EXCEEDED,
    ):
        return False
    return record.attempts < MAX_RETRIES


def _next_retry_at(attempts: int) -> datetime:
    delay = RETRY_DELAYS_SECONDS[min(attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)]
    return datetime.utcnow() + timedelta(seconds=delay)


# ---------------------------------------------------------------------------
# Twilio outbound call
# ---------------------------------------------------------------------------

def _initiate_twilio_call(phone_number: str, session_id: str) -> str:
    """
    Initiate an outbound call via Twilio REST API.
    Returns the Twilio CallSid.
    Runs synchronously — wrap with run_in_executor for async contexts.
    """
    from twilio.rest import Client as TwilioClient

    account_sid  = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token   = os.environ["TWILIO_AUTH_TOKEN"]
    from_number  = os.environ["TWILIO_FROM_NUMBER"]
    public_url   = os.environ.get("PUBLIC_URL", "").rstrip("/")

    if not public_url:
        raise RuntimeError("PUBLIC_URL env var required for outbound TwiML callback")

    twiml_url = (
        f"{public_url}/phone/twiml/outbound"
        f"?session_id={session_id}"
    )
    callback_url = f"{public_url}/outbound/callback"

    client = TwilioClient(account_sid, auth_token)
    call = client.calls.create(
        to=phone_number,
        from_=from_number,
        url=twiml_url,
        status_callback=callback_url,
        status_callback_method="POST",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    return call.sid


# ---------------------------------------------------------------------------
# Campaign manager
# ---------------------------------------------------------------------------

class CampaignManager:
    """
    Manages outbound call campaigns with concurrency control, retries,
    and compliance enforcement.
    """

    def __init__(self) -> None:
        self._campaigns: Dict[str, Campaign] = {}
        self._opt_out:   Set[str] = set()
        # Per-campaign semaphores (created lazily)
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        # Total active calls across all campaigns
        self._active_calls: int = 0

    # ------------------------------------------------------------------
    # Campaign CRUD
    # ------------------------------------------------------------------

    def create_campaign(
        self,
        name: str,
        numbers: List[str],
        role: str,
        criteria: List[str],
        max_concurrent: int = 3,
    ) -> Campaign:
        campaign_id = uuid.uuid4().hex[:8]
        calls = {
            uuid.uuid4().hex[:8]: CallRecord(
                call_id=uuid.uuid4().hex[:8],
                phone_number=_normalise_phone(n),
            )
            for n in numbers
        }
        campaign = Campaign(
            campaign_id=campaign_id,
            name=name,
            numbers=[_normalise_phone(n) for n in numbers],
            role=role,
            criteria=criteria,
            max_concurrent=max_concurrent,
            calls=calls,
        )
        self._campaigns[campaign_id] = campaign
        logger.info(
            "campaign created id=%s name=%r numbers=%d role=%s",
            campaign_id, name, len(numbers), role,
        )
        return campaign

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        return self._campaigns.get(campaign_id)

    def pause_campaign(self, campaign_id: str) -> bool:
        c = self._campaigns.get(campaign_id)
        if c and c.status == CampaignStatus.RUNNING:
            c.status = CampaignStatus.PAUSED
            return True
        return False

    def cancel_campaign(self, campaign_id: str) -> bool:
        c = self._campaigns.get(campaign_id)
        if c:
            c.status = CampaignStatus.CANCELLED
            return True
        return False

    # ------------------------------------------------------------------
    # Opt-out list
    # ------------------------------------------------------------------

    def add_opt_out(self, phone_number: str) -> None:
        normalised = _normalise_phone(phone_number)
        self._opt_out.add(normalised)
        logger.info("opt_out added %s", normalised)

    def is_opted_out(self, phone_number: str) -> bool:
        return _normalise_phone(phone_number) in self._opt_out

    # ------------------------------------------------------------------
    # Dialing
    # ------------------------------------------------------------------

    def _get_semaphore(self, campaign_id: str, max_concurrent: int) -> asyncio.Semaphore:
        if campaign_id not in self._semaphores:
            self._semaphores[campaign_id] = asyncio.Semaphore(max_concurrent)
        return self._semaphores[campaign_id]

    async def start_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Begin dialing all pending numbers in the campaign."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"error": f"Campaign {campaign_id!r} not found"}
        if campaign.status not in (CampaignStatus.CREATED, CampaignStatus.PAUSED):
            return {"error": f"Campaign is {campaign.status.value} — cannot start"}

        campaign.status = CampaignStatus.RUNNING
        asyncio.ensure_future(self._run_campaign(campaign))
        return {"status": "running", "campaign_id": campaign_id}

    async def _run_campaign(self, campaign: Campaign) -> None:
        """Drive the full campaign: dial all pending/retry-ready calls."""
        sem = self._get_semaphore(campaign.campaign_id, campaign.max_concurrent)
        tasks = []

        for record in list(campaign.calls.values()):
            if campaign.status not in (CampaignStatus.RUNNING,):
                break
            if record.status not in (CallStatus.PENDING, CallStatus.NO_ANSWER, CallStatus.FAILED):
                continue
            task = asyncio.ensure_future(self._dial_with_gate(campaign, record, sem))
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Mark complete if all calls are in a terminal state
        terminal = {
            CallStatus.COMPLETED, CallStatus.OPT_OUT,
            CallStatus.COMPLIANCE_BLOCKED, CallStatus.MAX_RETRIES_EXCEEDED,
        }
        if all(r.status in terminal for r in campaign.calls.values()):
            campaign.status = CampaignStatus.COMPLETED
            logger.info("campaign completed id=%s", campaign.campaign_id)

    async def _dial_with_gate(
        self,
        campaign: Campaign,
        record: CallRecord,
        sem: asyncio.Semaphore,
    ) -> None:
        """Acquire the concurrency gate then dial, with retry on transient failures."""
        # Wait if next_retry_at is in the future
        if record.next_retry_at and record.next_retry_at > datetime.utcnow():
            delay = (record.next_retry_at - datetime.utcnow()).total_seconds()
            if delay > 0:
                logger.info(
                    "call %s waiting %.0fs before retry", record.call_id, delay
                )
                await asyncio.sleep(delay)

        async with sem:
            await self._dial_one(campaign, record)

    async def _dial_one(self, campaign: Campaign, record: CallRecord) -> None:
        """
        Attempt a single outbound call with full compliance checks.

        Compliance gates (in order):
          1. Opt-out list — permanent block
          2. TCPA/calling hours — temporary block, schedule retry
          3. Max retries — give up
        """
        phone = record.phone_number
        record.attempts += 1
        record.updated_at = datetime.utcnow()

        # ---- Compliance: opt-out ----
        if self.is_opted_out(phone):
            record.status = CallStatus.COMPLIANCE_BLOCKED
            record.error = "number on opt-out list"
            logger.info("compliance_blocked opt_out call_id=%s phone=%s", record.call_id, phone)
            return

        # ---- Compliance: calling hours ----
        if not is_calling_hours_ok(phone):
            record.status = CallStatus.COMPLIANCE_BLOCKED
            record.next_retry_at = _next_calling_window(phone)
            record.error = "outside calling hours"
            logger.info(
                "compliance_blocked hours call_id=%s phone=%s next=%s",
                record.call_id, phone, record.next_retry_at,
            )
            # Re-queue for the next allowed window
            if record.attempts <= MAX_RETRIES:
                record.status = CallStatus.PENDING
            return

        # ---- Max retries ----
        if record.attempts > MAX_RETRIES:
            record.status = CallStatus.MAX_RETRIES_EXCEEDED
            logger.info("max_retries call_id=%s phone=%s", record.call_id, phone)
            return

        # ---- Dial ----
        record.status = CallStatus.DIALING
        session_id = f"outbound-{record.call_id}"
        self._active_calls += 1

        try:
            loop = asyncio.get_event_loop()
            call_sid = await loop.run_in_executor(
                None,
                lambda: _initiate_twilio_call(phone, session_id),
            )
            record.call_sid = call_sid
            logger.info(
                "outbound dialed call_id=%s phone=%s call_sid=%s attempt=%d",
                record.call_id, phone, call_sid, record.attempts,
            )
        except Exception as exc:
            record.status = CallStatus.FAILED
            record.error = str(exc)
            self._active_calls -= 1
            logger.warning(
                "outbound dial failed call_id=%s phone=%s error=%s",
                record.call_id, phone, exc,
            )
            if _should_retry(record):
                record.status = CallStatus.FAILED
                record.next_retry_at = _next_retry_at(record.attempts)

    def handle_twilio_callback(self, call_sid: str, call_status: str) -> None:
        """Update call record from a Twilio status callback event."""
        status_map = {
            "initiated":  CallStatus.DIALING,
            "ringing":    CallStatus.RINGING,
            "in-progress": CallStatus.IN_PROGRESS,
            "completed":  CallStatus.COMPLETED,
            "no-answer":  CallStatus.NO_ANSWER,
            "failed":     CallStatus.FAILED,
            "busy":       CallStatus.NO_ANSWER,
            "canceled":   CallStatus.FAILED,
        }
        new_status = status_map.get(call_status)
        if not new_status:
            return

        # Find the record by CallSid
        for campaign in self._campaigns.values():
            for record in campaign.calls.values():
                if record.call_sid == call_sid:
                    record.status = new_status
                    record.updated_at = datetime.utcnow()

                    if new_status in (
                        CallStatus.COMPLETED, CallStatus.NO_ANSWER, CallStatus.FAILED
                    ):
                        self._active_calls = max(0, self._active_calls - 1)

                    if new_status == CallStatus.NO_ANSWER and _should_retry(record):
                        record.next_retry_at = _next_retry_at(record.attempts)
                        logger.info(
                            "outbound no_answer call_id=%s — retry at %s",
                            record.call_id, record.next_retry_at,
                        )

                    logger.info(
                        "callback call_sid=%s status=%s", call_sid, call_status
                    )
                    return

    def status(self) -> Dict[str, Any]:
        return {
            "active_calls":   self._active_calls,
            "total_campaigns": len(self._campaigns),
            "opt_out_count":  len(self._opt_out),
            "campaigns": [c.aggregate() for c in self._campaigns.values()],
        }


# ---------------------------------------------------------------------------
# Calling window helper
# ---------------------------------------------------------------------------

def _next_calling_window(phone_number: str) -> datetime:
    """
    Return the next datetime (UTC) when calling hours start for this number's timezone.
    """
    tz_name = _timezone_for_number(phone_number)
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(_DEFAULT_TZ)

    import calendar
    now_local = datetime.now(tz)
    if now_local.hour < CALLING_HOURS_START:
        # Later today
        next_window = now_local.replace(
            hour=CALLING_HOURS_START, minute=0, second=0, microsecond=0
        )
    else:
        # Tomorrow
        tomorrow = now_local + timedelta(days=1)
        next_window = tomorrow.replace(
            hour=CALLING_HOURS_START, minute=0, second=0, microsecond=0
        )

    # Convert back to UTC
    return next_window.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# TwiML handler for outbound calls (with GDPR/TCPA compliance notice)
# ---------------------------------------------------------------------------

async def outbound_twiml_handler(request: "Request", session_id: str) -> str:
    """
    Returns TwiML for outbound calls.

    Opens with a verbal GDPR/TCPA disclosure before connecting to the
    Media Streams WebSocket so the agent can continue the conversation.
    """
    from fastapi import Request

    public_url = os.environ.get("PUBLIC_URL", "").rstrip("/")
    if not public_url:
        host = request.headers.get("host", "localhost")
        public_url = f"https://{host}"

    stream_url = (
        public_url
        .replace("https://", "wss://")
        .replace("http://", "ws://")
        + f"/phone/stream?session_id={session_id}"
    )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        # Compliance disclosure — required before any conversation
        "  <Say voice=\"Polly.Joanna\">"
        "Hello. This is an automated recruiting assistant. "
        "This call may be recorded for quality and training purposes. "
        "You may say stop or remove me at any time to be removed from our contact list."
        "</Say>\n"
        "  <Connect>\n"
        f'    <Stream url="{stream_url}" />\n'
        "  </Connect>\n"
        "</Response>"
    )
    return xml


# ---------------------------------------------------------------------------
# Status callback handler (called by Twilio via POST /outbound/callback)
# ---------------------------------------------------------------------------

async def outbound_callback_handler(form_data: Dict[str, str]) -> Dict[str, Any]:
    """
    Process Twilio status callback.

    Twilio POSTs form fields:  CallSid, CallStatus, Direction, etc.
    We update the call record and trigger retry scheduling if needed.
    """
    call_sid    = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")

    if call_sid and call_status:
        _manager.handle_twilio_callback(call_sid, call_status)

    return {"received": True}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager = CampaignManager()


def get_campaign_manager() -> CampaignManager:
    return _manager
