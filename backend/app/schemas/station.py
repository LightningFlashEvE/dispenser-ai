from datetime import datetime

from pydantic import BaseModel


class StationRead(BaseModel):
    station_id: str
    display_name: str | None = None
    has_bottle: bool
    reagent_code: str | None = None
    reagent_name_cn: str | None = None
    is_occupied: bool
    position_x: int | None = None
    position_y: int | None = None
    last_vision_update: datetime | None = None

    model_config = {"from_attributes": True}


class StationUpdate(BaseModel):
    has_bottle: bool | None = None
    reagent_code: str | None = None
    reagent_name_cn: str | None = None
    is_occupied: bool | None = None
