#!/usr/bin/env python3
"""Nature-style G17 morph triad 3D plot at standard share-pack camera angles.

Axes: Peak sharpness / Solidity / Spiculation index (no clinical size).
Uses the same elev/azim as G3 (view1 + altview); axis names kept fully visible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d import proj3d
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
PACK = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
OUT = PROJECT_ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/triplets_3d"
SHARE = PROJECT_ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"

STAGE = ["T1", "T2", "T3", "T4+"]
# NMI-pastel-ish, still readable on white
COLORS = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}

FEATS = (
    "morph_peak_sharpness_max",
    "morph_solidity",
    "margin_spic_robust",
)
LABELS = ("Peak sharpness", "Solidity", "Spiculation index")
# Match share-pack G3 / G17 standard camera (view1 + altview)
STANDARD_VIEWS = (
    {"tag": "view1", "elev": 22.0, "azim": -55.0},
    {"tag": "altview", "elev": 18.0, "azim": 125.0},
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument(
        "--view",
        choices=["view1", "altview", "both"],
        default="both",
        help="Standard share-pack camera (default: both)",
    )
    return ap.parse_args()


def apply_nature_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 6,
            "axes.labelsize": 6,
            "axes.titlesize": 7,
            "xtick.labelsize": 5,
            "ytick.labelsize": 5,
            "legend.fontsize": 5,
            "axes.linewidth": 0.6,
            "lines.linewidth": 0.8,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "text.color": "#111111",
            "axes.labelcolor": "#111111",
            "xtick.color": "#111111",
            "ytick.color": "#111111",
            "axes.edgecolor": "#333333",
            "grid.color": "#E6E6E6",
            "axes.unicode_minus": False,
        }
    )


def load_data() -> pd.DataFrame:
    pt = pd.read_csv(PT, usecols=["patient_id", "label"])
    pack = pd.read_csv(PACK)
    pt["patient_id"] = pt["patient_id"].astype(str)
    pack["patient_id"] = pack["patient_id"].astype(str)
    df = pack.merge(pt, on="patient_id", how="inner", suffixes=("", "_pt"))
    if "label_pt" in df.columns:
        df["label"] = df["label"].fillna(df["label_pt"])
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    for c in FEATS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    m = df[list(FEATS)].notna().all(axis=1) & df["label"].notna()
    return df.loc[m].reset_index(drop=True)


def project_xy(ax, x, y, z) -> tuple[np.ndarray, np.ndarray]:
    xs, ys, _ = proj3d.proj_transform(x, y, z, ax.get_proj())
    return np.asarray(xs), np.asarray(ys)


def separation_score(xy: np.ndarray, labels: np.ndarray) -> float:
    """Between-stage median path length / pooled within-stage RMS (in z-scored 2D)."""
    if len(np.unique(labels)) < 2 or len(xy) < 20:
        return -np.inf
    sc = StandardScaler()
    z = sc.fit_transform(xy)
    meds = []
    within = []
    for k in range(4):
        part = z[labels == k]
        if len(part) < 3:
            return -np.inf
        meds.append(np.median(part, axis=0))
        within.append(np.mean(np.sum((part - meds[-1]) ** 2, axis=1)))
    meds = np.asarray(meds)
    path = float(np.sum(np.linalg.norm(np.diff(meds, axis=0), axis=1)))
    w = float(np.mean(within)) + 1e-9
    try:
        sil = float(silhouette_score(z, labels, sample_size=min(800, len(z)), random_state=0))
    except Exception:
        sil = 0.0
    # combine: emphasize path clarity + cluster structure
    return path / np.sqrt(w) + 1.5 * sil


def search_best_view(df: pd.DataFrame) -> dict:
    x = df[FEATS[0]].to_numpy(float)
    y = df[FEATS[1]].to_numpy(float)
    z = df[FEATS[2]].to_numpy(float)
    lab = df["label"].astype(int).to_numpy()

    elevs = list(range(8, 46, 4))
    azims = list(range(-180, 180, 8))
    best = {"score": -np.inf, "elev": 20.0, "azim": -55.0}

    fig = plt.figure(figsize=(3.5, 3.2))
    ax = fig.add_subplot(111, projection="3d")
    # set limits once for stable projection
    ax.set_xlim(0, float(np.quantile(x, 0.995)) * 1.05)
    ax.set_ylim(float(np.quantile(y, 0.005)), 1.0)
    ax.set_zlim(0, float(np.quantile(z, 0.995)) * 1.08)

    for elev in elevs:
        for azim in azims:
            ax.view_init(elev=elev, azim=azim)
            px, py = project_xy(ax, x, y, z)
            sc = separation_score(np.column_stack([px, py]), lab)
            if sc > best["score"]:
                best = {"score": float(sc), "elev": float(elev), "azim": float(azim)}
    plt.close(fig)

    # local refine ±4°
    fig = plt.figure(figsize=(3.5, 3.2))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_xlim(0, float(np.quantile(x, 0.995)) * 1.05)
    ax.set_ylim(float(np.quantile(y, 0.005)), 1.0)
    ax.set_zlim(0, float(np.quantile(z, 0.995)) * 1.08)
    for elev in range(int(best["elev"]) - 4, int(best["elev"]) + 5, 2):
        for azim in range(int(best["azim"]) - 6, int(best["azim"]) + 7, 2):
            ax.view_init(elev=elev, azim=azim)
            px, py = project_xy(ax, x, y, z)
            sc = separation_score(np.column_stack([px, py]), lab)
            if sc > best["score"]:
                best = {"score": float(sc), "elev": float(elev), "azim": float(azim)}
    plt.close(fig)
    return best


def plot_nature(df: pd.DataFrame, elev: float, azim: float, stem: Path) -> None:
    x = df[FEATS[0]].to_numpy(float)
    y = df[FEATS[1]].to_numpy(float)
    z = df[FEATS[2]].to_numpy(float)
    lab = df["label"].astype(int).to_numpy()

    # Layout: 3D plot + right legend + bottom axis key (nothing overlaps the box)
    fig = plt.figure(figsize=(5.2, 4.0), dpi=300)
    ax = fig.add_axes([0.02, 0.18, 0.72, 0.76], projection="3d")

    handles = []
    for k in range(4):
        m = lab == k
        h = ax.scatter(
            x[m],
            y[m],
            z[m],
            s=4,
            alpha=0.22,
            c=COLORS[k],
            edgecolors="none",
            depthshade=False,
            label=f"{STAGE[k]} (n={int(m.sum())})",
            zorder=1,
        )
        handles.append(h)

    med = np.array([[np.median(df.loc[lab == k, FEATS[i]]) for i in range(3)] for k in range(4)])
    ax.plot(med[:, 0], med[:, 1], med[:, 2], color="#222222", linewidth=1.0, zorder=4)
    for k in range(4):
        ax.scatter(
            [med[k, 0]],
            [med[k, 1]],
            [med[k, 2]],
            s=42,
            c=COLORS[k],
            edgecolors="white",
            linewidths=0.9,
            marker="D",
            depthshade=False,
            zorder=6,
        )

    ax.set_xlim(0.0, float(np.quantile(x, 0.995)) * 1.05)
    ax.set_ylim(max(0.45, float(np.quantile(y, 0.005))), 1.0)
    ax.set_zlim(0.0, float(np.quantile(z, 0.995)) * 1.08)

    ax.view_init(elev=elev, azim=azim)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor("#CCCCCC")
    ax.yaxis.pane.set_edgecolor("#CCCCCC")
    ax.zaxis.pane.set_edgecolor("#CCCCCC")
    ax.grid(True, linestyle="-", linewidth=0.25, alpha=0.45)
    ax.tick_params(axis="both", which="major", labelsize=5.5, pad=2, length=1.5, width=0.35)

    # No 3D axis text (mplot3d places them into the box where they get occluded).
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_zlabel("")
    ax.set_title(f"Morph triad (N={len(df)})", fontsize=7, pad=2)

    # Legend outside, right of the 3D axes
    leg_ax = fig.add_axes([0.76, 0.35, 0.22, 0.40])
    leg_ax.axis("off")
    leg_ax.legend(
        handles,
        [f"{STAGE[k]} (n={int((lab == k).sum())})" for k in range(4)],
        loc="center left",
        fontsize=6,
        frameon=False,
        markerscale=2.2,
        handletextpad=0.4,
        labelspacing=0.45,
    )

    # Dedicated bottom band: full axis names, never clipped by the 3D pane
    key_ax = fig.add_axes([0.06, 0.02, 0.88, 0.12])
    key_ax.axis("off")
    key_ax.text(
        0.0,
        0.72,
        "Axes",
        fontsize=6,
        fontweight="bold",
        color="#111111",
        transform=key_ax.transAxes,
        va="center",
    )
    key_ax.text(
        0.0,
        0.28,
        "X  Peak sharpness      Y  Solidity      Z  Spiculation index",
        fontsize=6.5,
        color="#111111",
        transform=key_ax.transAxes,
        va="center",
        family="sans-serif",
    )

    stem.parent.mkdir(parents=True, exist_ok=True)
    for ext, dpi in (("png", 600), ("pdf", None), ("svg", None)):
        kw = {"facecolor": "white", "pad_inches": 0.04}
        if dpi:
            kw["dpi"] = dpi
        # Do not use bbox_inches='tight' — it re-crops and can hide the key band
        fig.savefig(stem.with_suffix(f".{ext}"), **kw)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    apply_nature_style()
    df = load_data()

    views = STANDARD_VIEWS
    if args.view != "both":
        views = tuple(v for v in STANDARD_VIEWS if v["tag"] == args.view)

    outputs = {}
    for v in views:
        stem = args.out_dir / f"G17_morph_triad_nature_{v['tag']}"
        plot_nature(df, v["elev"], v["azim"], stem)
        share_png = f"45_triplet_G17_peak_solidity_spic_nature_{v['tag']}.png"
        share_path = SHARE / share_png
        share_path.write_bytes(stem.with_suffix(".png").read_bytes())
        (SHARE / share_png.replace(".png", ".pdf")).write_bytes(stem.with_suffix(".pdf").read_bytes())
        outputs[v["tag"]] = {
            "elev": v["elev"],
            "azim": v["azim"],
            "png": str(stem.with_suffix(".png")),
            "pdf": str(stem.with_suffix(".pdf")),
            "share_png": str(share_path),
        }
        print(f"[ok] {v['tag']} elev={v['elev']} azim={v['azim']}")

    # Primary share alias: altview (same role as G3 *_altview.png)
    primary = outputs.get("altview") or next(iter(outputs.values()))
    alias = SHARE / "45_triplet_G17_peak_solidity_spic_nature_bestview.png"
    alias.write_bytes(Path(primary["png"]).read_bytes())
    (SHARE / "45_triplet_G17_peak_solidity_spic_nature_bestview.pdf").write_bytes(
        Path(primary["pdf"]).read_bytes()
    )

    meta = {
        "n": int(len(df)),
        "features": list(FEATS),
        "labels": list(LABELS),
        "camera": "standard share-pack views (not max-separation search)",
        "outputs": outputs,
        "share_alias": str(alias),
        "definitions": {
            "morph_peak_sharpness_max": (
                "Max peak sharpness on lightly smoothed radial distance signature (NRL): "
                "substantial contour protrusions with high local curvature/narrow width; "
                "higher = sharper lobule/spicule-like peaks."
            ),
            "morph_solidity": (
                "Mask area / convex-hull area. Near 1 = compact/convex; lower = deep "
                "indentations / concave margin."
            ),
            "margin_spic_robust": (
                "Composite spiculation index (0-1): heavy-smoothed high-frequency NRL energy, "
                "(1-solidity), circular bag-of-frequencies high-band, needle-like FFT ratio, "
                "and BoF peakiness — designed to be stable under imprecise masks."
            ),
        },
    }
    (args.out_dir / "G17_nature_standardview_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta["outputs"], indent=2))


if __name__ == "__main__":
    main()
