"""应用配置加载。从 .env 读取，pydantic-settings 做类型校验。

对应 docs/06-env-vars.md 全部环境变量。禁止硬编码密钥。
"""
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_name: str = "BJTU-lecture-analy"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"

    database_url: str = "sqlite:///./storage/db/app.db"

    secret_key: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    storage_root: str = "./storage"
    video_cache_dir: str = "./storage/videos"
    audio_cache_dir: str = "./storage/audios"
    log_dir: str = "./storage/logs"
    export_dir: str = "./storage/exports"
    cache_retention_days: int = 7
    cleanup_audio_after_task: bool = True

    # ---------- 硅基流动 AI（ASR + LLM 共用同一 API Key / Base URL）----------
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # ASR（A1）：语音转写，输出句级时间戳
    siliconflow_asr_model: str = "XingChenAGI/XingChenASR-V3.2-Ultra"
    siliconflow_asr_timeout: int = 300
    siliconflow_asr_max_retry: int = 3
    # 长回放切片：单分片最长时长（秒）与最大体积（MB）
    siliconflow_asr_chunk_seconds: int = 480
    siliconflow_asr_chunk_max_mb: int = 20
    # 接口不返回时间戳时，是否退回按字数估算时间轴（可用但精度下降）
    siliconflow_asr_allow_estimated_timestamps: bool = True

    # LLM（A2）：重点 / 分层总结 / 两级思维导图
    siliconflow_model: str = "Qwen/Qwen3-8B"
    siliconflow_timeout: int = 180
    siliconflow_max_retry: int = 3
    # 单次投喂的最大转写字符数，超出后按时间窗口分段做 map-reduce（docs/00:129）
    siliconflow_max_input_chars: int = 12000

    platform_base_url: str = ""
    platform_video_formats: str = "mp4,flv,hls"
    platform_request_timeout: int = 60
    platform_cas_login_url: str = "https://mis.bjtu.edu.cn"
    # 后台自动登录回退凭证（可选）：pipeline 无前端交互时使用；前台登录优先走 API 透传
    platform_username: str = ""
    platform_password: str = ""

    platform_captcha_mode: str = "manual"
    platform_cookie_ttl: int = 28800

    task_total_timeout: int = 3600
    task_max_concurrent: int = 2
    timestamp_tolerance_sec: int = 2
    # 平台 VTT 字幕覆盖时长占比达到该阈值时直接复用，不再调用 ASR（docs/10:948）
    vtt_min_coverage: float = 0.5

    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_endpoint: str = ""
    oss_bucket_name: str = ""
    oss_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()