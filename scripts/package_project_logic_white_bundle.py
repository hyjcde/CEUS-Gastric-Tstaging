#!/usr/bin/env python3
"""Package white project-logic HTML + all referenced images into one portable folder.

  python scripts/package_project_logic_white_bundle.py
  python scripts/package_project_logic_white_bundle.py --copy   # full copy (~350MB)
  python scripts/package_project_logic_white_bundle.py --zip    # also write .zip beside folder
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAINLINE = PROJECT_ROOT / "docs" / "mainline"
SOURCE_HTML = MAINLINE / "gastric_tstaging_project_logic_white.html"
BUNDLE_DIR = MAINLINE / "project_logic_white"
INDEX_HTML = BUNDLE_DIR / "index.html"

IMG_RE = re.compile(r'src="([^"]+\.(?:png|jpg|jpeg|gif|webp))"', re.I)


def image_srcs(html: str) -> list[str]:
    return sorted(set(IMG_RE.findall(html)))


def link_or_copy(src: Path, dest: Path, *, use_copy: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    if use_copy:
        shutil.copy2(src, dest)
        return
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def build_bundle(*, use_copy: bool, make_zip: bool) -> None:
    if not SOURCE_HTML.is_file():
        raise SystemExit(f"missing {SOURCE_HTML}")

    html = SOURCE_HTML.read_text(encoding="utf-8")
    # Footer links: parent mainline docs when bundled
    html = html.replace(
        'href="gastric_tstaging_project_logic.html"',
        'href="../gastric_tstaging_project_logic.html"',
    ).replace(
        'href="gastric_tstaging_project_framework_zh.md"',
        'href="../gastric_tstaging_project_framework_zh.md"',
    )

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_HTML.write_text(html, encoding="utf-8")

    srcs = image_srcs(html)
    missing: list[str] = []
    for rel in srcs:
        src = MAINLINE / rel
        dest = BUNDLE_DIR / rel
        if not src.is_file():
            missing.append(rel)
            continue
        link_or_copy(src, dest, use_copy=use_copy)

    readme = BUNDLE_DIR / "README.txt"
    mode = "copy" if use_copy else "hardlink"
    readme.write_text(
        f"""GastricTstaging 项目逻辑总览（白底离线包）
========================================

打开 index.html 即可浏览（建议 Chrome / Edge）。

- HTML: index.html
- 图片: figures/ 与本目录下 PNG（与 HTML 相对路径一致）
- 点击图片可放大；Esc 或点背景关闭

打包: python scripts/package_project_logic_white_bundle.py
模式: {mode} · 图片 {len(srcs)} 张 · 缺失 {len(missing)} 张
""",
        encoding="utf-8",
    )

    print(f"Bundle: {BUNDLE_DIR}")
    print(f"  index.html")
    print(f"  images: {len(srcs) - len(missing)} ok, {len(missing)} missing")
    if missing:
        for m in missing[:10]:
            print(f"    MISSING {m}")

    if make_zip:
        zip_path = BUNDLE_DIR.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in BUNDLE_DIR.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(BUNDLE_DIR.parent))
        print(f"  zip: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of hardlinks (portable USB / zip)",
    )
    parser.add_argument("--zip", action="store_true", help="Also create project_logic_white.zip")
    args = parser.parse_args()
    build_bundle(use_copy=args.copy, make_zip=args.zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
