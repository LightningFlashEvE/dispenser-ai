from datetime import datetime

from pydantic import BaseModel, Field


class ReagentBottleCreate(BaseModel):
    bottle_id: str
    station_id: str | None = None
    reagent_code: str | None = None
    label: str
    status: str = "empty"
    volume_ml: float | None = None
    notes: str | None = None


class ReagentBottleUpdate(BaseModel):
    station_id: str | None = None
    reagent_code: str | None = None
    label: str | None = None
    status: str | None = None
    volume_ml: float | None = None
    fill_date: datetime | None = None
    notes: str | None = None


class ReagentBottleRead(BaseModel):
    bottle_id: str
    station_id: str | None = None
    reagent_code: str | None = None
    reagent_name_cn: str | None = Field(default=None, description="从药品库关联的中文名，非持久化字段")
    label: str
    status: str
    volume_ml: float | None = None
    fill_date: datetime | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
