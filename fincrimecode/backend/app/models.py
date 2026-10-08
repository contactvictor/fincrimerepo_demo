from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MigrationRun(Base):
    __tablename__ = "migration_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    source_system: Mapped[str] = mapped_column(String(64))
    target_system: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16), default="UAT", index=True)
    status: Mapped[str] = mapped_column(String(32), default="CREATED")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    reconciliation_pct: Mapped[float] = mapped_column(Float, default=0.0)
    signoff_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    exceptions: Mapped[list["ReconException"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SourceRecord(Base):
    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class TargetRecord(Base):
    __tablename__ = "target_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class ReconSummary(Base):
    """Level 1 totals per domain/metric."""

    __tablename__ = "recon_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(64))
    source_value: Mapped[float] = mapped_column(Float)
    target_value: Mapped[float] = mapped_column(Float)
    difference: Mapped[float] = mapped_column(Float)
    matched: Mapped[bool] = mapped_column(Boolean)


class RecordResult(Base):
    """Level 2 (record) results with Level 3 (field) differences embedded."""

    __tablename__ = "record_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    source_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_differences: Mapped[list] = mapped_column(JSON, default=list)
    variance: Mapped[float] = mapped_column(Float, default=0.0)


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32))
    domain: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(16), default="HIGH")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RuleResult(Base):
    __tablename__ = "rule_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"))
    rule_name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    domain: Mapped[str] = mapped_column(String(32))
    passed: Mapped[bool] = mapped_column(Boolean)
    actual: Mapped[str] = mapped_column(String(256), default="")
    expected: Mapped[str] = mapped_column(String(256), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconException(Base):
    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    root_cause: Mapped[str] = mapped_column(String(32), index=True)
    root_cause_detail: Mapped[str] = mapped_column(Text, default="")
    record_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    variance: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="DETECTED", index=True)
    resolution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[MigrationRun] = relationship(back_populates="exceptions")
    history: Mapped[list["ExceptionHistory"]] = relationship(
        back_populates="exception", cascade="all, delete-orphan", order_by="ExceptionHistory.id"
    )


class ExceptionHistory(Base):
    __tablename__ = "exception_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey("exceptions.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    exception: Mapped[ReconException] = relationship(back_populates="history")


class SignOff(Base):
    __tablename__ = "signoffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    area: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(48))
    file_format: Mapped[str] = mapped_column(String(8))
    filename: Mapped[str] = mapped_column(String(256))
    content_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
