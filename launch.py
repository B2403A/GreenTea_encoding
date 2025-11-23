#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GreenTea 一键压制脚本
--------------------------------
使用方法：

 首先，确保运行了requirement.py文件；
 之后，将源视频放在raw，字体放在fonts，字幕放在ass；
 然后，运行autochapter.py，将半自动生成章节文件，请注意一定要人工检查XML和ffmeta时间戳！
 最后，运行此脚本，终端确保在此脚本所在目录下运行，执行python3 launch.py
 按照提示输入番剧的英文名，或是在greentea_auto.py和hardsub.py里修改。

功能：
1. 自动检查并穿件创建所有需要的目录
2. 自动扫描所有字体和分集
3. 自动进行硬压和软压
"""

import os
from pathlib import Path
import subprocess

DIRS = [
    "raw", "ass", "fonts", "fonts_sub",
    "chapters", "work", "out", "backup", "input"
]

def update_show_name(pyfile: Path, show_name: str):
    """自动修改脚本中的 SHOW_NAME"""
    text = pyfile.read_text(encoding="utf-8")
    text = re.sub(
        r'SHOW_NAME\s*=\s*".+?"',
        f'SHOW_NAME = "{show_name}"',
        text
    )
    pyfile.write_text(text, encoding="utf-8")

def main():
    print("=== GreenTea 自动化启动器 ===\n")

    # 创建目录
    for d in DIRS:
        Path(d).mkdir(exist_ok=True)
    print("[OK] 所有目录已创建")

    # 输入番剧名称
    show = input("\n请输入番剧英文名称（例如：Silent Witch ...）\n> ").strip()

    # 修改脚本变量
    update_show_name(Path("greentea_auto.py"), show)
    update_show_name(Path("hardsub.py"), show)

    print("\n选择模式：\n1 = soft（greentea）\n2 = hard（hardsub）")
    mode = input("> ").strip()

    if mode == "1":
        print("\n== 开始软压（greentea_auto） ==")
        subprocess.run(["python3", "greentea_auto.py"])
    else:
        print("\n== 开始硬压（hardsub） ==")
        subprocess.run(["python3", "hardsub.py"])

    print("\n=== 完成 ===")

if __name__ == "__main__":
    import re
    main()
