from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WeighingDraft(BaseModel):
    task_type: Literal["WEIGHING"] = "WEIGHING"
    chemical_name: str | None = None
    target_mass: float | None = None
    mass_unit: str | None = None
    target_vessel: str | None = None
    purpose: str | None = None


WEIGHING_DRAFT_DEFAULT = WeighingDraft().model_dump()

