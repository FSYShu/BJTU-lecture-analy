"""A1：硅基流动 ASR 客户端测试。

全部走 mock 传输层，不产生真实 API 调用、不消耗额度；
覆盖分片偏移、segments/words/text 三种返回形态与时间戳校验。
"""
from __future__ import annotations

import wave
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.integrations import siliconflow_asr


def _write_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("POST", "https://example.invalid"))


@pytest.fixture()
def wav_file(tmp_path: Path) -> Path:
    return _write_wav(tmp_path / "audio.wav", 1.0)


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def test_from_segments_applies_offset():
    sentences = siliconflow_asr._sentences_from_payload(
        {"segments": [{"start": 0.0, "end": 2.0, "text": "开场。"},
                      {"start": 2.0, "end": 4.5, "text": "定义。"}]},
        offset=100.0,
        chunk_end=120.0,
    )
    assert [s["text"] for s in sentences] == ["开场。", "定义。"]
    assert sentences[0]["start_sec"] == 100.0
    assert sentences[1]["end_sec"] == 104.5


def test_from_words_groups_into_sentences():
    words = [
        {"word": "傅", "start": 0.0, "end": 0.4},
        {"word": "里", "start": 0.4, "end": 0.8},
        {"word": "叶。", "start": 0.8, "end": 1.2},
        {"word": "下一句", "start": 1.2, "end": 2.0},
    ]
    sentences = siliconflow_asr._sentences_from_payload({"words": words}, offset=0.0, chunk_end=3.0)
    assert [s["text"] for s in sentences] == ["傅里叶。", "下一句"]


def test_from_text_estimates_timeline(monkeypatch):
    monkeypatch.setattr(settings, "siliconflow_asr_allow_estimated_timestamps", True)
    sentences = siliconflow_asr._from_text("第一句。第二句更长一些。", 0.0, 10.0, estimated=True)
    assert [s["text"] for s in sentences] == ["第一句。", "第二句更长一些。"]
    assert sentences[0]["start_sec"] == 0.0
    assert sentences[-1]["end_sec"] == pytest.approx(10.0)
    # 时间按字数比例分配：更长的一句占用更多时长
    assert (sentences[1]["end_sec"] - sentences[1]["start_sec"]) > (
        sentences[0]["end_sec"] - sentences[0]["start_sec"]
    )


def test_from_text_raises_when_estimation_disabled(monkeypatch):
    monkeypatch.setattr(settings, "siliconflow_asr_allow_estimated_timestamps", False)
    with pytest.raises(RuntimeError):
        siliconflow_asr._from_text("句子。", 0.0, 5.0, estimated=True)


def test_payload_without_text_or_segments_returns_empty():
    """空分片（静音段）应跳过而非报错（docs/05 风险处理）。"""
    result = siliconflow_asr._sentences_from_payload({}, offset=0.0, chunk_end=1.0)
    assert result == []


def test_validate_is_monotonic_and_drops_blank():
    cleaned = siliconflow_asr._validate([
        {"text": "A", "start_sec": 5.0, "end_sec": 7.0},
        {"text": "B", "start_sec": 6.0, "end_sec": 6.2},  # 时间回退且 end<=start
        {"text": "   ", "start_sec": 9.0, "end_sec": 10.0},
        {"text": "C", "start_sec": -3.0, "end_sec": -1.0},  # 负数起点，先归零再顺延
    ])
    assert [item["text"] for item in cleaned] == ["A", "B", "C"]
    assert cleaned[1]["start_sec"] >= cleaned[0]["end_sec"]
    assert cleaned[1]["end_sec"] > cleaned[1]["start_sec"]
    # 负数起点先归零 (0.0)，再因单调性顺延到前一句 end_sec
    assert cleaned[2]["start_sec"] >= cleaned[1]["end_sec"]


# --------------------------------------------------------------------------- #
# 分片与端到端
# --------------------------------------------------------------------------- #
def test_transcribe_single_chunk(monkeypatch, wav_file):
    monkeypatch.setattr(settings, "siliconflow_api_key", "test-key")
    monkeypatch.setattr(settings, "siliconflow_asr_chunk_seconds", 30)
    calls: list[str] = []

    def fake_post(client, path, data):
        calls.append(path.name)
        return _ok({"segments": [{"start": 0.0, "end": 0.5, "text": "你好。"}]})

    monkeypatch.setattr(siliconflow_asr, "_post", fake_post)
    out = siliconflow_asr.transcribe(str(wav_file))
    assert out == [{"text": "你好。", "start_sec": 0.0, "end_sec": 0.5}]
    assert calls == ["chunk_0000.wav"]


def test_transcribe_multi_chunk_offsets(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "siliconflow_api_key", "test-key")
    monkeypatch.setattr(settings, "siliconflow_asr_chunk_seconds", 1)
    audio = _write_wav(tmp_path / "long.wav", 2.5)

    def fake_post(client, path, data):
        return _ok({"segments": [{"start": 0.0, "end": 0.5, "text": "句子。"}]})

    monkeypatch.setattr(siliconflow_asr, "_post", fake_post)
    out = siliconflow_asr.transcribe(str(audio))
    assert [round(item["start_sec"], 1) for item in out] == [0.0, 1.0, 2.0]


def test_transcribe_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "siliconflow_api_key", "test-key")
    with pytest.raises(RuntimeError):
        siliconflow_asr.transcribe(str(tmp_path / "nope.wav"))


def test_transcribe_requires_api_key(monkeypatch, wav_file):
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    with pytest.raises(RuntimeError):
        siliconflow_asr.transcribe(str(wav_file))


def test_transcribe_falls_back_to_plain_params(monkeypatch, wav_file):
    """接口拒绝 verbose_json 时退回基础参数（HTTP 400 → 重试一次）。"""
    monkeypatch.setattr(settings, "siliconflow_api_key", "test-key")
    monkeypatch.setattr(settings, "siliconflow_asr_chunk_seconds", 30)
    seen: list[dict] = []

    def fake_post(client, path, data):
        seen.append(dict(data))
        if len(seen) == 1:
            return httpx.Response(400, json={"message": "unsupported"},
                                  request=httpx.Request("POST", "https://example.invalid"))
        return _ok({"text": "纯文本。"})

    monkeypatch.setattr(siliconflow_asr, "_post", fake_post)
    out = siliconflow_asr.transcribe(str(wav_file))
    assert len(seen) == 2
    assert "response_format" in seen[0] and "response_format" not in seen[1]
    assert out[0]["text"] == "纯文本。"


def test_transcribe_sends_bearer_token(monkeypatch, wav_file):
    """用 respx 校验真实 httpx 请求：URL、鉴权头与 multipart 字段。"""
    respx = pytest.importorskip("respx")
    monkeypatch.setattr(settings, "siliconflow_api_key", "test-key")
    monkeypatch.setattr(settings, "siliconflow_base_url", "https://api.siliconflow.cn/v1")
    monkeypatch.setattr(settings, "siliconflow_asr_chunk_seconds", 30)

    route = respx.post("https://api.siliconflow.cn/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"segments": [{"start": 0.0, "end": 1.0, "text": "测试。"}]})
    )
    out = siliconflow_asr.transcribe(str(wav_file))
    assert route.called
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer test-key"
    assert out[0]["text"] == "测试。"
