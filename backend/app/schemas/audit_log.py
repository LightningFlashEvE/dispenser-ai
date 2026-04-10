from datetime import datetime

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    task_id: str | None
    operator_id: str
    event_type: str
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
