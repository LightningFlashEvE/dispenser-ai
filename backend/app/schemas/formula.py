from datetime import datetime

from pydantic import BaseModel, Field


class FormulaStepBase(BaseModel):
    step_index: int
    step_name: str | None = None
    command_type: str
    reagent_code: str | None = None
    target_mass_mg: int | None = None
    tolerance_mg: int | None = None
    target_vessel: str | None = None


class FormulaStepRead(FormulaStepBase):
    id: int
    formula_id: str

    model_config = {"from_attributes": True}


class FormulaBase(BaseModel):
    formula_name: str
    aliases_list: list[str] = Field(default_factory=list)
    notes: str | None = None


class FormulaCreate(FormulaBase):
    formula_id: str
    steps: list[FormulaStepBase] = Field(default_factory=list)


class FormulaUpdate(BaseModel):
    formula_name: str | None = None
    aliases_list: list[str] | None = None
    notes: str | None = None
    steps: list[FormulaStepBase] | None = None


class FormulaRead(FormulaBase):
    formula_id: str
    steps: list[FormulaStepRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FormulaSearchResult(BaseModel):
    formula_id: str
    formula_name: str
    aliases_list: list[str]
    step_count: int
    score: float = Field(description="模糊匹配相似度，1.0=完全匹配")
