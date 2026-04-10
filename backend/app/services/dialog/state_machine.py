import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class DeviceState(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"


class TaskState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class StateMachine:
    def __init__(self):
        self._device_state = DeviceState.IDLE
        self._current_task_id: str | None = None

    @property
    def device_state(self) -> DeviceState:
        return self._device_state

    @property
    def current_task_id(self) -> str | None:
        return self._current_task_id

    def can_start_task(self) -> tuple[bool, str]:
        if self._device_state == DeviceState.BUSY:
            return False, "设备正在执行其他任务"
        if self._device_state == DeviceState.ERROR:
            return False, "设备处于错误状态，需先复位"
        if self._device_state == DeviceState.EMERGENCY_STOP:
            return False, "设备处于急停状态，需先解除"
        return True, ""

    def start_task(self, task_id: str) -> bool:
        ok, reason = self.can_start_task()
        if not ok:
            logger.warning("任务 %s 无法启动: %s", task_id, reason)
            return False
        self._device_state = DeviceState.BUSY
        self._current_task_id = task_id
        logger.info("任务 %s 开始执行", task_id)
        return True

    def complete_task(self, task_id: str) -> bool:
        if self._current_task_id != task_id:
            logger.warning("任务 %s 不是当前执行任务（当前=%s），忽略", task_id, self._current_task_id)
            return False
        self._device_state = DeviceState.IDLE
        self._current_task_id = None
        logger.info("任务 %s 完成", task_id)
        return True

    def fail_task(self, task_id: str, error: str) -> bool:
        if self._current_task_id != task_id:
            logger.warning("任务 %s 不是当前执行任务（当前=%s），忽略", task_id, self._current_task_id)
            return False
        self._device_state = DeviceState.ERROR
        self._current_task_id = None
        logger.error("任务 %s 失败: %s", task_id, error)
        return True

    def cancel_task(self, task_id: str) -> bool:
        if self._current_task_id != task_id:
            logger.warning("任务 %s 不是当前执行任务（当前=%s），忽略", task_id, self._current_task_id)
            return False
        self._device_state = DeviceState.IDLE
        self._current_task_id = None
        logger.info("任务 %s 已取消", task_id)
        return True

    def trigger_emergency_stop(self) -> None:
        self._device_state = DeviceState.EMERGENCY_STOP
        prev_task = self._current_task_id
        self._current_task_id = None
        logger.critical("急停触发，当前任务 %s 中断", prev_task)

    def recover_from_error(self) -> None:
        self._device_state = DeviceState.IDLE
        self._current_task_id = None
        logger.info("设备从错误状态恢复")


_state_machine: StateMachine | None = None
_sm_lock: asyncio.Lock | None = None


def _get_sm_lock() -> asyncio.Lock:
    global _sm_lock
    if _sm_lock is None:
        _sm_lock = asyncio.Lock()
    return _sm_lock


async def get_state_machine_async() -> StateMachine:
    global _state_machine
    if _state_machine is not None:
        return _state_machine
    async with _get_sm_lock():
        if _state_machine is None:
            _state_machine = StateMachine()
    return _state_machine


def get_state_machine() -> StateMachine:
    global _state_machine
    if _state_machine is None:
        _state_machine = StateMachine()
    return _state_machine
