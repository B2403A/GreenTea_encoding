#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GreenTea Requirement Installer
自动安装 Python 依赖 + 检查外部工具环境
"""

import os
import subprocess
import sys
from pathlib import Path

REQUIRED_PY_LIBS = [
    "fonttools>=4.47.0",
    "lxml>=4.9.2"
]

REQUIRED_TOOLS = {
    "ffmpeg": "视频压制 用于 hardsub / softsub",
    "mkvmerge": "MKVToolNix 视频封装、章节写入、附件封装",
    "pyftsubset": "字体子集化工具（fonttools 自带）"
}

PROJECT_DIRS = [
    "raw", "ass", "fonts",
    "fonts_sub", "chapters",
    "input", "out", "backup", "work"
]


# --------- Utility functions ---------

def run(cmd):
    print("[CMD]", " ".join(cmd))
    return subprocess.run(cmd, shell=False)


def pip_install(package: str):
    print(f"\n 正在安装 Python 依赖: {package}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def check_tool(tool: str) -> bool:
    try:
        subprocess.run([tool, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception:
        return False


# --------- Main Logic ---------

def main():
    print("========================================")
    print("  GreenTea 自动环境安装脚本")
    print("========================================")

    # 1. 生成 requirements.txt
    print("\n 正在生成 requirements.txt ...")
    req_path = Path("requirements.txt")
    with req_path.open("w", encoding="utf-8") as f:
        for lib in REQUIRED_PY_LIBS:
            f.write(lib + "\n")
    print("✔ requirements.txt 已生成\n")

    # 2. 自动创建目录
    print(" 正在创建项目目录结构 ...")
    for d in PROJECT_DIRS:
        Path(d).mkdir(exist_ok=True)
        print(f" - {d}/")
    print("✔ 所有目录已准备好。\n")

    # 3. 安装 Python 库
    print(" 正在安装 Python 依赖库 ...")
    for lib in REQUIRED_PY_LIBS:
        pip_install(lib)

    print("\n Python 库安装完成。\n")

    # 4. 检查外部工具
    print(" 正在检查外部工具环境 ...\n")
    missing = []
    for tool, desc in REQUIRED_TOOLS.items():
        ok = check_tool(tool)
        if ok:
            print(f"   {tool} 已安装 ({desc})")
        else:
            print(f"   {tool} 未找到！ ({desc})")
            missing.append(tool)

    if missing:
        print("\n⚠ 以下外部工具缺失，请用户手动安装：\n")
        for t in missing:
            print(f" - {t}")
        print("\n安装指南：")
        print("  ffmpeg: https://ffmpeg.org/download.html")
        print("  mkvmerge(MKVToolNix): https://mkvtoolnix.download/")
        print("  pyftsubset 随 fonttools 自动安装，无需额外安装\n")

    print("\n========================================")
    print("   GreenTea 环境安装完成！")
    print("========================================\n")


if __name__ == "__main__":
    main()
