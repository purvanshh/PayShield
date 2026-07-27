from datetime import datetime

from sqlalchemy import (JSON, Boolean, CheckConstraint, Column, DateTime,
                         Float, ForeignKey, Integer, String, Text, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    __tablename__ = "layer1_audit_log"
    __table_args__ = (
        CheckConstraint("decision IN ('ALLOW', 'BLOCK', 'REVIEW')", name="ck_audit_decision"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    fraud_probability: Mapped[float] = mapped_column(Float, default=0.0)
    triggered_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    model_version: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class InvestigationReport(Base):
    __tablename__ = "investigation_reports"
    __table_args__ = (
        CheckConstraint("fraud_type IN ('MULE_RING','BURST_ATTACK','MERCHANT_COLLUSION','ACCOUNT_TAKEOVER','OTHER')", name="ck_fraud_type"),
        CheckConstraint("confidence IN ('HIGH','MEDIUM','LOW')", name="ck_confidence"),
        CheckConstraint("recommended_action IN ('BLOCK','REVIEW','ALLOW')", name="ck_action"),
    )

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    fraud_type: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(10), nullable=False)
    key_evidence_json: Mapped[dict] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    model_version: Mapped[str] = mapped_column(String(20), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnalystFeedback(Base):
    __tablename__ = "analyst_feedback"
    __table_args__ = (
        CheckConstraint("original_decision IN ('ALLOW','BLOCK','REVIEW')", name="ck_fb_original"),
        CheckConstraint("analyst_decision IN ('ALLOW','BLOCK','REVIEW')", name="ck_fb_analyst"),
        CheckConstraint("category IN ('FALSE_POSITIVE','FALSE_NEGATIVE','TRUE_POSITIVE','TRUE_NEGATIVE')", name="ck_fb_category"),
    )

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    original_decision: Mapped[str] = mapped_column(String(10), nullable=False)
    analyst_decision: Mapped[str] = mapped_column(String(10), nullable=False)
    analyst_id: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class MitigationAction(Base):
    __tablename__ = "mitigation_actions"
    __table_args__ = (
        CheckConstraint("action_type IN ('BLOCK','ALERT','NOTIFY','FREEZE','ESCALATE','UNBLOCK')", name="ck_action_type"),
    )

    action_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    executed_by: Mapped[str] = mapped_column(String(20), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rolled_back: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback_approved_by: Mapped[str] = mapped_column(String(50), default="")


class GraphTransactionLog(Base):
    __tablename__ = "graph_transaction_log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    device_id: Mapped[str] = mapped_column(String(50), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    txn_type: Mapped[str] = mapped_column(String(10), default="P2P")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('analyst','admin','system')", name="ck_user_role"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(20), default="system")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
