#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GreenTea — 硬压脚本（支持多进程 + GPU加速（如果有的话））
 字幕硬压+章节封装（有xml章节文件自动处理功能，如有xml无需单独生成mp4章节文件）
 支持launch一键调用或是单独运行，单独运行请更改SHOW_NAME为番剧英文名称
指令示例
CPU
Cython3 hardsub.py --max-workers 8
GPU
python3 hardsub.py --gpu --max-workers 4
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
import concurrent.futures
import xml.etree.ElementTree as ET

# ================== 可配置 ==================

GROUP = "Studio GreenTea"
SHOW_NAME = None #示例"Silent Witch - Chinmoku no Majo no Kakushigoto"
SOURCE = "WebRip"

RAW_DIR = Path("raw")
SUB_DIR = Path("ass")
OUT_DIR = Path("out")
CHAPTER_DIR = Path("chapters")

FORCE_1080P = True

# CPU x265 settings
CPU_PRESET = "slow"
CPU_CRF = 18

# GPU NVENC settings
GPU_PRESET = "slow"
GPU_CRF = 18

# 要硬压的字幕类型
SUB_SUFFIX_LIST = ["JPSC", "JPTC"]

# 默认多进程数量
DEFAULT_WORKERS = 2

# ============================================================

def parse_time_to_ms(ts: str) -> int:
    """
    将 MKVToolNix XML 的 ChapterTimeStart 转为毫秒（整数）
    ffmpeg 的 ffmetadata 必须是毫秒整数
    """
    ts = ts.strip()

    # 分离小数部分
    if "." in ts:
        main, sub = ts.split(".")
    else:
        main, sub = ts, "0"

    # 解析 h:m:s
    h, m, s = map(int, main.split(":"))

    # 解析小数（统一转成毫秒）
    # 例如：
    #   "4" → "400"
    #   "45" → "450"
    #   "456700000" → "456"
    if len(sub) > 3:
        sub = sub[:3]   # 截断到毫秒
    else:
        sub = sub.ljust(3, "0")  # 补齐到 3 位毫秒

    ms = int(sub)

    # 总毫秒
    return (h * 3600 + m * 60 + s) * 1000 + ms


def parse_chapters_xml_to_ffmetadata(xml_path: Path) -> Path:
    """
    将 MKVToolNix XML 章节转换成 ffmpeg 的 ffmetadata 格式（毫秒精确）
    """
    try:
        tree = ET.parse(xml_path)
    except Exception as e:
        print(f"[ERROR] 无法解析章节 XML: {xml_path}, {e}")
        return None

    root = tree.getroot()

    chapters = []

    for atom in root.findall(".//ChapterAtom"):
        t = atom.find("ChapterTimeStart")
        name_elem = atom.find(".//ChapterString")

        if t is None:
            continue

        start_ms = parse_time_to_ms(t.text)
        name = name_elem.text.strip() if name_elem is not None else "Chapter"

        chapters.append((start_ms, name))

    if not chapters:
        return None

    ffmeta = xml_path.with_suffix(".ffmeta")

    with ffmeta.open("w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")

        for i, (start, name) in enumerate(chapters):
            if i + 1 < len(chapters):
                end = chapters[i + 1][0] - 1
            else:
                end = start + 1000  # 最后 1 秒

            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={start}\n")
            f.write(f"END={end}\n")
            f.write(f"title={name}\n")

    print(f"[INFO] 已生成 ffmetadata 章节：{ffmeta}")
    return ffmeta



def run(cmd: list):
    """执行命令并打印"""
    print("[CMD]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def guess_episode_number(basename: str) -> str:
    """集数识别逻辑（与 soft 一致）"""
    m = re.search(r"[Ss]\d+[EePp](\d{2,3})", basename)
    if m:
        return m.group(1).zfill(2)

    m = re.search(r"[EePp](\d{2,3})", basename)
    if m:
        return m.group(1).zfill(2)

    m = re.search(r"\b(\d{2,3})\b", basename)
    if m:
        return m.group(1).zfill(2)

    nums = re.findall(r"(\d{2})", basename)
    if nums:
        return nums[-1]

    return "01"


def build_output_name(ep: str, suffix: str) -> str:
    """符合你提供的硬压命名规范"""
    return (
        f"[{GROUP}] {SHOW_NAME} [{ep}][{SOURCE}]"
        f"[HEVC-10bit 1080p AAC][{suffix}].mp4"
    )



def encode_hardsub(video: Path, ass: Path, out_path: Path, chapter_xml: Path, gpu: bool):
    """执行 ffmpeg 硬压（固定码率 3000k + 音频 copy + 正确章节处理）"""

    VIDEO_BITRATE = "3000k"

    # ----------- VF（字幕 + 缩放）-----------
    if FORCE_1080P:
        vf = (
            f"ass='{ass}',"
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(1920-iw)/2:(1080-ih)/2"
        )
    else:
        vf = f"ass='{ass}'"

    # ----------- 如果有 XML，先转成 ffmetadata ----------
    chapter_meta = None
    if chapter_xml and chapter_xml.exists():
        chapter_meta = parse_chapters_xml_to_ffmetadata(chapter_xml)

    # ----------- 先放所有输入 -----------
    cmd = ["ffmpeg", "-i", str(video)]
    if chapter_meta:
        cmd += ["-i", str(chapter_meta)]  # 第二输入：ffmetadata（只带章节）

    # ----------- 下面才是输出相关参数（滤镜 / 编码）-----------

    # 视频滤镜
    cmd += ["-filter:v", vf]

    # 编码器选择
    if gpu:
        cmd.extend([
            "-c:v", "hevc_nvenc",
            "-preset", GPU_PRESET,
            "-b:v", "3000k",
            "-maxrate", "3000k",
            "-bufsize", "6000k",
            "-pix_fmt", "p010le",
        ])

    # ----------- CPU x265 -----------
    else:
        cmd.extend([
            "-c:v", "libx265",
            "-preset", CPU_PRESET,
            "-b:v", "3000k",
            "-maxrate", "3000k",
            "-bufsize", "6000k",
            "-pix_fmt", "yuv420p10le",
        ])

    # 音频直接复制
    cmd += ["-c:a", "copy"]

    # 映射 ffmetadata 里的章节和元数据（只要第二个输入存在）
    if chapter_meta:
        cmd += ["-map_metadata", "1"]

    # 输出文件
    cmd += ["-y", str(out_path)]

    run(cmd)





def process_one_video(video_path: str, gpu: bool):
    """多进程任务入口：一集内做所有字幕版本"""
    video = Path(video_path)
    basename = video.stem
    ep = guess_episode_number(basename)

    print(f"\n========== 开始硬压 {basename} ==========")

    chapter_xml = CHAPTER_DIR / f"{basename}.xml"
    if not chapter_xml.exists():
        print(f"[INFO] 未找到章节：{chapter_xml}")


    for suffix in SUB_SUFFIX_LIST:
        ass = SUB_DIR / f"{basename} {suffix}.ass"
        if not ass.exists():
            print(f"[WARN] 跳过 {suffix}：未找到字幕 {ass}")
            continue

        out_name = build_output_name(ep, suffix)
        out_path = OUT_DIR / out_name

        print(f"\n=== Hardsub {suffix} → {out_path.name} ===")
        encode_hardsub(video, ass, out_path, chapter_xml, gpu)

    print(f"[DONE] 完成 {basename}")


def main():
    parser = argparse.ArgumentParser(
        description="GreenTea Hardsub 多进程 GPU/CPU 脚本"
    )

    parser.add_argument(
        "--gpu",
        action="store_true",
        help="使用 GPU (NVENC) 进行硬压"
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"并行进程数（默认 {DEFAULT_WORKERS}）"
    )

    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    videos = sorted(RAW_DIR.glob("*.mkv"))
    if not videos:
        print("[ERROR] raw/ 中没有找到 MKV")
        sys.exit(1)

    print(f"[INFO] 找到 {len(videos)} 个源视频，使用 {args.max_workers} 个进程")

    # 多进程
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.max_workers) as exe:
        futures = [
            exe.submit(process_one_video, str(v), args.gpu)
            for v in videos
        ]

        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print("[ERROR] 任务失败：", e)

    print("\n 全部硬压任务完成！输出目录：", OUT_DIR)


if __name__ == "__main__":
    main()
