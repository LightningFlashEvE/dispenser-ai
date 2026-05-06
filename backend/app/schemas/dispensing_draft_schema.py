from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DispensingDraft(BaseModel):
    task_type: Literal["DISPENSING"] = "DISPENSING"
    source_material: str | None = None
    portion_count: int | None = None
    mass_per_portion: float | None = None
    mass_unit: str | None = None
    target_vessels: list[str] | None = None
    purpose: str | None = None

