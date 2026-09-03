from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Numeric
)

from app.db.database import Base


class TransactionDB(Base):

    __tablename__ = "transactions"

    id = Column(
        Integer,
        primary_key=True
    )

    transaction_id = Column(
        String(100),
        unique=True,
        nullable=False
    )

    mandate_id = Column(
        String(100),
        nullable=False
    )

    razorpay_order_id = Column(
        String(100),
        unique=True,
        nullable=True
    )

    razorpay_payment_id = Column(
        String(100),
        unique=True,
        nullable=True
    )

    amount = Column(
        Numeric(20, 2),
        nullable=False
    )

    currency = Column(
        String(10),
        nullable=False
    )

    status = Column(
        String(30),
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    source_amount = Column(
    Numeric(20, 8),
    nullable=True)

    source_currency = Column(
        String(10),
        nullable=True
    )

    fx_rate = Column(
        Numeric(20, 8),
        nullable=True
    )

    fx_timestamp = Column(
        DateTime(timezone=True),
        nullable=True
    )
class WebhookEventDB(Base):

    __tablename__ = "webhook_events"

    id = Column(
        Integer,
        primary_key=True
    )

    event_id = Column(
        String(150),
        nullable=False,
        unique=True
    )

    event_type = Column(
        String(100),
        nullable=True
    )

    received_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class AuditEventDB(Base):

    __tablename__ = "audit_events"

    id = Column(
        Integer,
        primary_key=True
    )

    event_id = Column(
        String(150),
        unique=True,
        nullable=False
    )

    actor = Column(
        String(100),
        nullable=False
    )

    action = Column(
        String(100),
        nullable=False
    )

    status = Column(
        String(50),
        nullable=False
    )

    reason = Column(
        String(500),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
