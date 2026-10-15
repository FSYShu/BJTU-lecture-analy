"""讯飞 ASR 客户端。输出带句级时间戳的转写。

对应 docs/05-risk-handling.md API 异常降级。
"""
import httpx

from app.config import settings


def transcribe(audio_path: str) -> list[dict]:
    """返回 [{"text", "start_sec", "end_sec"}, ...]。

    TODO: 实现讯飞 ASR 鉴权（hmac-sha256 签名）+ 上传音频/分片 + 轮询识别结果。
    MVP 占位：调用讯飞长音频识别接口，解析返回的句级时间戳。
    """
    if not settings.xfyun_app_id or not settings.xfyun_api_key:
        raise RuntimeError("讯飞 ASR 凭证未配置")
    raise NotImplementedError("讯飞 ASR 调用实现待补充")