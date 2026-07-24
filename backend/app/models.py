import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

CONTROLLER_CHANNELS = ("geyser", "fridge", "lighting", "plugs", "cooking", "background")
SWITCHING_STATES = ("on", "off", "standby", "fault")
QUALITY_FLAGS = ("valid", "missing", "duplicate", "out_of_range", "abnormal_event")


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    """Role/consent record — not wired to an auth flow yet, see Objective 2/8."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    role: Mapped[str] = mapped_column(String, default="researcher")
    consent_status: Mapped[str] = mapped_column(String, default="not_required")
    access_level: Mapped[str] = mapped_column(String, default="read")


class Site(Base):
    """Anonymised household/community site — never stores name or address."""

    __tablename__ = "sites"

    site_id: Mapped[str] = mapped_column(String, primary_key=True)
    community_id: Mapped[str | None] = mapped_column(String, nullable=True)
    anonymised_label: Mapped[str] = mapped_column(String, nullable=False)
    site_type: Mapped[str] = mapped_column(String, default="household")

    channels: Mapped[list["SmartControllerChannel"]] = relationship(back_populates="site")


class SmartControllerChannel(Base):
    """A monitored load/channel on a site's simulated smart circuit controller."""

    __tablename__ = "smart_controller_channels"

    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.site_id"), nullable=False)
    controller_channel: Mapped[str] = mapped_column(String, nullable=False)
    device_category: Mapped[str | None] = mapped_column(String, nullable=True)
    rated_power_kw: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    switching_state: Mapped[str] = mapped_column(String, default="off")

    site: Mapped["Site"] = relationship(back_populates="channels")
    readings: Mapped[list["Reading"]] = relationship(back_populates="device")

    __table_args__ = (
        CheckConstraint(
            f"controller_channel IN {CONTROLLER_CHANNELS}",
            name="ck_channel_controller_channel_valid",
        ),
        CheckConstraint(
            f"switching_state IN {SWITCHING_STATES}",
            name="ck_channel_switching_state_valid",
        ),
    )


class Reading(Base):
    """A single timestamped measurement — the canonical unit from DATA_SPECIFICATION.md."""

    __tablename__ = "readings"

    reading_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("smart_controller_channels.device_id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voltage_v: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    current_a: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    power_kw: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    energy_kwh_interval: Mapped[float | None] = mapped_column(Numeric(8, 5), nullable=True)
    cumulative_energy_kwh: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    switching_state: Mapped[str] = mapped_column(String, nullable=False)
    quality_flag: Mapped[str] = mapped_column(String, nullable=False, default="valid")

    device: Mapped["SmartControllerChannel"] = relationship(back_populates="readings")

    __table_args__ = (
        CheckConstraint(
            f"switching_state IN {SWITCHING_STATES}",
            name="ck_reading_switching_state_valid",
        ),
        CheckConstraint(
            f"quality_flag IN {QUALITY_FLAGS}",
            name="ck_reading_quality_flag_valid",
        ),
    )


class DailySummary(Base):
    """Per-device daily aggregate — supports dashboard trend/cost views."""

    __tablename__ = "daily_summaries"

    summary_id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("smart_controller_channels.device_id"), nullable=False
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_kwh: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    peak_power_kw: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)


class ComparisonResult(Base):
    """Stored output of baseline/peer-group comparative analytics for a site+period."""

    __tablename__ = "comparison_results"

    comparison_id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.site_id"), nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)
    baseline_kwh: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    group_average_kwh: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    ratio: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    status_flag: Mapped[str | None] = mapped_column(String, nullable=True)


class AuditLog(Base):
    """Accountability trail — who/what/when, per POPIA-aligned design (Section B.6)."""

    __tablename__ = "audit_logs"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
