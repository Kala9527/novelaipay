from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    UNCERTAIN = 'uncertain'


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80), default='')
    password_hash: Mapped[str] = mapped_column(String(255))
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=2)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal('0'))
    reserved: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal('0'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegistrationSettings(Base):
    __tablename__ = 'registration_settings'
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    smtp_host: Mapped[str] = mapped_column(String(255), default='')
    smtp_port: Mapped[int] = mapped_column(Integer, default=465)
    smtp_security: Mapped[str] = mapped_column(String(20), default='ssl')
    smtp_username: Mapped[str] = mapped_column(String(320), default='')
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text)
    sender_email: Mapped[str] = mapped_column(String(320), default='')
    subject: Mapped[str] = mapped_column(String(200), default='邮箱注册验证码')
    html_template: Mapped[str] = mapped_column(Text, default='')
    template_vars: Mapped[dict] = mapped_column(JSON, default=dict)
    code_expiry_minutes: Mapped[int] = mapped_column(Integer, default=15)


class RegistrationCode(Base):
    __tablename__ = 'registration_codes'
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class ApiKey(Base):
    __tablename__ = 'api_keys'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey('upstream_groups.id'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(18), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    encrypted_key: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class UpstreamAccount(Base):
    __tablename__ = 'upstream_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    encrypted_key: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(20), default='openai')
    opus_free: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=10)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UpstreamGroup(Base):
    __tablename__ = 'upstream_groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=10)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GroupMember(Base):
    __tablename__ = 'group_members'
    __table_args__ = (UniqueConstraint('group_id', 'user_id', name='uq_group_member'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('upstream_groups.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)


class GroupAccount(Base):
    __tablename__ = 'group_accounts'
    __table_args__ = (UniqueConstraint('group_id', 'account_id', name='uq_group_account'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('upstream_groups.id'), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('upstream_accounts.id'), index=True)


class ModelRoute(Base):
    __tablename__ = 'model_routes'
    __table_args__ = (UniqueConstraint('model_mapping_id', 'account_id', name='uq_model_route'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_mapping_id: Mapped[int] = mapped_column(ForeignKey('model_mappings.id'), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('upstream_accounts.id'), index=True)
    upstream_model: Mapped[str] = mapped_column(String(150))


class ModelMapping(Base):
    __tablename__ = 'model_mappings'
    id: Mapped[int] = mapped_column(primary_key=True)
    __table_args__ = (UniqueConstraint('group_id', 'public_name', name='uq_group_public_model'),)
    group_id: Mapped[int] = mapped_column(ForeignKey('upstream_groups.id'), index=True)
    public_name: Mapped[str] = mapped_column(String(100))
    upstream_model: Mapped[str] = mapped_column(String(150))
    upstream_account_id: Mapped[int] = mapped_column(ForeignKey('upstream_accounts.id'))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=2)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account: Mapped[UpstreamAccount] = relationship()


class PriceVersion(Base):
    __tablename__ = 'price_versions'
    id: Mapped[int] = mapped_column(primary_key=True)
    model_mapping_id: Mapped[int] = mapped_column(ForeignKey('model_mappings.id'), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    extra_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal('0'))
    currency: Mapped[str] = mapped_column(String(3), default='CNY')
    billing_mode: Mapped[str] = mapped_column(String(20), default='fixed')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationJob(Base):
    __tablename__ = 'generation_jobs'
    __table_args__ = (
        UniqueConstraint('user_id', 'idempotency_key', name='uq_job_user_idempotency'),
        Index('ix_job_claim', 'status', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey('api_keys.id'))
    group_id: Mapped[int | None] = mapped_column(ForeignKey('upstream_groups.id'), index=True)
    model_mapping_id: Mapped[int] = mapped_column(ForeignKey('model_mappings.id'))
    price_version_id: Mapped[int] = mapped_column(ForeignKey('price_versions.id'))
    upstream_account_id: Mapped[int] = mapped_column(ForeignKey('upstream_accounts.id'))
    public_model: Mapped[str] = mapped_column(String(100))
    upstream_model: Mapped[str] = mapped_column(String(150))
    mapping_revision: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    size: Mapped[str] = mapped_column(String(40))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    anlas_cost: Mapped[int | None] = mapped_column(Integer)
    billing_overlap: Mapped[bool] = mapped_column(Boolean, default=False)
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED)
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WalletLedger(Base):
    __tablename__ = 'wallet_ledger'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    kind: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageRecord(Base):
    __tablename__ = 'usage_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('generation_jobs.id'), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    price_version_id: Mapped[int] = mapped_column(ForeignKey('price_versions.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentOrder(Base):
    __tablename__ = 'payment_orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    transaction_id: Mapped[str] = mapped_column(String(150))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('provider', 'transaction_id', name='uq_payment_transaction'),)


class RedemptionCode(Base):
    __tablename__ = 'redemption_codes'
    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    encrypted_code: Mapped[str | None] = mapped_column(Text)
    prefix: Mapped[str] = mapped_column(String(12))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    redeemed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Announcement(Base):
    __tablename__ = 'announcements'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
