from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Formula(Base):
    __tablename__ = "formulas"

    formula_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    formula_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aliases_list: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    steps: Mapped[list[FormulaStep]] = relationship(
        "FormulaStep",
        back_populates="formula",
        cascade="all, delete-orphan",
        order_by="FormulaStep.step_index",
    )


class FormulaStep(Base):
    __tablename__ = "formula_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    formula_id: Mapped[str] = mapped_column(ForeignKey("formulas.formula_id"), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    command_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reagent_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_mass_mg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tolerance_mg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_vessel: Mapped[str | None] = mapped_column(String(64), nullable=True)

    formula: Mapped[Formula] = relationship("Formula", back_populates="steps")
