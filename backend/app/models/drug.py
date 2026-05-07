from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Drug(Base):
    __tablename__ = "drugs"

    reagent_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    reagent_name_cn: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reagent_name_en: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reagent_name_formula: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aliases_list: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cas_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purity_grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    molar_weight_g_mol: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_g_cm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    station_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stock_mg: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
