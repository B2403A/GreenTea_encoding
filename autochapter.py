#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自动分析 ASS 文件生成章节 XML，并自动生成 MP4 可用的 ffmeta
功能：
1. 自动扫描 OP/ED 字体样式 → 自动定位 OP / ED 起点
2. 用户可输入偏移秒数自动生成 OP 结束时间（默认 90 秒）
3. 自动生成 MKV xml + ffmpeg ffmetadata
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
import datetime

ASS_DIR = Path("ass")
OUT_DIR = Path("chapters")
OUT_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------
# 工具函数：ASS 时间格式 → 秒数
# ------------------------------------------------------------
def ass_time_to_seconds(ts: str) -> float:
    """
    ASS 格式：0:01:23.45 → 秒(float)
    """
    h, m, s = ts.split(":")
    sec = float(s)
    return int(h) * 3600 + int(m) * 60 + sec


def seconds_to_timestamp(sec: float) -> str:
    """
    秒 → MKV XML 章节格式：HH:MM:SS.mmm
    """
    ms = int((sec - int(sec)) * 1000)
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


# ------------------------------------------------------------
# 工具函数：解析 XML → ffmetadata
# ------------------------------------------------------------
def parse_time_to_ms(ts: str) -> int:
    """
    MKV XML 时间戳 → 毫秒
    """
    ts = ts.strip()
    if "." in ts:
        main, sub = ts.split(".")
    else:
        main, sub = ts, "0"

    h, m, s = map(int, main.split(":"))

    if len(sub) > 3:
        sub = sub[:3]
    else:
        sub = sub.ljust(3, "0")

    return (h * 3600 + m * 60 + s) * 1000 + int(sub)


def xml_to_ffmetadata(xml_path: Path) -> Path:
    """
    XML → MP4 ffmetadata
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    chapters = []

    for atom in root.findall(".//ChapterAtom"):
        ts = atom.find("ChapterTimeStart").text
        name_elem = atom.find(".//ChapterString")
        title = name_elem.text if name_elem is not None else "Chapter"
        chapters.append((parse_time_to_ms(ts), title))

    if not chapters:
        print("[WARN] 没有任何章节")
        return None

    out_path = xml_path.with_suffix(".ffmeta")

    with out_path.open("w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")

        for i, (start, title) in enumerate(chapters):
            if i + 1 < len(chapters):
                end = chapters[i + 1][0] - 1
            else:
                end = start + 1000

            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={start}\n")
            f.write(f"END={end}\n")
            f.write(f"title={title}\n")

    print(f"[INFO] 已生成 ffmeta：{out_path.name}")
    return out_path


# ------------------------------------------------------------
# 自动解析 OP / ED 时间
# ------------------------------------------------------------
def detect_op_ed(ass_file: Path):
    """
    自动识别 OP / ED 的开始时间
    依据：
    - Style 名包含 "OP" / "ED"
    - 读取第一条匹配对话行的 Start 时间
    """
    op_time = None
    ed_time = None

    dialogue_re = re.compile(r"Dialogue: \d+?,([^,]+),([^,]+),([^,]+),")

    with ass_file.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            if not line.startswith("Dialogue:"):
                continue

            m = dialogue_re.match(line)
            if not m:
                continue

            layer = m.group(1)
            start = m.group(2)
            style = m.group(3).strip()

            start_sec = ass_time_to_seconds(start)

            # 匹配 OP
            if "OP" in style.upper() and op_time is None:
                op_time = start_sec

            # 匹配 ED
            if "ED" in style.upper() and ed_time is None:
                ed_time = start_sec

    return op_time, ed_time


# ------------------------------------------------------------
# 生成 XML + FFMETA
# ------------------------------------------------------------
def generate_chapters(ass_file: Path):
    print(f"\n=== 解析：{ass_file.name} ===")

    op_start, ed_start = detect_op_ed(ass_file)

    if not op_start:
        print("[WARN] 未找到 OP 起始")
    if not ed_start:
        print("[WARN] 未找到 ED 起始")

    # 输入 OP 偏移
    offset_input = input("请输入 OP 时长偏移秒（默认 90 秒）：").strip()
    offset = float(offset_input) if offset_input else 90.0

    chapter_list = []

    # OP
    if op_start:
        chapter_list.append(("OP", op_start))
        chapter_list.append(("Chapter 1", op_start + offset))

    # ED
    if ed_start:
        chapter_list.append(("ED", ed_start))

    # 排序
    chapter_list.sort(key=lambda x: x[1])

    # XML 输出
    ep = ass_file.stem
    xml_path = OUT_DIR / f"{ep}.xml"

    with xml_path.open("w", encoding="utf-8") as f:
        f.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        f.write("<Chapters>\n")
        f.write("  <EditionEntry>\n")

        for title, sec in chapter_list:
            ts = seconds_to_timestamp(sec)
            f.write("    <ChapterAtom>\n")
            f.write(f"      <ChapterTimeStart>{ts}</ChapterTimeStart>\n")
            f.write(f"      <ChapterDisplay>\n")
            f.write(f"        <ChapterString>{title}</ChapterString>\n")
            f.write("      </ChapterDisplay>\n")
            f.write("    </ChapterAtom>\n")

        f.write("  </EditionEntry>\n")
        f.write("</Chapters>\n")

    print(f"[INFO] 已生成 XML：{xml_path.name}")

    # 同时生成 ffmetadata
    xml_to_ffmetadata(xml_path)


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
def main():
    ass_files = sorted(ASS_DIR.glob("*.ass"))
    if not ass_files:
        print("[ERROR] ass 文件夹为空")
        return

    for ass in ass_files:
        generate_chapters(ass)


if __name__ == "__main__":
    main()
