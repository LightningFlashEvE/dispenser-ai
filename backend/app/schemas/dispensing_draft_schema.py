from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DispensingDraft(BaseModel):
    task_type: Literal["DISPENSING"] = "DISPENSING"
    source_material_text: str | None = None
    chemical_id: str | None = None
    chemical_display_name: str | None = None
    cas_no: str | None = None
    grade: str | None = None
    catalog_match_status: str = "UNMATCHED"
    catalog_candidates: list[dict] = []
    portion_count: int | None = None
    amount_per_portion: float | None = None
    amount_unit: str | None = None
    target_vessels: list[str] | None = None
    purpose: str | None = None


DISPENSING_DRAFT_DEFAULT = DispensingDraft().model_dump()
