#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GreenTea 环境一键安装脚本
--------------------------------
功能：
1. 自动创建所有需要的目录
2. 自动检查 ffmpeg / mkvmerge 是否安装
3. 自动安装 Python requirements.txt
4. Windows / Mac / Linux 全平台兼容
"""

import os
import subprocess
from pathlib import Path
import sys
import shutil

# 所需目录
DIRS = [
    "ass",
    "backup",
    "chapters",
    "fonts",
    "fonts_sub",
    "input",
    "out",
    "raw",
    "work"
]

REQUIREMENTS_FILE = "requirements.txt"


def print_header():
    print("=" * 60)
    print("       GreenTea 自动压制脚本环境安装器")
    print("=" * 60)


def run(cmd):
    """执行命令并实时输出"""
    print("[CMD]", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"[ERROR] 执行命令失败: {e}")
        sys.exit(1)


def check_program_exists(name):
    """检查命令是否存在于系统环境变量路径中"""
    return shutil.which(name) is not None


def create_directories():
    print("\n→ 创建目录...")
    for d in DIRS:
        Path(d).mkdir(exist_ok=True)
        print(f"[OK] {d}/")
    print("[DONE] 所有目录已准备完成\n")


def install_python_requirements():
    if not Path(REQUIREMENTS_FILE).exists():
        print(f"[WARN] 未找到 {REQUIREMENTS_FILE}，跳过 Python 依赖安装")
        return

    print("→ 安装 Python 依赖...")
    cmd = [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE]
    run(cmd)
    print("[DONE] Python 依赖安装完成\n")


def check_ffmpeg_mkvmerge():
    print("→ 检查系统依赖（ffmpeg / mkvmerge）...")

    missing = []

    if check_program_exists("ffmpeg"):
        print("[OK] ffmpeg 已安装")
    else:
        print("[ERROR] 未找到 ffmpeg")
        missing.append("ffmpeg")

    if check_program_exists("mkvmerge"):
        print("[OK] mkvmerge 已安装")
    else:
        print("[ERROR] 未找到 mkvmerge")
        missing.append("mkvmerge")

    if missing:
        print("\n❗ 以下必要组件未安装：")
        for m in missing:
            print("   -", m)

        print("\n请按系统安装方法：")

        print("\nWindows：")
        print("  ffmpeg   下载：https://www.gyan.dev/ffmpeg/builds/")
        print("  mkvmerge 下载：https://mkvtoolnix.download/")

        print("\nmacOS (Homebrew)：")
        print("  brew install ffmpeg mkvtoolnix")

        print("\nUbuntu / Debian：")
        print("  sudo apt install ffmpeg mkvtoolnix")

        print("\n安装完成后再重新运行 install_environment.py")
        sys.exit(1)

    print("[DONE] 系统依赖检查完成\n")


def main():
    print_header()

    create_directories()
    check_ffmpeg_mkvmerge()
    install_python_requirements()

    print("=" * 60)
    print(" 🎉 环境安装已全部完成！")
    print(" 请将 raw/ 放入视频，ass/ 放字幕，fonts/ 放字体即可开始压制")
    print(" 稍后运行 launch.py 开始全自动压制")
    print("=" * 60)


if __name__ == "__main__":
    main()
