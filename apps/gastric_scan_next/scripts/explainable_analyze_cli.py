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

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.explainable_features_v4 import ExplainableFeatureExtractorV4  # noqa: E402


def build_visualization_base64(image, contour, result1, result2, result3, results) -> str:
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
    ax1.set_title("Risk Map", fontsize=11, color="white")
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

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--annotation", required=True)
    parser.add_argument("--patient-id", default="unknown")
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
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        points, image_size = extractor.load_annotation(str(annotation_path))
        mask = extractor.create_mask_from_points(points, image_size)
        contour = extractor.get_smooth_contour(mask, num_points=360)

        morphology = results["morphology"]
        result1 = results["algorithm1"]
        result2 = results["algorithm2"]
        result3 = results["algorithm3"]
        viz_base64 = build_visualization_base64(image, contour, result1, result2, result3, results)

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
            },
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
