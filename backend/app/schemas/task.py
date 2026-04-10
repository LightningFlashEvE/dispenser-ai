from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TaskStepRead(BaseModel):
    id: int
    task_id: str
    step_index: int
    command_type: str
    reagent_code: str | None = None
    reagent_name_cn: str | None = None
    target_mass_mg: int | None = None
    actual_mass_mg: int | None = None
    deviation_mg: int | None = None
    target_vessel: str | None = None
    status: str
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskRead(BaseModel):
    task_id: str
    command_type: str
    operator_id: str
    status: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[TaskStepRead] = []

    model_config = {"from_attributes": True}


class DeviceCallbackPayload(BaseModel):
    command_id: str
    status: str
    completed_at: datetime
    result: Any | None = None
    error: dict[str, str] | None = None
