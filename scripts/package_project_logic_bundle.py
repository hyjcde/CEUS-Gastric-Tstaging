#!/usr/bin/env python3
"""Package project logic HTML + Poe figures into a self-contained folder.

Output: docs/mainline/project_logic_bundle/
  index.html                      (copy of white theme, entry point)
  gastric_tstaging_project_logic_white.html
  gastric_tstaging_project_logic.html
  gastric_us_agent_methodology_architecture_poe.png
  figures/*.png
  README.md
  manifest.json

  python scripts/package_project_logic_bundle.py
  python scripts/package_project_logic_bundle.py --zip
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAINLINE = PROJECT_ROOT / "docs" / "mainline"
SOURCE_FIGURES = MAINLINE / "figures"
BUNDLE = MAINLINE / "project_logic_bundle"

HTML_FILES = [
    "gastric_tstaging_project_logic_white.html",
    "gastric_tstaging_project_logic.html",
]
METHODOLOGY_PNG = "gastric_us_agent_methodology_architecture_poe.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package logic HTML + figures.")
    parser.add_argument(
        "--out",
        type=Path,
        default=BUNDLE,
        help=f"Output directory (default: {BUNDLE})",
    )
    parser.add_argument("--zip", action="store_true", help="Also write a .zip next to the folder.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir: Path = args.out
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    fig_dir = out_dir / "figures"
    fig_dir.mkdir()

    copied_png: list[str] = []
    if SOURCE_FIGURES.is_dir():
        for png in sorted(SOURCE_FIGURES.glob("fig_*.png")):
            shutil.copy2(png, fig_dir / png.name)
            copied_png.append(png.name)
        local_dir = SOURCE_FIGURES / "local"
        if local_dir.is_dir():
            local_out = fig_dir / "local"
            local_out.mkdir(exist_ok=True)
            for png in sorted(local_dir.glob("local_*.png")):
                shutil.copy2(png, local_out / png.name)
                copied_png.append(f"local/{png.name}")

    meth_src = MAINLINE / METHODOLOGY_PNG
    if meth_src.is_file():
        shutil.copy2(meth_src, out_dir / METHODOLOGY_PNG)
        copied_png.append(METHODOLOGY_PNG)

    for name in HTML_FILES:
        src = MAINLINE / name
        if src.is_file():
            shutil.copy2(src, out_dir / name)

    white = out_dir / "gastric_tstaging_project_logic_white.html"
    if white.is_file():
        shutil.copy2(white, out_dir / "index.html")

    readme = f"""# GastricTstaging 项目逻辑总览（离线包）

生成时间（UTC）：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}

## 打开方式

- 推荐：用浏览器打开 **`index.html`**（白底版）
- 深色版：`gastric_tstaging_project_logic.html`

## 目录

| 路径 | 说明 |
|------|------|
| `figures/` | Poe GPT-Image-2 生成的方法学/结果示意图 |
| `gastric_us_agent_methodology_architecture_poe.png` | §7.1 方法学总图 |
| `manifest.json` | 文件清单 |

## 重新生成图片

在仓库根目录配置 `.env`（见 `.env.example` 的 `POE_API_KEY`），然后：

```bash
python scripts/generate_agent_figures_poe_batch.py --skip-existing
python scripts/package_project_logic_bundle.py --zip
```

需要联网加载 Mermaid CDN（`index.html` 内脚本）。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "html": HTML_FILES + ["index.html"],
        "figures": sorted(copied_png),
        "figure_count": len([p for p in copied_png if p.startswith("fig_")]),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Bundle: {out_dir} ({len(copied_png)} PNG, {len(HTML_FILES)+1} HTML)")

    if args.zip:
        zip_base = out_dir.parent / out_dir.name
        archive = shutil.make_archive(str(zip_base), "zip", root_dir=out_dir.parent, base_dir=out_dir.name)
        print(f"Zip: {archive}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
