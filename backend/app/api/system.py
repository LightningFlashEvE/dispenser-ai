import asyncio
import platform
import shutil
import subprocess

import psutil
from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["系统资源"])


@router.get("/resources")
async def system_resources() -> dict:
    return await asyncio.to_thread(_collect_system_resources)


def _collect_system_resources() -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count()

    mem = psutil.virtual_memory()
    mem_used_mb = mem.used / (1024 * 1024)
    mem_total_mb = mem.total / (1024 * 1024)
    mem_percent = mem.percent

    gpu_percent = _get_jetson_gpu_usage()

    disk = shutil.disk_usage("/")
    disk_used_gb = disk.used / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)
    disk_percent = (disk.used / disk.total) * 100

    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": cpu_count,
        },
        "memory": {
            "used_mb": round(mem_used_mb, 1),
            "total_mb": round(mem_total_mb, 1),
            "percent": mem_percent,
        },
        "gpu": {
            "percent": gpu_percent,
            "used_mb": 0,
            "total_mb": round(mem_total_mb, 1),
        },
        "disk": {
            "used_gb": round(disk_used_gb, 1),
            "total_gb": round(disk_total_gb, 1),
            "percent": round(disk_percent, 1),
        },
    }


def _get_jetson_gpu_usage() -> float:
    """通过 tegrastats 获取 Jetson GPU 使用率"""
    if platform.system() != "Linux" or shutil.which("tegrastats") is None:
        return 0.0

    try:
        result = subprocess.run(
            ["tegrastats", "--interval", "1000", "--count", "1"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        lines = result.stdout.strip().split("\n")
        if not lines:
            return 0.0
        last_line = lines[-1]
        match = __import__("re").search(r"GR3D_FREQ (\d+)%", last_line)
        if match:
            return float(match.group(1))
        return 0.0
    except Exception:
        return 0.0
