#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GreenTea 自动压制脚本（分集扫描+ttc拆分+子集化+章节整合）
 支持分集和字体扫描
 自动匹配字体内部名称
 子集化不损坏字体
 未使用字体自动剔除
 自动拆分 TTC
 自动封装字幕轨、子集字体、章节
 launch调用或是单独运行，单独运行请更改SHOW_NAME为番剧英文名称
"""

import argparse
import concurrent.futures
import re
import subprocess
import sys
from pathlib import Path
import shutil
from fontTools.ttLib import TTFont, TTCollection


# ================== 可配置 ==================

GROUP_TAG = "Studio GreenTea"
SHOW_NAME = None  #举例"Silent Witch - Chinmoku no Majo no Kakushigoto"
SOURCE_TAG = "WebRip"

RAW_DIR = Path("raw")
ASS_DIR = Path("ass")
CHAPTER_DIR = Path("chapters")
FONTS_DIR = Path("fonts")
FONTS_SUBSET_DIR = Path("fonts_sub")
WORK_DIR = Path("work")
OUT_DIR = Path("out")

RAW_PATTERN = "*.mkv"

SUBTITLE_TRACKS = [
    {"suffix": "SC", "language": "zh", "title": "SC"},
    {"suffix": "TC", "language": "zh", "title": "TC"},
    {"suffix": "JPSC", "language": "zh", "title": "JPSC"},
    {"suffix": "JPTC", "language": "zh", "title": "JPTC"},
]

FFMPEG_THREADS = 8
VIDEO_PRESET = "slow"
FORCE_1080P_16_9 = True
MAX_WORKERS = 2

DRY_RUN = False

# ============================================================
#                字体扫描 + 子集化
# ============================================================

def get_episode_font_dir(ep: str) -> Path:
    """
    根据集数生成 fonts_sub/E01/ 类目录
    """
    sub_dir = FONTS_SUBSET_DIR / f"E{ep}"
    sub_dir.mkdir(parents=True, exist_ok=True)
    return sub_dir


def extract_used_fonts_from_ass(ass_dir: Path) -> set:
    """扫描 ASS 文件提取所有字体名：Style 字体 + override 字体"""
    used = set()
    style_re = re.compile(r"Style:\s*[^,]+,([^,]+)")
    override_re = re.compile(r"\\fn([^\\}]+)")

    for ass in sorted(ass_dir.glob("*.ass")):
        with ass.open("r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                # Style 字体
                m = style_re.match(line)
                if m:
                    used.add(m.group(1).strip())

                # override 字体
                for fn in override_re.findall(line):
                    used.add(fn.strip())

    print(f"[INFO] ASS 中使用字体：{used}")
    return used


def get_font_internal_names(font_path: Path) -> set:
    """读取字体内部名称（FullName、PostScriptName）"""
    names = set()
    try:
        font = TTFont(str(font_path), lazy=True)
        for rec in font["name"].names:
            try:
                s = rec.toStr()
                if s:
                    names.add(s)
            except:
                pass
    except:
        pass
    return names


def split_ttc_to_ttfs(ttc_path: Path, out_dir: Path) -> list:
    """拆分 TTC 为多个 TTF，保留内部真实名称"""
    out = []
    try:
        ttc = TTCollection(str(ttc_path))
    except:
        return out

    for font in ttc.fonts:
        name_table = font["name"]
        ps = name_table.getName(6, 3, 1, 1033)
        full = name_table.getName(4, 3, 1, 1033)

        if ps:
            real = ps.toStr()
        elif full:
            real = full.toStr()
        else:
            real = f"{ttc_path.stem}_unknown"

        real = re.sub(r"[^A-Za-z0-9._-]+", "_", real)
        out_path = out_dir / f"{real}.ttf"
        try:
            font.save(out_path)
            out.append(out_path)
            print(f"[INFO] 拆分 TTC → {out_path.name}")
        except:
            pass

    return out


def subset_fonts(text_file: Path, fonts_dir: Path, episode_out_dir: Path, used_fonts: set):
    """对子集化 ASS 中使用的字体，并输出至 E01/ E02/ 等独立目录"""

    episode_out_dir.mkdir(parents=True, exist_ok=True)

    for font_path in sorted(fonts_dir.glob("*")):
        if font_path.suffix.lower() not in (".ttf", ".otf"):
            continue

        # 内部名称匹配
        internal_names = get_font_internal_names(font_path)
        match = any(name in used_fonts for name in internal_names)

        if not match:
            print(f"[SKIP] 未使用字体：{font_path.name}")
            continue

        out_path = episode_out_dir / f"{font_path.stem}.subset{font_path.suffix}"
        print(f"[Subset] Epi-Subset → {out_path.name}")

        cmd = [
            "pyftsubset", str(font_path),
            f"--output-file={out_path}",
            f"--text-file={text_file}",
            "--layout-features=*",
            "--glyph-names",
            "--symbol-cmap",
            "--retain-gids",
            "--name-IDs=*",
            "--name-legacy",
            "--name-languages=*",
        ]
        subprocess.run(cmd, check=True)



# ============================================================
#                       字幕字符收集
# ============================================================

def collect_chars_from_ass(ass_dir: Path, output_txt: Path):
    chars = set()

    for ass in sorted(ass_dir.glob("*.ass")):
        with ass.open("r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                for ch in line:
                    if ord(ch) >= 32:
                        chars.add(ch)

    # 加入 ASCII
    for i in range(0x20, 0x7F):
        chars.add(chr(i))

    output_txt.parent.mkdir(exist_ok=True)
    with output_txt.open("w", encoding="utf-8") as f:
        f.write("".join(sorted(chars)))

    print(f"[INFO] 共收集 {len(chars)} 字符 → {output_txt}")


# ============================================================
#                   视频编码 + Mux 封装
# ============================================================

def run_cmd(cmd):
    print("\n[CMD]", " ".join(str(c) for c in cmd))
    if DRY_RUN:
        return 0
    try:
        subprocess.run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 命令失败：{e}")
        return e.returncode


def guess_episode_number(name: str) -> str:
    m = re.search(r"\b(\d{2,3})\b", name)
    return m.group(1).zfill(2) if m else "01"


def build_final_filename(ep: str, sub_count: int):
    ass_tag = f"ASSx{sub_count}" if sub_count else "NO-SUB"
    return f"[{GROUP_TAG}] {SHOW_NAME} [{ep}][{SOURCE_TAG}][HEVC-10bit 1080p AAC {ass_tag}].mkv"


def encode_episode(raw_path: Path, work_dir: Path, args):
    """编码视频（固定 3000kbps）"""
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / f"{raw_path.stem}_encoded.mkv"

    vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
          "pad=1920:1080:(1920-iw)/2:(1080-ih)/2")

    cmd = ["ffmpeg", "-i", str(raw_path),
           "-map", "0:v:0", "-map", "0:a:0"]

    bitrate = "3000k"

    if args.gpu:
        cmd += [
            "-c:v", "hevc_nvenc",
            "-pix_fmt", "p010le",
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-bufsize", "6000k",
            "-preset", "p6",
            "-rc", "vbr_hq",
            "-spatial-aq", "1",
        ]
    else:
        cmd += [
            "-c:v", "libx265",
            "-pix_fmt", "yuv420p10le",
            "-preset", VIDEO_PRESET,
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-bufsize", "6000k",
        ]

    cmd += ["-vf", vf, "-c:a", "copy",
            "-threads", str(FFMPEG_THREADS),
            "-y", str(out)]

    if run_cmd(cmd) != 0:
        raise RuntimeError("编码失败")

    return out


def mux_episode(raw_path, encoded_mkv: Path,
                ass_dir: Path, chapters_dir: Path,
                fonts_subset_dir: Path, out_dir: Path):

    basename = raw_path.stem
    ep = guess_episode_number(basename)

    subtitle_inputs = []
    sub_count = 0

    for track in SUBTITLE_TRACKS:
        suffix = track["suffix"]
        ass = ass_dir / f"{basename} {suffix}.ass"
        if ass.exists():
            subtitle_inputs.append((ass, track["language"], track["title"]))
            sub_count += 1

    final_name = build_final_filename(ep, sub_count)
    out_path = out_dir / final_name
    out_dir.mkdir(exist_ok=True)

    cmd = ["mkvmerge", "-o", str(out_path),
           "--language", "1:ja",
           "--track-name", "1:jpn",
           str(encoded_mkv)]

    for ass_path, lang, title in subtitle_inputs:
        cmd += [
            "--language", f"0:{lang}",
            "--track-name", f"0:{title}",
            str(ass_path)
        ]

    chapter_xml = chapters_dir / f"{basename}.xml"
    if chapter_xml.exists():
        cmd += ["--chapters", str(chapter_xml)]

    # 附加子集字体
    for font in sorted(fonts_subset_dir.glob("*subset*")):
        cmd += [
            "--attachment-mime-type", "application/x-truetype-font",
            "--attach-file", str(font)
        ]

    run_cmd(cmd)


def process_one_episode(raw_path_str: str, args):
    raw = Path(raw_path_str)
    print(f"\n======= 处理：{raw.name} =======")

    ep = guess_episode_number(raw.stem)

    # 每集独立字体目录
    episode_font_dir = get_episode_font_dir(ep)
    # 清理本集字体目录，避免重复文件
    for old in episode_font_dir.glob("*"):
        old.unlink()


    if not args.no_font_subset:
        used_fonts = extract_used_fonts_from_ass(ASS_DIR)
        text_file = episode_font_dir / "chars.txt"
        collect_chars_from_ass(ASS_DIR, text_file)
        subset_fonts(text_file, FONTS_DIR, episode_font_dir, used_fonts)

    encoded = encode_episode(raw, WORK_DIR, args)

    # mux 使用当前集数的字体目录
    mux_episode(raw, encoded, ASS_DIR, CHAPTER_DIR, episode_font_dir, OUT_DIR)


    print(f"[DONE] 完成：{raw.name}")


# ============================================================
#                          MAIN 流程
# ============================================================

def main():
    global DRY_RUN

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-font-subset", action="store_true")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gpu", action="store_true")

    args = parser.parse_args()
    DRY_RUN = args.dry_run

    FONTS_DIR.mkdir(exist_ok=True)
    FONTS_SUBSET_DIR.mkdir(exist_ok=True)

    # 拆分 TTC
    for ttc in sorted(FONTS_DIR.glob("*.ttc")):
        split_ttc_to_ttfs(ttc, FONTS_DIR)

    # 字体列表重新扫描
    print("\n=== 扫描字体目录 ===")
    all_fonts = [f for f in FONTS_DIR.glob("*.ttf")] + \
                [f for f in FONTS_DIR.glob("*.otf")]

    print(f"[INFO] 共发现 {len(all_fonts)} 字体")


    # ---------------- 扫描视频 ----------------
    raws = sorted(RAW_DIR.glob(RAW_PATTERN))
    if not raws:
        print("[ERROR] raw/ 中没有找到视频")
        sys.exit(1)

    print(f"\n共有 {len(raws)} 个视频，使用 {args.max_workers} 线程")

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.max_workers) as exe:
        futures = {exe.submit(process_one_episode, str(r), args): r for r in raws}

        for fut in concurrent.futures.as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                print("[ERROR] 出错：", e)

    print("\n====== 全部任务完成 ======")


if __name__ == "__main__":
    main()

