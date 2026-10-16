"""本地测试脚本：用本地视频文件或 HLS URL 测试完整解析流程。

用法:
    # 本地 .ts / .mp4 文件
    python scripts/test_pipeline_local.py path/to/video.ts

    # HLS URL
    python scripts/test_pipeline_local.py "https://example.com/playlist.m3u8"

    # 跳过音频提取，直接用已有 wav
    python scripts/test_pipeline_local.py --wav storage/audios/5.wav

    # 只跑 ASR 不跑 LLM
    python scripts/test_pipeline_local.py path/to/video.ts --no-llm

流程: 提取音频(ffmpeg) → ASR 转写 → LLM 生成重点/总结/导图 → 输出结果
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from loguru import logger

from app.config import settings
from app.pipeline.retry import with_retry

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


def step(msg: str) -> None:
    logger.info(f"▶ {msg}")


@with_retry(max_attempts=settings.siliconflow_max_retry, step_name="test-keypoints")
def _llm_keypoints(text: str, course_title: str) -> list[dict]:
    from app.integrations import siliconflow_llm
    return siliconflow_llm.extract_keypoints(text, course_title)


@with_retry(max_attempts=settings.siliconflow_max_retry, step_name="test-summary")
def _llm_summary(text: str, course_title: str) -> dict:
    from app.integrations import siliconflow_llm
    return siliconflow_llm.generate_summary(text, course_title)


@with_retry(max_attempts=settings.siliconflow_max_retry, step_name="test-mindmap")
def _llm_mindmap(text: str, course_title: str) -> dict:
    from app.integrations import siliconflow_llm
    return siliconflow_llm.generate_mindmap(text, course_title)


def extract_audio(source: str, out_path: str) -> str:
    """用 ffmpeg 从视频文件或 HLS URL 提取音频 → 16kHz 单声道 WAV。"""
    import ffmpeg

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    is_url = source.startswith("http")
    step(f"提取音频: {source[:80]}{'...' if len(source) > 80 else ''} → {out_path}")

    input_kwargs = {"protocol_whitelist": "https,http,tcp,tls"} if is_url else {}
    (
        ffmpeg.input(source, **input_kwargs)
        .audio
        .output(str(out), acodec="pcm_s16le", ar="16000", ac=1)
        .overwrite_output()
        .global_args("-loglevel", "warning")
        .run()
    )

    size_mb = out.stat().st_size / 1024 / 1024
    logger.info(f"  ✓ 音频文件 {size_mb:.1f}MB")
    return str(out)


def run_asr(audio_path: str) -> list[dict]:
    """调用硅基流动 ASR 转写。"""
    from app.integrations import siliconflow_asr

    step(f"ASR 转写: {audio_path}")
    t0 = time.time()
    sentences = siliconflow_asr.transcribe(audio_path)
    elapsed = time.time() - t0
    logger.info(f"  ✓ {len(sentences)} 句，耗时 {elapsed:.1f}s")

    for s in sentences[:5]:
        start = s.get("start_sec", 0)
        text = s.get("text", "")
        logger.info(f"    [{start:.1f}s] {text[:60]}")
    if len(sentences) > 5:
        logger.info(f"    ... 共 {len(sentences)} 句")
    return sentences


def run_llm(transcripts: list[dict], course_title: str = "测试课程", out_dir: Path | None = None) -> None:
    """调用 LLM 生成重点/总结/导图。"""
    text = "\n".join(
        f"[{float(t.get('start_sec', 0)):.1f}] {t.get('text', '')}"
        for t in transcripts if t.get("text", "").strip()
    )
    if not text:
        logger.warning("转写为空，跳过 LLM")
        return

    failures: list[str] = []

    step("LLM 生成重点")
    try:
        t0 = time.time()
        keypoints = _llm_keypoints(text, course_title)
        logger.info(f"  ✓ {len(keypoints)} 条重点，耗时 {time.time() - t0:.1f}s")
        for kp in keypoints[:3]:
            logger.info(f"    [{kp.get('timestamp_sec', 0):.0f}s] {kp.get('title', '')}")
        if out_dir:
            p = out_dir / "keypoints.json"
            p.write_text(json.dumps(keypoints, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"  重点已保存: {p}")
    except Exception as e:
        logger.error(f"  ✗ 重点生成失败: {e}")
        failures.append("keypoints")

    step("LLM 生成总结")
    try:
        t0 = time.time()
        summary = _llm_summary(text, course_title)
        logger.info(f"  ✓ 总结生成完成，耗时 {time.time() - t0:.1f}s")
        overview = summary.get("overview", "")
        logger.info(f"    概述: {overview[:120]}...")
        if out_dir:
            p = out_dir / "summary.json"
            p.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"  总结已保存: {p}")
    except Exception as e:
        logger.error(f"  ✗ 总结生成失败: {e}")
        failures.append("summary")

    step("LLM 生成思维导图")
    try:
        t0 = time.time()
        mindmap = _llm_mindmap(text, course_title)
        logger.info(f"  ✓ 导图生成完成，耗时 {time.time() - t0:.1f}s")
        logger.info(f"    根节点: {mindmap.get('root_topic', '')}")
        if out_dir:
            p = out_dir / "mindmap.json"
            p.write_text(json.dumps(mindmap, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"  导图已保存: {p}")
    except Exception as e:
        logger.error(f"  ✗ 导图生成失败: {e}")
        failures.append("mindmap")

    if failures:
        logger.warning(f"部分失败: {failures}")


def main():
    parser = argparse.ArgumentParser(description="本地测试解析流程")
    parser.add_argument("source", nargs="?", help="视频文件路径或 HLS URL")
    parser.add_argument("--wav", help="直接使用已有 WAV 文件，跳过音频提取")
    parser.add_argument("--no-llm", action="store_true", help="只跑 ASR，不跑 LLM")
    parser.add_argument("--no-asr", action="store_true", help="跳过 ASR（需配合 --transcripts）")
    parser.add_argument("--transcripts", help="已有转写 JSON 文件，跳过 ASR")
    parser.add_argument("--title", default="测试课程", help="课程标题")
    parser.add_argument("--out-dir", default="storage/test", help="输出目录")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_path = args.wav

    # Step 1: 提取音频
    if not audio_path and not args.transcripts:
        if not args.source:
            parser.error("需要提供 source 或 --wav 或 --transcripts")
        audio_path = str(out_dir / "audio.wav")
        extract_audio(args.source, audio_path)

    # Step 2: ASR 转写
    transcripts: list[dict] = []
    if not args.no_asr:
        if args.transcripts:
            step(f"加载已有转写: {args.transcripts}")
            transcripts = json.loads(Path(args.transcripts).read_text(encoding="utf-8"))
            logger.info(f"  ✓ {len(transcripts)} 句")
        elif audio_path:
            transcripts = run_asr(audio_path)
            tp = out_dir / "transcripts.json"
            tp.write_text(json.dumps(transcripts, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"  转写已保存: {tp}")
    elif args.transcripts:
        transcripts = json.loads(Path(args.transcripts).read_text(encoding="utf-8"))

    # Step 3: LLM 解析
    if not args.no_llm and transcripts:
        run_llm(transcripts, args.title, out_dir)

    logger.info("完成")


if __name__ == "__main__":
    main()