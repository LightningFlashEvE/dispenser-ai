import platform
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 运行环境
    env: str = "development"
    log_level: str = "INFO"

    # Ollama LLM
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:7b"
    ollama_keep_alive: int = Field(default=300, description="秒数，0=立即释放，-1=永久")

    # ASR（whisper.cpp）— Windows 开发阶段跳过
    whisper_cpp_model_path: str = "models/whisper/ggml-small.bin"

    # TTS（MeloTTS）— Windows 开发阶段跳过
    melotts_model_path: str = "models/melotts"

    # 数据库
    sqlite_db_path: str = "data/app.db"

    # Schema 文件路径
    intent_schema_path: str = "../shared/intent_schema.json"
    command_schema_path: str = "../shared/command_schema.json"

    # 规则配置
    rules_config_path: str = "config/rules.json"

    # 天平量程（mg），WKC204C 最大 220g
    balance_max_mass_mg: int = 220000

    # C++ 后级控制程序
    # Windows 开发阶段：对接 mock-qt (HTTP)
    # Jetson 部署阶段：替换为真实 C++ 控制程序
    control_adapter_host: str = "localhost"
    control_adapter_port: int = 9000

    # 天平串口（RS422-USB）— Windows 开发阶段跳过，Jetson 部署后使用
    balance_serial_port: str = "/dev/ttyUSB0" if platform.system() == "Linux" else "COM3"
    balance_baud_rate: int = 9600

    # 音频 / 相机（Windows 和 Jetson 设备索引含义不同）
    audio_device_index: int = 0
    camera_device_index: int = 0

    # 业务规则
    skip_confirmation: bool = Field(
        default=False,
        description="跳过用户确认，仅开发阶段使用，生产必须为 False",
    )
    default_tolerance_mg: int = Field(default=10, description="默认容差下限（mg）")
    default_tolerance_pct: float = Field(default=2.0, description="默认容差百分比")

    # 对话状态（方案A：任务级清空，内存维护）
    dialog_max_rounds: int = Field(
        default=8,
        description="单次任务最大补槽轮数，超出后重置。当前策略=任务级清空(方案A)。"
        "如需改为滑动窗口(方案B)或Token预算(方案C)，修改 llm.py 中的 DialogSessionManager。",
    )

    @property
    def control_adapter_url(self) -> str:
        return f"http://{self.control_adapter_host}:{self.control_adapter_port}"

    @property
    def is_development(self) -> bool:
        return self.env.lower() == "development"


settings = Settings()
