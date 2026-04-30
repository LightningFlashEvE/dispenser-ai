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

    # LLM (llama.cpp server)
    # 当前模型：Qwen3-4B-Instruct-2507-Q4_K_M（约 2.5GB，Jetson Orin NX CUDA 全层卸载）
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model_path: str = "models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    llm_context_length: int = 16384
    llm_max_tokens: int = 256
    # 采样温度：对话阶段偏创造，意图 JSON 阶段偏确定（Qwen3 建议更低以稳 JSON）
    llm_dialog_temperature: float = 0.3
    llm_intent_temperature: float = 0.05
    llm_gp_layers: int = 99
    llm_threads: int = 6

    # ASR (whisper-server HTTP 服务)
    whisper_server_url: str = "http://127.0.0.1:8081"
    whisper_cpp_model_path: str = "models/whisper/ggml-base.bin"
    whisper_language: str = "zh"
    whisper_vad_threshold: float = 0.5
    audio_sample_rate: int = 16000
    audio_chunk_size_ms: int = 100
    audio_max_buffer_ms: int = 30000

    # TTS（MeloTTS 独立服务）
    tts_provider: str = "melotts"
    tts_base_url: str = "http://localhost:8020"
    tts_timeout_sec: int = 60
    tts_play_default: bool = True
    tts_speed: float = Field(
        default=0.9,
        description="TTS 语速，<1.0 表示更慢，>1.0 表示更快",
    )

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
    control_adapter_host: str = "localhost"
    control_adapter_port: int = 9000

    # 天平串口（RS422-USB）
    balance_serial_port: str = "/dev/ttyUSB0" if platform.system() == "Linux" else "COM3"
    balance_baud_rate: int = 9600

    # 音频 / 相机
    audio_device_index: int = 0
    camera_device_index: int = 0

    # 业务规则
    skip_confirmation: bool = Field(
        default=False,
        description="跳过用户确认，仅开发阶段使用，生产必须为 False",
    )
    default_tolerance_mg: int = Field(default=10, description="默认容差下限（mg）")
    default_tolerance_pct: float = Field(default=2.0, description="默认容差百分比")

    # 对话状态（任务级清空，内存维护）
    dialog_max_rounds: int = Field(
        default=8,
        description="单次任务最大补槽轮数，超出后 TTS 提示重置并清空 session。",
    )

    # 对话历史滚动窗口（条数，一问一答算 2 条）
    dialog_history_max_messages: int = Field(
        default=8,
        description="dialog_history 最多保留的消息条数，超过后按 FIFO 丢弃最旧的一对消息，防止 prompt 无限膨胀。",
    )

    # LLM 单次请求超时（秒）
    llm_request_timeout_sec: float = Field(
        default=45.0,
        description="单次 httpx 调 llama-server 的超时。Jetson 上 Qwen3-4B 生成速度约 17 tok/s，45s 足够 700+ tokens。",
    )

    # WebSocket 心跳间隔（秒，0 表示关闭心跳）
    ws_ping_interval_sec: float = Field(
        default=20.0,
        description="后端主动给前端发 {type:ping} 的周期，防止中间代理空闲断连。",
    )

    # pending_intent 有效期（秒）
    pending_intent_ttl_sec: int = Field(
        default=60,
        description="AI 生成 pending_intent 后，用户需在此时间内确认；超时自动清除。",
    )

    # CORS 白名单（逗号分隔字符串，通过 property 解析为 list）
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="前端允许访问的 origin 列表，逗号分隔。生产环境配置局域网实际 IP。",
    )

    @property
    def control_adapter_url(self) -> str:
        return f"http://{self.control_adapter_host}:{self.control_adapter_port}"

    @property
    def control_adapter_ws_url(self) -> str:
        return f"ws://{self.control_adapter_host}:{self.control_adapter_port}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.env.lower() == "development"


settings = Settings()
