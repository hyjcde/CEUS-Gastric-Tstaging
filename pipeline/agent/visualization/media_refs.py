"""Relative file references for HTML reports (no base64 embeds)."""

from __future__ import annotations

import html
import os
import shutil
from pathlib import Path
from typing import Optional, Union

MediaPath = Union[Path, str]


def report_assets_dir(html_path: Path) -> Path:
    return html_path.parent / f"{html_path.stem}_assets"


def ensure_assets_dir(html_path: Path) -> Path:
    assets = report_assets_dir(html_path)
    assets.mkdir(parents=True, exist_ok=True)
    return assets


def rel_href(html_path: Path, asset_path: Path) -> str:
    """POSIX relative URL from HTML file to asset."""
    return os.path.relpath(asset_path.resolve(), html_path.parent.resolve()).replace("\\", "/")


def save_png_bytes(data: bytes, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def stage_file(
    src: Path,
    dest: Path,
    *,
    copy: bool = False,
) -> Path:
    """Hardlink or copy ``src`` to ``dest`` if missing or stale."""
    src = src.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return dest
    if dest.exists():
        dest.unlink()
    if copy:
        shutil.copy2(src, dest)
    else:
        try:
            os.link(src, dest)
        except OSError:
            shutil.copy2(src, dest)
    return dest


def img_tag(
    html_path: Path,
    asset_path: Path,
    *,
    css_class: str = "fig",
    alt: Optional[str] = None,
) -> str:
    if not asset_path.is_file():
        return ""
    href = rel_href(html_path, asset_path)
    name = alt or asset_path.name
    return (
        f'<img class="{css_class}" src="{html.escape(href)}" '
        f'alt="{html.escape(name)}" />'
    )


def video_tag(html_path: Path, asset_path: Path, *, css_class: str = "") -> str:
    if not asset_path.is_file():
        return (
            f'<p class="meta">视频不存在：<code>{html.escape(str(asset_path))}</code></p>'
        )
    href = rel_href(html_path, asset_path)
    size_mb = asset_path.stat().st_size / 1e6
    style = "width:100%;max-width:960px;border:1px solid var(--line);border-radius:4px"
    cls = f' class="{css_class}"' if css_class else ""
    return (
        f'<p class="meta">{html.escape(asset_path.name)} · {size_mb:.1f} MB</p>'
        f'<video controls preload="metadata"{cls} style="{style}">'
        f'<source src="{html.escape(href)}" type="video/mp4" />'
        f"浏览器不支持 video 标签</video>"
    )
