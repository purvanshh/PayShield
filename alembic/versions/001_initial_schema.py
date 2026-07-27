"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "layer1_audit_log",
        sa.Column("log_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("txn_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("fraud_probability", sa.Float(), nullable=True, server_default="0"),
        sa.Column("triggered_rules", postgresql.JSONB(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True, server_default="0"),
        sa.Column("model_version", sa.String(20), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        sa.CheckConstraint("decision IN ('ALLOW','BLOCK','REVIEW')", name="ck_audit_decision"),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_table(
        "investigation_reports",
        sa.Column("report_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("txn_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("fraud_type", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False),
        sa.Column("recommended_action", sa.String(10), nullable=False),
        sa.Column("key_evidence_json", postgresql.JSONB(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True, server_default=""),
        sa.Column("model_version", sa.String(20), nullable=True, server_default=""),
        sa.Column("prompt_version", sa.String(20), nullable=True, server_default=""),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("fraud_type IN ('MULE_RING','BURST_ATTACK','MERCHANT_COLLUSION','ACCOUNT_TAKEOVER','OTHER')", name="ck_fraud_type"),
        sa.CheckConstraint("confidence IN ('HIGH','MEDIUM','LOW')", name="ck_confidence"),
        sa.CheckConstraint("recommended_action IN ('BLOCK','REVIEW','ALLOW')", name="ck_action"),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_table(
        "analyst_feedback",
        sa.Column("feedback_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("txn_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("original_decision", sa.String(10), nullable=False),
        sa.Column("analyst_decision", sa.String(10), nullable=False),
        sa.Column("analyst_id", sa.String(50), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        sa.CheckConstraint("original_decision IN ('ALLOW','BLOCK','REVIEW')", name="ck_fb_original"),
        sa.CheckConstraint("analyst_decision IN ('ALLOW','BLOCK','REVIEW')", name="ck_fb_analyst"),
        sa.CheckConstraint("category IN ('FALSE_POSITIVE','FALSE_NEGATIVE','TRUE_POSITIVE','TRUE_NEGATIVE')", name="ck_fb_category"),
        sa.PrimaryKeyConstraint("feedback_id"),
    )
    op.create_table(
        "mitigation_actions",
        sa.Column("action_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("txn_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True, server_default=""),
        sa.Column("executed_by", sa.String(20), nullable=False),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.Column("rolled_back", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("rollback_approved_by", sa.String(50), nullable=True, server_default=""),
        sa.CheckConstraint("action_type IN ('BLOCK','ALERT','NOTIFY','FREEZE','ESCALATE','UNBLOCK')", name="ck_action_type"),
        sa.PrimaryKeyConstraint("action_id"),
    )
    op.create_table(
        "graph_transaction_log",
        sa.Column("log_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("txn_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("merchant_id", sa.String(50), nullable=False),
        sa.Column("device_id", sa.String(50), nullable=True, server_default=""),
        sa.Column("amount", sa.Float(), nullable=True, server_default="0"),
        sa.Column("txn_type", sa.String(10), nullable=True, server_default="P2P"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="analyst"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('analyst','admin','system')", name="ck_user_role"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "api_keys",
        sa.Column("key_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=True, server_default=""),
        sa.Column("role", sa.String(20), nullable=True, server_default="system"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("key_id"),
    )
    op.create_table(
        "admin_audit_log",
        sa.Column("log_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True, server_default=""),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("log_id"),
    )


def downgrade() -> None:
    op.drop_table("admin_audit_log")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("graph_transaction_log")
    op.drop_table("mitigation_actions")
    op.drop_table("analyst_feedback")
    op.drop_table("investigation_reports")
    op.drop_table("layer1_audit_log")
