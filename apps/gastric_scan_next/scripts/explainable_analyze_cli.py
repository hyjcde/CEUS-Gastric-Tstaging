#!/usr/bin/env python3
"""CLI wrapper for explainable boundary analysis (V4). Outputs JSON to stdout."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from io import BytesIO
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.explainable_features_v4 import ExplainableFeatureExtractorV4  # noqa: E402
from pipeline.agent.signs.direction_growth import compute_direction_growth_features  # noqa: E402


def _bbox_from_points(points):
    if not points or len(points) < 3:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
    }


def _parse_json_arg(value, name):
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {name} JSON") from exc
    return parsed


def _geometry_summary(mask, lumen_mask, lumen_polygon, lumen_bbox):
    if lumen_mask is None and lumen_bbox is None:
        return None
    lumen_for_distance = lumen_mask
    if lumen_for_distance is None and lumen_bbox is not None:
        lumen_for_distance = np.zeros_like(mask, dtype=np.uint8)
        x1 = max(0, min(lumen_for_distance.shape[1] - 1, int(round(lumen_bbox["x1"]))))
        y1 = max(0, min(lumen_for_distance.shape[0] - 1, int(round(lumen_bbox["y1"]))))
        x2 = max(0, min(lumen_for_distance.shape[1] - 1, int(round(lumen_bbox["x2"]))))
        y2 = max(0, min(lumen_for_distance.shape[0] - 1, int(round(lumen_bbox["y2"]))))
        if x2 > x1 and y2 > y1:
            lumen_for_distance[y1 : y2 + 1, x1 : x2 + 1] = 1
    nearest_gap = None
    if lumen_for_distance is not None and np.any(mask > 0):
        lumen_bin = (lumen_for_distance > 0).astype(np.uint8)
        distance_map = cv2.distanceTransform((1 - lumen_bin).astype(np.uint8), cv2.DIST_L2, 5)
        lesion_distances = distance_map[mask > 0]
        if lesion_distances.size:
            nearest_gap = float(np.min(lesion_distances))
    features = compute_direction_growth_features(
        mask,
        lumen_bbox=lumen_bbox,
        lumen_mask=lumen_mask,
    )
    growth = features.get("growth_proxy") or {}
    viz = features.get("viz") or {}
    return {
        "status": features.get("status"),
        "direction_source": features.get("direction_source"),
        "quality_flags": features.get("quality_flags") or [],
        "contact_arc_ratio": features.get("contact_arc_ratio"),
        "outward_expansion_ratio": growth.get(
            "outward_expansion_ratio",
            growth.get("outward_protrusion_ratio"),
        ),
        "continuous_outward_arc_frac": growth.get("continuous_outward_arc_frac"),
        "outward_concentration": growth.get("outward_concentration"),
        "outward_norm_px": features.get("outward_norm_px"),
        "lumen_distance_px": nearest_gap,
        "center_distance_px": features.get("outward_norm_px"),
        "lumen_center": viz.get("lumen_center"),
        "lesion_center": viz.get("lesion_center"),
        "outward_arrow": viz.get("outward_arrow"),
        "lumen_polygon": lumen_polygon,
    }


def build_visualization_base64(
    image,
    contour,
    lumen_contour,
    result1,
    result2,
    result3,
    results,
) -> str:
    risk_colors = ["#00C853", "#FFEB3B", "#FF9800", "#F44336"]
    risk_cmap = LinearSegmentedColormap.from_list("risk", risk_colors, N=256)
    stage = results["predicted_t_stage"]
    stage_color = "#F44336" if "T4" in stage else "#FF9800" if "T3" in stage else "#4CAF50"

    fig = plt.figure(figsize=(12, 7), facecolor="#0a0a0a")
    fig.suptitle(
        f"Boundary Integrity Analysis: {stage} ({results['confidence']})",
        fontsize=13,
        fontweight="bold",
        color=stage_color,
        y=0.98,
    )

    ax1 = fig.add_subplot(1, 2, 1)
    ax1.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    strengths = result1["boundary_strengths"]
    risks = result3["constrained_risk"]
    combined_risk = (1 - strengths) * 0.6 + risks * 0.4
    for i in range(len(contour) - 1):
        color = risk_cmap(float(combined_risk[i]))
        ax1.plot(
            [contour[i, 0], contour[i + 1, 0]],
            [contour[i, 1], contour[i + 1, 1]],
            color=color,
            linewidth=3,
            solid_capstyle="round",
        )
    geometry = results.get("geometry") or {}
    if lumen_contour is not None and len(lumen_contour) >= 2:
        ax1.plot(
            lumen_contour[:, 0],
            lumen_contour[:, 1],
            color="#e879f9",
            linewidth=2,
            linestyle=(0, (5, 4)),
        )
    if geometry.get("lumen_center") and geometry.get("lesion_center"):
        lumen_center = geometry["lumen_center"]
        lesion_center = geometry["lesion_center"]
        ax1.plot(
            [lumen_center[0], lesion_center[0]],
            [lumen_center[1], lesion_center[1]],
            color="#bef264",
            linewidth=1.5,
            linestyle=(0, (4, 3)),
        )
        ax1.scatter(
            [lumen_center[0], lesion_center[0]],
            [lumen_center[1], lesion_center[1]],
            color=["#e879f9", "#22d3ee"],
            s=18,
            zorder=4,
        )
    if geometry.get("outward_arrow") and len(geometry["outward_arrow"]) >= 4:
        arrow = geometry["outward_arrow"]
        ax1.annotate(
            "",
            xy=(arrow[2], arrow[3]),
            xytext=(arrow[0], arrow[1]),
            arrowprops={"arrowstyle": "-|>", "color": "#bef264", "lw": 1.8},
        )
    legend_items = [
        mpatches.Patch(color="#e879f9", label="Lumen contour"),
        mpatches.Patch(color="#22d3ee", label="Lesion contour"),
    ]
    ax1.legend(
        handles=legend_items,
        loc="lower left",
        fontsize=8,
        framealpha=0.65,
        facecolor="#111827",
        edgecolor="#334155",
        labelcolor="white",
    )
    ax1.set_title("Boundary risk / lumen-lesion geometry", fontsize=11, color="white")
    ax1.axis("off")

    ax2 = fig.add_subplot(1, 2, 2)
    metrics = [
        ("SII", results["sii"]),
        ("BCI", results["bci"]),
        ("CRI", results["cri"]),
        ("Composite", results["composite_score"]),
    ]
    ax2.bar([m[0] for m in metrics], [m[1] for m in metrics], color=["#2196F3", "#9C27B0", "#FF5722", "#4CAF50"])
    ax2.set_ylim(0, 1)
    ax2.set_title("Core Metrics", fontsize=11, color="white")
    ax2.tick_params(colors="white")
    ax2.set_facecolor("#111")

    morphology = results.get("morphology") or {}
    fourier = results.get("fourier") or {}
    geometry_line = (
        f"Smoothness {float(fourier.get('smoothness_index', 0.0)):.2f}  |  "
        f"Roughness {float(fourier.get('boundary_roughness', 0.0)):.2f}  |  "
        f"Solidity {float(morphology.get('solidity', 0.0)):.2f}  |  "
        f"Outward expansion {float(geometry.get('outward_expansion_ratio', 0.0)):+.2f}"
    )
    fig.text(0.52, 0.035, geometry_line, ha="center", color="#cbd5e1", fontsize=8)
    fig.tight_layout(rect=[0, 0.08, 1, 0.95])
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--annotation", required=True)
    parser.add_argument("--patient-id", default="unknown")
    parser.add_argument("--lumen-polygon", default="")
    parser.add_argument("--lumen-bbox", default="")
    args = parser.parse_args()

    image_path = Path(args.image)
    annotation_path = Path(args.annotation)
    if not image_path.exists():
        print(json.dumps({"success": False, "patient_id": args.patient_id, "error": f"Image not found: {image_path}"}))
        return 1
    if not annotation_path.exists():
        print(json.dumps({"success": False, "patient_id": args.patient_id, "error": f"Annotation not found: {annotation_path}"}))
        return 1

    extractor = ExplainableFeatureExtractorV4(
        tolerance_pixels=8,
        track_offset=5,
        window_size=11,
        pixel_spacing=0.1,
        multi_scale=True,
        scales=[3, 5, 7],
    )

    try:
        results = extractor.analyze_image(str(image_path), str(annotation_path), visualize=False)
        image = cv2.imread(str(image_path))
        points, image_size = extractor.load_annotation(str(annotation_path))
        mask = extractor.create_mask_from_points(points, image_size)
        contour = extractor.get_smooth_contour(mask, num_points=360)
        lumen_points = _parse_json_arg(args.lumen_polygon, "lumen polygon")
        if not isinstance(lumen_points, list) or len(lumen_points) < 3:
            lumen_points = None
        elif not all(
            isinstance(point, (list, tuple))
            and len(point) >= 2
            and all(isinstance(coord, (int, float)) for coord in point[:2])
            for point in lumen_points
        ):
            lumen_points = None
        lumen_bbox = _parse_json_arg(args.lumen_bbox, "lumen bbox")
        if not isinstance(lumen_bbox, dict):
            lumen_bbox = _bbox_from_points(lumen_points)
        else:
            try:
                lumen_bbox = {
                    "x1": float(lumen_bbox["x1"]),
                    "y1": float(lumen_bbox["y1"]),
                    "x2": float(lumen_bbox["x2"]),
                    "y2": float(lumen_bbox["y2"]),
                }
                if lumen_bbox["x2"] <= lumen_bbox["x1"] or lumen_bbox["y2"] <= lumen_bbox["y1"]:
                    lumen_bbox = None
            except (KeyError, TypeError, ValueError):
                lumen_bbox = _bbox_from_points(lumen_points)
        lumen_points_array = np.asarray(lumen_points, dtype=np.float64) if lumen_points else None
        if lumen_points_array is None and lumen_bbox is not None:
            lumen_points_array = np.asarray(
                [
                    [lumen_bbox["x1"], lumen_bbox["y1"]],
                    [lumen_bbox["x2"], lumen_bbox["y1"]],
                    [lumen_bbox["x2"], lumen_bbox["y2"]],
                    [lumen_bbox["x1"], lumen_bbox["y2"]],
                ],
                dtype=np.float64,
            )
        lumen_mask = (
            extractor.create_mask_from_points(lumen_points_array, image_size)
            if lumen_points_array is not None
            else None
        )
        results["geometry"] = _geometry_summary(mask, lumen_mask, lumen_points, lumen_bbox)
        lumen_contour = (
            extractor.get_smooth_contour(lumen_mask, num_points=240)
            if lumen_mask is not None and np.any(lumen_mask > 0)
            else None
        )

        morphology = results["morphology"]
        result1 = results["algorithm1"]
        result2 = results["algorithm2"]
        result3 = results["algorithm3"]
        viz_base64 = build_visualization_base64(
            image,
            contour,
            lumen_contour,
            result1,
            result2,
            result3,
            results,
        )

        payload = {
            "success": True,
            "patient_id": args.patient_id,
            "predicted_stage": results["predicted_t_stage"],
            "confidence": results["confidence"],
            "sii": results["sii"],
            "bci": results["bci"],
            "cri": results["cri"],
            "composite_score": results["composite_score"],
            "total_danger_regions": (
                result1["num_weak_regions"]
                + result2["num_breach_regions"]
                + result3["num_high_risk_regions"]
            ),
            "morphology": {
                "diameter_mm": morphology.get("equivalent_diameter_mm"),
                "area_mm2": morphology.get("area_mm2"),
                "circularity": morphology.get("circularity"),
                "irregularity": morphology.get("irregularity"),
                "aspect_ratio": morphology.get("aspect_ratio"),
                "solidity": morphology.get("solidity"),
                "smoothness_index": results["fourier"].get("smoothness_index"),
                "boundary_roughness": results["fourier"].get("boundary_roughness"),
                "shape_complexity": results["fourier"].get("shape_complexity"),
            },
            "geometry": results.get("geometry"),
            "explanation": results["explanation"],
            "visualization_base64": viz_base64,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"success": False, "patient_id": args.patient_id, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
