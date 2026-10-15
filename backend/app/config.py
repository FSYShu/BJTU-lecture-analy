"""应用配置加载。从 .env 读取，pydantic-settings 做类型校验。

对应 docs/06-env-vars.md 全部环境变量。禁止硬编码密钥。
"""
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

    secret_key: str = "change-me-to-a-strong-random-secret"
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

    xfyun_app_id: str = ""
    xfyun_api_key: str = ""
    xfyun_api_secret: str = ""
    xfyun_asr_lang: str = "zh-CN"
    xfyun_asr_timeout: int = 120
    xfyun_asr_max_retry: int = 3

    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "deepseek-ai/DeepSeek-V3"
    siliconflow_timeout: int = 180
    siliconflow_max_retry: int = 3

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