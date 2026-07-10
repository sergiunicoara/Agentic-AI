from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # trace_id UUID
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    task_id: Mapped[str] = mapped_column(String(128), index=True, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    spans: Mapped[list["Span"]] = relationship(
        "Span", back_populates="trace", cascade="all, delete-orphan"
    )


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # span_id UUID
    trace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_traces.id", ondelete="CASCADE"), index=True
    )
    parent_span_id: Mapped[str] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    timestamp_ms: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)

    trace: Mapped["AgentTrace"] = relationship("AgentTrace", back_populates="spans")
