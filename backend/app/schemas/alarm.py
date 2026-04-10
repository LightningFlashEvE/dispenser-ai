from datetime import datetime

from pydantic import BaseModel


class AlarmRead(BaseModel):
    id: int
    task_id: str | None
    alarm_code: str
    severity: str
    message: str
    is_resolved: bool
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
