from datetime import datetime

from pydantic import BaseModel, Field


class DrugBase(BaseModel):
    reagent_name_cn: str
    reagent_name_en: str | None = None
    reagent_name_formula: str | None = None
    aliases_list: list[str] = Field(default_factory=list)
    cas_number: str | None = None
    purity_grade: str | None = None
    molar_weight_g_mol: float | None = None
    density_g_cm3: float | None = None
    station_id: str | None = None
    stock_mg: int = 0
    notes: str | None = None


class DrugCreate(DrugBase):
    reagent_code: str


class DrugUpdate(BaseModel):
    reagent_name_cn: str | None = None
    reagent_name_en: str | None = None
    reagent_name_formula: str | None = None
    aliases_list: list[str] | None = None
    cas_number: str | None = None
    purity_grade: str | None = None
    molar_weight_g_mol: float | None = None
    density_g_cm3: float | None = None
    station_id: str | None = None
    stock_mg: int | None = None
    notes: str | None = None


class DrugRead(DrugBase):
    reagent_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DrugSearchResult(BaseModel):
    reagent_code: str
    reagent_name_cn: str
    reagent_name_en: str | None = None
    reagent_name_formula: str | None = None
    purity_grade: str | None = None
    station_id: str | None = None
    stock_mg: int
    score: float = Field(description="模糊匹配相似度，1.0=完全匹配")
