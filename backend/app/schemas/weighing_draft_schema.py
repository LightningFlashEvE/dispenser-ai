from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WeighingDraft(BaseModel):
    task_type: Literal["WEIGHING"] = "WEIGHING"
    chemical_name: str | None = None
    chemical_name_text: str | None = None
    chemical_id: str | None = None
    chemical_display_name: str | None = None
    cas_no: str | None = None
    grade: str | None = None
    catalog_match_status: str = "UNMATCHED"
    catalog_candidates: list[dict] = []
    target_mass: float | None = None
    mass_unit: str | None = None
    target_vessel: str | None = None
    purpose: str | None = None


WEIGHING_DRAFT_DEFAULT = WeighingDraft().model_dump()
