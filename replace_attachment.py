#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
单集章节文件+子集文件整合脚本：
用于给压制完成的MKV和MP4更换子集文件或是章节文件
保持字体附件 + 替换章节 + 子集

使用方法：
1.将压制好的视频放在input文件夹下
2.将所有子集化完成的文件保存在fonts_sub文件夹下！！！注意直接放在该目录下，不要有额外文件！！！对应好分集
3.运行此脚本，或是在跟目录下运行终端并执行python3 replace_attachment.py
4.输出在out
"""

import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
import uuid
import shutil

INPUT_DIR = Path("input")
CHAPTER_DIR = Path("chapters")
FONT_DIR = Path("fonts_sub")   # 字体目录（可选）
OUT_DIR = Path("out")

OUT_DIR.mkdir(exist_ok=True)


def run(cmd):
    print("[CMD]", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)



# -------------------------------------------------------------------
#  1) XML → FFmetadata（用于 mp4）
# -------------------------------------------------------------------
def xml_to_ffmetadata(xml_path: Path) -> Path:
    if not xml_path.exists():
        print(f"[WARN] XML 不存在：{xml_path}")
        return None

    tree = ET.parse(xml_path)
    root = tree.getroot()

    chapters = []
    time_re = re.compile(r"(\d+):(\d{2}):(\d{2})(?:\.(\d+))?")

    def ts_to_ms(ts: str):
        m = time_re.match(ts)
        h = int(m.group(1))
        mm = int(m.group(2))
        s = int(m.group(3))
        frac = (m.group(4) or "0").ljust(3, "0")[:3]
        return (h*3600 + mm*60 + s)*1000 + int(frac)

    for atom in root.findall(".//ChapterAtom"):
        t = atom.find("ChapterTimeStart")
        n = atom.find(".//ChapterString")
        if t is None:
            continue
        chapters.append((ts_to_ms(t.text.strip()), n.text.strip() if n is not None else "Chapter"))

    if not chapters:
        return None

    chapters.sort(key=lambda x: x[0])

    out = xml_path.with_suffix(".ffmeta")
    with out.open("w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        for i, (start, title) in enumerate(chapters):
            end = (chapters[i+1][0] - 1) if i+1 < len(chapters) else (start + 1000)
            if end <= start:
                end = start + 1
            f.write("[CHAPTER]\nTIMEBASE=1/1000\n")
            f.write(f"START={start}\nEND={end}\ntitle={title}\n")

    print(f"[INFO] 生成 ffmetadata：{out.name}")
    return out




# -------------------------------------------------------------------
#  2) 字体收集
# -------------------------------------------------------------------
def collect_fonts():
    fonts = [f for f in FONT_DIR.iterdir() if f.suffix.lower() in (".ttf", ".otf")]
    print(f"[INFO] 找到 {len(fonts)} 个字体")
    return fonts



# -------------------------------------------------------------------
#  3) MKV：保留原有内容 + 添加字体 + 替换章节（绝不会丢失子集）
# -------------------------------------------------------------------
def process_mkv(video: Path, xml_file: Path, fonts):
    print(f"\n=== 处理 MKV {video.name} ===")

    tmp = OUT_DIR / f"tmp_{uuid.uuid4().hex}.mkv"
    final = OUT_DIR / video.name

    # 必须先禁用原章节和原附件，否则所有附件会被覆盖掉
    cmd = [
        "mkvmerge",
        "-o", str(tmp),

        "--no-chapters",        # 删除原章节
        "--no-attachments",     # 删除原附件（否则后面会被覆盖）
        
        "--chapters", str(xml_file),  # 写入新章节
    ]

    # 附加字体（必须在 input 文件前）
    for f in fonts:
        cmd += [
            "--attachment-mime-type", "application/x-truetype-font",
            "--attach-file", str(f)
        ]

    # 最后再放输入文件，否则附件会被覆盖
    cmd += [str(video)]

    run(cmd)

    if final.exists():
        final.unlink()
    tmp.rename(final)

    print(f"[DONE] MKV 输出：{final.name}")




# -------------------------------------------------------------------
#  4) MP4：保持视频 + 写入 ffmetadata 章节
# -------------------------------------------------------------------
def process_mp4(video: Path, xml_file: Path):

    print(f"\n=== 处理 MP4 {video.name} ===")

    ffmeta = xml_to_ffmetadata(xml_file)
    if not ffmeta:
        print("[WARN] 无法生成 ffmeta，跳过")
        return

    out = OUT_DIR / video.name

    cmd = [
        "ffmpeg",
        "-i", str(video),
        "-i", str(ffmeta),
        "-map", "0",
        "-map_metadata", "1",
        "-map_chapters", "1",
        "-codec", "copy",
        "-y", str(out)
    ]

    run(cmd)

    print(f"[DONE] MP4 输出：{out.name}")



# -------------------------------------------------------------------
#  5) 主程序
# -------------------------------------------------------------------
def main():

    videos = sorted(INPUT_DIR.glob("*.*"))
    fonts = collect_fonts()

    print(f"[INFO] 总视频：{len(videos)}\n")

    for video in videos:

        # 提取 show + ep
        m = re.search(r"\] (.+?) \[(\d{2,3})\]", video.name)
        if not m:
            print(f"[WARN] 无法识别番名/集数：{video.name}")
            continue

        show = m.group(1)
        ep = m.group(2)
        base = f"{show} {ep}"

        xml = CHAPTER_DIR / f"{base}.xml"
        if not xml.exists():
            print(f"[WARN] 找不到章节：{xml.name}")
            continue

        # 分格式处理
        if video.suffix.lower() == ".mkv":
            process_mkv(video, xml, fonts)
        elif video.suffix.lower() == ".mp4":
            process_mp4(video, xml)
        else:
            print(f"[WARN] 不支持：{video.name}")

    print("\n🎉 所有文件完成：已替换章节 + 保留附加字体（子集）")


if __name__ == "__main__":
    main()
