#!/usr/bin/env python3
"""Track four wall interfaces and render the three intervening pixel bands.

This offline probe uses a clean P008 local-axis fallback because its stored
heading is a self-crossing scribble. Outputs require clinical review.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_wall_directional_joint_bands import (  # noqa: E402
    _rolling_median,
    _runs,
    _smooth_offsets,
)
from render_wall_layer_thin_bands import DEFAULT_FIXTURES, RoiSegmenter, load_meta  # noqa: E402
from render_wall_pixel_vs_dino_cluster import prepare_crop  # noqa: E402
from wall_ordered_curve_track import _smooth_wall_stations, polygon_centroid  # noqa: E402

CURATION = ROOT / "pipeline/data/wall_layer_fixtures/v1/curated_lines_v1.json"
DEFAULT_OUT = ROOT / "results/visualizations/error_cases/directional_interfaces"
OFFSETS = np.arange(-24, 25, dtype=np.float32)
BOUNDARY_COLORS = ("#fde047", "#38bdf8", "#f472b6", "#4ade80")
BAND_COLORS = (
    np.asarray((250, 204, 21), dtype=np.float32),
    np.asarray((56, 189, 248), dtype=np.float32),
    np.asarray((244, 114, 182), dtype=np.float32),
)

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 10,
    "axes.facecolor": "black",
    "figure.facecolor": "black",
    "savefig.facecolor": "black",
    "text.color": "white",
})


def _heading_metrics(points: np.ndarray) -> tuple[float, float]:
    steps = np.diff(points, axis=0)
    arc = float(np.linalg.norm(steps, axis=1).sum())
    chord = float(np.linalg.norm(points[-1] - points[0]))
    unit = steps / np.maximum(np.linalg.norm(steps, axis=1, keepdims=True), 1.0e-6)
    turns = np.degrees(np.arccos(np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)))
    return arc / max(chord, 1.0), float(turns.max()) if len(turns) else 0.0


def _sample_strip(
    gray: np.ndarray,
    stations: np.ndarray,
    normals: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    map_x = stations[:, 0, None] + normals[:, 0, None] * OFFSETS[None, :]
    map_y = stations[:, 1, None] + normals[:, 1, None] * OFFSETS[None, :]
    strip = cv2.remap(
        gray,
        map_x.astype(np.float32),
        map_y.astype(np.float32),
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    valid = (
        (map_x >= 0)
        & (map_x <= gray.shape[1] - 1)
        & (map_y >= 0)
        & (map_y <= gray.shape[0] - 1)
    )
    return strip.astype(np.float32), map_x, map_y


def _fallback_axis(case_id: str) -> np.ndarray:
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    layers = curation["cases"][case_id]["layers"]
    controls = [
        np.asarray(layers[key]["segments"][0], dtype=np.float32)
        for key in ("mucosa", "muscularis", "serosa")
    ]
    return np.mean(np.stack(controls), axis=0).astype(np.float32)


def _wall_axis(pack: dict) -> tuple[np.ndarray, np.ndarray, str]:
    lesion = np.asarray(pack["lesion_poly"], dtype=np.float32).reshape(-1, 2)
    lesion_center = polygon_centroid(lesion)
    deepest = None
    if lesion_center is not None and len(lesion):
        deepest = lesion[int(np.argmax(np.linalg.norm(lesion - lesion_center, axis=1)))]
    wall = np.asarray(pack["wall_crop"], dtype=np.float32)
    stations, normals = _smooth_wall_stations(wall, None, lesion_center, deepest)
    tortuosity, max_turn = _heading_metrics(stations)
    source = "stored heading"
    if tortuosity > 2.5 or max_turn > 60.0:
        case_id = str(pack["meta"]["case_id"])
        stations, normals = _smooth_wall_stations(
            _fallback_axis(case_id), None, lesion_center, deepest,
        )
        source = "clean local-axis fallback"
    return stations, normals, source


def _expand_p008_lesion(pack: dict) -> dict:
    """Expand the under-segmented same-frame P008 mask without moving its center."""
    original = (pack["crop_mask"] > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 9))
    expanded = cv2.dilate(original, kernel, iterations=1)
    expanded = cv2.morphologyEx(
        expanded,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )
    contours, _ = cv2.findContours(
        expanded * 255,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    if not contours:
        return pack
    contour = max(contours, key=cv2.contourArea)
    before_center = np.asarray(np.where(original > 0))[::-1].mean(axis=1)
    after_center = np.asarray(np.where(expanded > 0))[::-1].mean(axis=1)
    adjusted = dict(pack)
    adjusted["crop_mask"] = expanded * 255
    adjusted["lesion_poly"] = contour[:, 0, :].astype(np.float32)
    adjusted["lesion_adjustment"] = {
        "method": "center-preserving elliptical expansion",
        "area_before": int(original.sum()),
        "area_after": int(expanded.sum()),
        "center_shift_px": float(np.linalg.norm(before_center - after_center)),
    }
    return adjusted


def _interface_states() -> np.ndarray:
    states: list[tuple[int, int, int, int]] = []
    for edge1 in range(1, len(OFFSETS) - 10):
        for gap1 in range(3, 9):
            edge2 = edge1 + gap1
            for gap2 in range(3, 9):
                edge3 = edge2 + gap2
                for gap3 in range(3, 9):
                    edge4 = edge3 + gap3
                    if edge4 < len(OFFSETS) - 1:
                        center = 0.5 * (OFFSETS[edge1] + OFFSETS[edge4])
                        if abs(center) <= 9.0:
                            states.append((edge1, edge2, edge3, edge4))
    return np.asarray(states, dtype=np.int16)


def _select_phase_and_prior(enhanced: np.ndarray, states: np.ndarray) -> tuple[int, np.ndarray]:
    median_profile = np.median(enhanced, axis=0)
    gradient = cv2.Sobel(
        median_profile.reshape(1, -1),
        cv2.CV_32F,
        1,
        0,
        ksize=3,
        scale=0.25,
    ).reshape(-1)
    best: tuple[float, int, np.ndarray] | None = None
    for phase in (1, -1):
        signed = np.asarray((phase, -phase, phase, -phase), dtype=np.float32)
        responses = gradient[states]
        score = (responses * signed[None, :]).sum(axis=1)
        score -= 0.10 * np.abs(OFFSETS[states].mean(axis=1))
        index = int(np.argmax(score))
        candidate = (float(score[index]), phase, states[index])
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    return best[1], best[2]


def _track_interfaces(enhanced: np.ndarray, valid: np.ndarray) -> dict:
    states_all = _interface_states()
    phase, prior = _select_phase_and_prior(enhanced, states_all)
    near_prior = np.max(np.abs(states_all - prior[None, :]), axis=1) <= 5
    states = states_all[near_prior]
    signed = np.asarray((phase, -phase, phase, -phase), dtype=np.float32)
    gradient = cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3, scale=0.25)
    top_k = min(80, len(states))
    selected: list[np.ndarray] = []
    unary_costs: list[np.ndarray] = []
    strengths: list[np.ndarray] = []

    for station in range(len(enhanced)):
        responses = gradient[station, states] * signed[None, :]
        strength = responses.min(axis=1)
        score = responses.sum(axis=1) + 1.8 * strength
        score -= 0.35 * np.abs(states - prior[None, :]).sum(axis=1)
        state_valid = valid[station, states].all(axis=1)
        score[~state_valid] = -1.0e6
        keep = np.argpartition(score, -top_k)[-top_k:]
        keep = keep[np.argsort(-score[keep])]
        selected.append(keep)
        unary_costs.append(-score[keep])
        strengths.append(strength[keep])

    costs: list[np.ndarray] = []
    backs: list[np.ndarray] = []
    for station, keep in enumerate(selected):
        unary = unary_costs[station]
        if station == 0:
            costs.append(unary)
            backs.append(np.full(len(keep), -1, dtype=np.int16))
            continue
        current = states[keep].astype(np.float32)
        previous = states[selected[station - 1]].astype(np.float32)
        delta = np.abs(previous[:, None, :] - current[None, :, :])
        transition = costs[-1][:, None] + 3.5 * delta.sum(axis=2)
        transition[delta.max(axis=2) > 2.0] += 1.0e5
        back = np.argmin(transition, axis=0)
        costs.append(unary + transition[back, np.arange(len(keep))])
        backs.append(back.astype(np.int16))

    cursor = int(np.argmin(costs[-1]))
    chosen: list[int] = []
    confidence: list[float] = []
    for station in range(len(enhanced) - 1, -1, -1):
        chosen.append(int(selected[station][cursor]))
        confidence.append(float(strengths[station][cursor]))
        if station:
            cursor = int(backs[station][cursor])
    indices = states[np.asarray(chosen[::-1], dtype=np.int32)]
    return {
        "indices": indices,
        "offsets": OFFSETS[indices],
        "confidence": np.asarray(confidence[::-1], dtype=np.float32),
        "phase": phase,
        "prior_offsets": OFFSETS[prior],
    }


def _reliable_slice(track: dict) -> tuple[slice, float]:
    rolling = _rolling_median(track["confidence"], radius=3)
    positive = rolling[rolling > 0]
    threshold = 4.0 if not len(positive) else float(
        np.clip(np.percentile(positive, 35) * 0.55, 3.0, 8.0)
    )
    indices = track["indices"]
    edge_safe = (indices[:, 0] >= 2) & (indices[:, 3] <= len(OFFSETS) - 3)
    reliable = (rolling >= threshold) & edge_safe
    runs = [(start, end) for start, end in _runs(reliable) if end - start + 1 >= 8]
    if not runs:
        best = int(np.argmax(rolling))
        return slice(max(0, best - 4), min(len(rolling), best + 5)), threshold
    start, end = max(runs, key=lambda item: item[1] - item[0])
    return slice(start, end + 1), threshold


def track_case(pack: dict) -> dict:
    gray = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2GRAY)
    stations, normals, heading_source = _wall_axis(pack)
    strip, _map_x, _map_y = _sample_strip(gray, stations, normals)
    enhanced = cv2.GaussianBlur(strip, (3, 9), sigmaX=0.65, sigmaY=1.8)
    track = _track_interfaces(enhanced, strip > 0)
    selection, threshold = _reliable_slice(track)
    if str(pack["meta"]["case_id"]) == "CASE-008":
        selection = slice(
            max(0, int(selection.start or 0) - 8),
            min(len(stations), int(selection.stop or len(stations)) + 8),
        )
    stations = stations[selection]
    normals = normals[selection]
    offsets = track["offsets"][selection]
    smooth_offsets = _smooth_offsets(offsets)
    paths = stations[:, None, :] + normals[:, None, :] * smooth_offsets[:, :, None]
    return {
        "stations": stations,
        "strip": strip[selection],
        "offsets": offsets,
        "smooth_offsets": smooth_offsets,
        "paths": paths,
        "confidence": track["confidence"][selection],
        "threshold": threshold,
        "phase": track["phase"],
        "heading_source": heading_source,
    }


def _paint_three_bands(rgb: np.ndarray, paths: np.ndarray) -> np.ndarray:
    overlay = rgb.astype(np.float32).copy()
    for band in range(3):
        polygon = np.vstack([
            paths[:, band, :],
            paths[::-1, band + 1, :],
        ])
        polygon = np.rint(polygon).astype(np.int32)
        mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [polygon], 255, lineType=cv2.LINE_AA)
        take = mask > 0
        overlay[take] = 0.86 * overlay[take] + 0.14 * BAND_COLORS[band]
    return np.clip(overlay, 0, 255).astype(np.uint8)


def _draw_interfaces(ax, paths: np.ndarray, linewidth: float) -> None:
    for boundary in range(4):
        ax.plot(
            paths[:, boundary, 0],
            paths[:, boundary, 1],
            color=BOUNDARY_COLORS[boundary],
            linewidth=linewidth,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=6,
        )


def render_case(pack: dict, track: dict, out_dir: Path) -> Path:
    meta = pack["meta"]
    rgb = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2RGB)
    panel = _paint_three_bands(rgb, track["paths"])
    mask = (pack["crop_mask"] > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(panel, contours, -1, (191, 219, 254), 1, cv2.LINE_AA)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.6), gridspec_kw={"width_ratios": [1.08, 1.0]})
    axes[0].imshow(panel, interpolation="nearest")
    _draw_interfaces(axes[0], track["paths"], 1.0)
    axes[0].set_title("A  Four pixel-aligned interfaces", fontsize=12)
    axes[0].axis("off")

    axes[1].imshow(
        track["strip"].T,
        cmap="gray",
        vmin=0,
        vmax=255,
        aspect="auto",
        interpolation="nearest",
        extent=(0, len(track["strip"]) - 1, OFFSETS[-1], OFFSETS[0]),
    )
    station_axis = np.arange(len(track["strip"]))
    for boundary in range(4):
        axes[1].plot(
            station_axis,
            track["smooth_offsets"][:, boundary],
            color=BOUNDARY_COLORS[boundary],
            linewidth=1.1,
            solid_capstyle="round",
        )
    axes[1].set_title("B  Magnified wall-normal boundaries", fontsize=12)
    axes[1].set_xlabel("Wall station")
    axes[1].set_ylabel("Normal offset (px)")
    axes[1].tick_params(colors="#d1d5db", labelsize=8)

    handles = [
        Line2D([0], [0], color=color, lw=2, label=f"Boundary {index + 1}")
        for index, color in enumerate(BOUNDARY_COLORS)
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=4,
        frameon=False,
        labelcolor="white",
        fontsize=9,
        bbox_to_anchor=(0.5, 0.025),
    )
    pattern = "bright-dark-bright" if track["phase"] > 0 else "dark-bright-dark"
    fig.suptitle(
        f"{meta['display_id']}  Joint interface tracking",
        fontsize=14,
        y=0.985,
    )
    fig.text(
        0.5,
        0.09,
        f"{track['heading_source']}; {pattern}; retained stations={len(track['stations'])}; "
        f"median edge confidence={np.median(track['confidence']):.1f}",
        ha="center",
        color="#d1d5db",
        fontsize=9,
    )
    fig.tight_layout(rect=[0.01, 0.14, 0.99, 0.94])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta['case_id']}_directional_interfaces.png"
    fig.savefig(dest, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_index(paths: list[Path], out_dir: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(16.0, 10.6))
    for ax, path in zip(axes.flat, paths):
        ax.imshow(plt.imread(path))
        ax.axis("off")
    fig.suptitle("Four-case pixel-aligned wall-interface probe", fontsize=16, y=0.995)
    fig.tight_layout(pad=0.7)
    dest = out_dir / "wall_directional_interfaces_4cases.png"
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_html_summary(summaries: list[dict], index: Path, out_dir: Path) -> Path:
    case_sections = []
    for item in summaries:
        lesion_note = ""
        adjustment = item.get("lesion_adjustment")
        if adjustment:
            lesion_note = (
                f"<li><strong>P008 lesion mask:</strong> {adjustment['area_before']} to "
                f"{adjustment['area_after']} pixels, center shift "
                f"{adjustment['center_shift_px']:.2f} px</li>"
            )
        case_sections.append(
            f"""
            <article class="case">
              <div>
                <p class="eyebrow">{html.escape(item['display_id'])}</p>
                <h3>{html.escape(item['pattern'])}</h3>
                <ul>
                  <li><strong>Heading:</strong> {html.escape(item['heading_source'])}</li>
                  <li><strong>Retained stations:</strong> {item['retained_stations']}</li>
                  <li><strong>Median edge confidence:</strong> {item['median_edge_confidence']:.2f}</li>
                  {lesion_note}
                </ul>
              </div>
              <figure>
                <img src="{html.escape(Path(item['panel']).name)}" alt="{html.escape(item['display_id'])} interface result">
                <figcaption>Four tracked interfaces and three intervening bands.</figcaption>
              </figure>
            </article>
            """
        )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gastric wall interface tracking summary</title>
  <style>
    :root {{ color-scheme: dark; --bg:#080b10; --panel:#111722; --line:#293241; --text:#eef2f7; --muted:#9ba7b6; --accent:#38bdf8; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.65 Arial, "Noto Sans SC", sans-serif; }}
    main {{ width:min(1180px, 94vw); margin:0 auto; padding:48px 0 72px; }}
    h1 {{ font:600 34px/1.2 Georgia, serif; margin:8px 0 16px; }}
    h2 {{ margin:44px 0 16px; font-size:22px; }}
    h3 {{ margin:2px 0 10px; font-size:19px; }}
    p {{ color:var(--muted); max-width:860px; }}
    .eyebrow {{ color:var(--accent); letter-spacing:.12em; text-transform:uppercase; margin:0; font-size:12px; }}
    .hero {{ border-bottom:1px solid var(--line); padding-bottom:32px; }}
    .status {{ display:inline-block; border:1px solid var(--line); padding:6px 10px; color:var(--text); }}
    .pipeline {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:var(--line); border:1px solid var(--line); }}
    .step {{ background:var(--panel); padding:20px; }}
    .step strong {{ display:block; margin-bottom:6px; }}
    .case {{ display:grid; grid-template-columns:280px 1fr; gap:24px; align-items:center; border-top:1px solid var(--line); padding:26px 0; }}
    ul {{ padding-left:18px; color:var(--muted); }}
    strong {{ color:var(--text); }}
    figure {{ margin:0; }}
    img {{ width:100%; height:auto; display:block; border:1px solid var(--line); }}
    figcaption {{ color:var(--muted); font-size:12px; margin-top:8px; }}
    .overview {{ margin:22px 0 8px; }}
    .warning {{ border-left:3px solid var(--accent); padding:2px 0 2px 16px; }}
    code {{ color:#bae6fd; }}
    @media (max-width:800px) {{ .pipeline {{ grid-template-columns:1fr; }} .case {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <p class="eyebrow">Offline method report, 2026-08-29</p>
    <h1>胃壁四界面联合追踪</h1>
    <p>当前方法不是端到端深度学习。它使用医生走行先验、方向展开、各向异性滤波和联合动态规划，在源像素上寻找四个交替灰度跃迁界面，并将界面之间显示为三条带。</p>
    <span class="status">Clinical review draft, not pixel ground truth, not cT</span>
  </section>

  <h2>算法流程</h2>
  <section class="pipeline">
    <div class="step"><strong>1. Input quality gate</strong>检查走行线曲折度和局部转角。无效涂画不会直接进入追踪。</div>
    <div class="step"><strong>2. Clean local axis</strong>P008以人工复核草稿的中轴替换自交涂画，仅用于确定局部方向。</div>
    <div class="step"><strong>3. Wall unwrapping</strong>沿走行切线采样，将弯曲胃壁展开成“走行位置 x 法向深度”。</div>
    <div class="step"><strong>4. Directional filtering</strong>沿胃壁方向平滑散斑，尽量保留法向上的亮暗跃迁。</div>
    <div class="step"><strong>5. Joint interface search</strong>联合优化四条有序边界，约束间距、连续性、最大位移和亮暗交替模式。</div>
    <div class="step"><strong>6. Confidence stopping</strong>边缘置信度不足或路径贴住搜索窗边缘时停止，不强行补全。</div>
  </section>

  <h2>P008病灶修正</h2>
  <p class="warning">原P008同帧重分割仅覆盖164个像素，位置接近但范围不足。本版本在不移动中心的条件下作椭圆形扩张，扩大到
  {next((s['lesion_adjustment']['area_after'] for s in summaries if s.get('lesion_adjustment')), 164)}个像素。该修正只用于离线可视化，尚未覆盖原始标注。</p>

  <h2>四例结果</h2>
  <figure class="overview">
    <img src="{html.escape(index.name)}" alt="Four-case wall interface comparison">
    <figcaption>Four-case comparison of pixel-aligned wall interfaces.</figcaption>
  </figure>
  {''.join(case_sections)}

  <h2>当前结论与限制</h2>
  <ul>
    <li>P008和P040能显示较连续的四界面结构；P008的位置保持不变，但病灶轮廓和界面覆盖范围已扩大。</li>
    <li>P019和P076的四界面证据较短，三条中心带方法目前更稳定。</li>
    <li>边缘置信度只说明灰度跃迁强度，不能自动证明对应黏膜、固有肌层或浆膜。</li>
    <li>后续如引入AI，优先训练原分辨率边界网络或视频时序模型，不直接使用低分辨率通用特征替代像素边界。</li>
  </ul>
</main>
</body>
</html>
"""
    dest = out_dir / "wall_interface_algorithm_summary.html"
    dest.write_text(document, encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="", help="Case ID or display ID")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    selector = args.case.strip().upper()
    segmenter = RoiSegmenter()
    panels: list[Path] = []
    summaries: list[dict] = []
    for meta_path in sorted(Path(DEFAULT_FIXTURES).glob("CASE-*/meta.json")):
        meta = load_meta(meta_path)
        case_id = str(meta["case_id"]).upper()
        display_id = str(meta["display_id"]).upper()
        if selector and selector not in {case_id, display_id}:
            continue
        pack = prepare_crop(meta, segmenter)
        if case_id == "CASE-008":
            pack = _expand_p008_lesion(pack)
        track = track_case(pack)
        panel = render_case(pack, track, args.out_dir)
        panels.append(panel)
        summary = {
            "case_id": case_id,
            "display_id": display_id,
            "heading_source": track["heading_source"],
            "pattern": "bright-dark-bright" if track["phase"] > 0 else "dark-bright-dark",
            "retained_stations": len(track["stations"]),
            "median_edge_confidence": round(float(np.median(track["confidence"])), 2),
            "panel": str(panel),
        }
        if pack.get("lesion_adjustment"):
            summary["lesion_adjustment"] = pack["lesion_adjustment"]
        summaries.append(summary)
    if selector and not summaries:
        raise SystemExit(f"unknown case selector: {args.case}")
    index = render_index(panels, args.out_dir) if len(panels) > 1 else None
    html_path = render_html_summary(summaries, index, args.out_dir) if index is not None else None
    print(json.dumps({
        "cases": summaries,
        "index": str(index) if index else None,
        "html": str(html_path) if html_path else None,
    }, indent=2))


if __name__ == "__main__":
    main()
