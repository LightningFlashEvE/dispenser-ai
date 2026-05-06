from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MixingDraft(BaseModel):
    task_type: Literal["MIXING"] = "MIXING"
    target_product: str | None = None
    total_mass: float | None = None
    mass_unit: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    ratio_type: str | None = None
    target_vessel: str | None = None
    purpose: str | None = None

