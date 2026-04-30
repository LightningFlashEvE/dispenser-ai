from fastapi import APIRouter

from app.services.device.control_client import get_control_client
from app.services.dialog.state_machine import get_state_machine

router = APIRouter(prefix="/api/device", tags=["设备状态"])


@router.get("/status")
async def device_status() -> dict:
    control_client = get_control_client()
    state_machine = get_state_machine()

    remote_status = await control_client.get_status()
    return {
        "device_status": remote_status.get("device_status", "unknown"),
        "balance_ready": remote_status.get("balance_ready", False),
        "current_weight_mg": remote_status.get("current_weight_mg"),
        "current_command_id": remote_status.get("current_command_id"),
        "current_task": remote_status.get("current_task"),
        "last_completed_task": remote_status.get("last_completed_task"),
        "state_machine_state": state_machine.device_state.value,
        "current_task_id": state_machine.current_task_id,
    }
