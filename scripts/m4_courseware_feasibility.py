"""M4 课件流可行性验证：抽帧 + 感知哈希换页检测实验脚本。

用法：
    uv run python scripts/m4_courseware_feasibility.py --stream <vgaStreamHlsUrl> [--interval 2] [--threshold 0.92]

功能：
1. 验证 vgaStreamHlsUrl 可播放（ffprobe 探测分辨率与帧率）
2. 按固定间隔抽帧（默认 2 秒/帧）
3. 对相邻帧计算感知哈希（pHash），相似度低于阈值时判定为换页
4. 输出换页时间点列表 + 相似度分布 + 阈值建议
"""
import argparse
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import imagehash
from PIL import Image


def probe_stream(stream_url: str) -> dict:
    """用 ffprobe 探测流信息：分辨率、帧率、时长。"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", stream_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return {"playable": False, "error": result.stderr[:200]}
    import json
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        return {"playable": False, "error": "无视频流"}
    return {
        "playable": True,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": eval(video.get("r_frame_rate", "0/1")),
        "duration": float(data.get("format", {}).get("duration", 0)),
        "codec": video.get("codec_name", ""),
    }


def extract_frames(stream_url: str, interval: float, out_dir: Path) -> list[Path]:
    """按固定间隔从流中抽帧，返回帧文件路径列表。"""
    cmd = [
        "ffmpeg", "-v", "quiet", "-y",
        "-i", stream_url,
        "-vf", f"fps=1/{interval}",
        "-frames:v", "300",
        str(out_dir / "frame_%04d.png"),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    frames = sorted(out_dir.glob("frame_*.png"))
    return frames


def compute_phashes(frames: list[Path]) -> list[tuple[int, str]]:
    """对每帧计算 pHash，返回 (帧序号, hash_hex) 列表。"""
    results = []
    for i, fp in enumerate(frames):
        img = Image.open(fp)
        h = imagehash.phash(img)
        results.append((i, str(h)))
    return results


def detect_page_changes(
    phashes: list[tuple[int, str]],
    threshold: float,
) -> list[dict]:
    """相邻帧 pHash 相似度低于阈值时判定换页，返回换页事件列表。"""
    changes = []
    similarities = []
    for i in range(1, len(phashes)):
        h1 = imagehash.hex_to_hash(phashes[i - 1][1])
        h2 = imagehash.hex_to_hash(phashes[i][1])
        diff = h1 - h2
        similarity = 1 - diff / 64.0
        similarities.append(similarity)
        if similarity < threshold:
            changes.append({
                "frame_idx": i,
                "similarity": round(similarity, 4),
                "hamming_dist": diff,
            })
    return changes, similarities


def suggest_threshold(similarities: list[float]) -> float:
    """基于相似度分布自动建议阈值：均值 - 2*标准差。"""
    if len(similarities) < 5:
        return 0.92
    mean = statistics.mean(similarities)
    std = statistics.stdev(similarities)
    suggested = mean - 2 * std
    return round(max(0.80, min(0.98, suggested)), 2)


def main():
    parser = argparse.ArgumentParser(description="M4 课件流可行性验证")
    parser.add_argument("--stream", required=True, help="vgaStreamHlsUrl 地址")
    parser.add_argument("--interval", type=float, default=2.0, help="抽帧间隔（秒），默认 2")
    parser.add_argument("--threshold", type=float, default=0.92, help="换页相似度阈值，默认 0.92")
    args = parser.parse_args()

    print(f"[1/4] 探测流信息: {args.stream[:80]}...")
    info = probe_stream(args.stream)
    if not info["playable"]:
        print(f"  ✗ 流不可播放: {info['error']}")
        sys.exit(1)
    print(f"  ✓ 可播放 | 分辨率 {info['width']}x{info['height']} | 帧率 {info['fps']:.1f}fps | 时长 {info['duration']:.0f}s | 编码 {info['codec']}")

    print(f"[2/4] 抽帧（间隔 {args.interval}s）...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        frames = extract_frames(args.stream, args.interval, tmp_dir)
        print(f"  ✓ 抽取 {len(frames)} 帧")

        if len(frames) < 2:
            print("  ✗ 帧数不足，无法计算相似度")
            sys.exit(1)

        print("[3/4] 计算感知哈希...")
        phashes = compute_phashes(frames)
        print(f"  ✓ 完成 {len(phashes)} 帧的 pHash 计算")

        print(f"[4/4] 换页检测（阈值 {args.threshold}）...")
        changes, similarities = detect_page_changes(phashes, args.threshold)
        print(f"  ✓ 检测到 {len(changes)} 次换页")
        for c in changes[:20]:
            frame_time = c["frame_idx"] * args.interval
            print(f"    帧 {c['frame_idx']} (≈{frame_time:.0f}s) | 相似度 {c['similarity']} | 汉明距离 {c['hamming_dist']}")

        suggested = suggest_threshold(similarities)
        print(f"\n--- 结论 ---")
        print(f"流可播放: ✓")
        print(f"抽帧成功: ✓ ({len(frames)} 帧)")
        print(f"感知哈希计算成功: ✓")
        print(f"换页检测: {len(changes)} 次 (阈值 {args.threshold})")
        print(f"相似度统计: min={min(similarities):.4f} max={max(similarities):.4f} mean={statistics.mean(similarities):.4f}")
        print(f"建议阈值: {suggested} (均值-2σ)")
        print(f"可行性: {'✓ 可行' if len(frames) > 10 else '✗ 帧数不足'}")


if __name__ == "__main__":
    main()