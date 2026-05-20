#!/usr/bin/env python3
"""Generate DINOv3 token case panels for Frame+agg · Prospective (test_prospective_full)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

# Reuse DINO inference helpers from external token panel script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_external_source_dino_token_panels import (  # noqa: E402
    CLASS_NAMES,
    infer_dino_maps,
    load_model,
    mark_query_on_axis,
    plot_probs,
    read_image,
    resolve_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANATOMIC_DIR = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class_anatomic_region_contrastive" / "regions"
FULL_PROSP_DIR = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class_prospective_full_anatomic" / "regions"
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last2blocks_mlp_decoder.yaml"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/dinov3_framelevel_scalar_train_eval/prospective_dino_case_panels"
)
FIG_RESULTS = PROJECT_ROOT / "docs/mainline/figures/results"

PREOP_COLS = [
    "age", "age_missing", "sex", "sex_missing",
    "tumor_length_cm", "tumor_length_cm_missing",
    "tumor_thickness_cm", "tumor_thickness_cm_missing",
    "tumor_location", "tumor_location_missing",
    "cea_value", "cea_value_missing", "cea_binary", "cea_binary_missing",
    "ca199_value", "ca199_value_missing", "ca199_binary", "ca199_binary_missing",
    "lauren_type", "lauren_type_missing", "differentiation", "differentiation_missing",
]
ANATOMIC_COLS = [
    "anatomic_lumen_missing", "anatomic_lesion_area_px", "anatomic_outer_band_area_px",
    "anatomic_inner_band_area_px", "anatomic_bridge_area_px",
    "anatomic_lesion_lumen_distance_px", "anatomic_lesion_lumen_distance_norm",
    "anatomic_outward_angle_deg", "anatomic_outer_mean", "anatomic_outer_std",
    "anatomic_outer_lap_var", "anatomic_inner_mean", "anatomic_inner_std",
    "anatomic_inner_lap_var", "anatomic_outer_inner_mean_delta",
    "anatomic_outer_inner_std_delta", "anatomic_outer_inner_lap_var_delta",
    "box_guided_focus_area_px", "lesion_lumen_wall_area_px",
    "same_frame_intact_wall_control_area_px", "control_wall_quality_score",
    "crop_box_x1", "crop_box_y1", "crop_box_x2", "crop_box_y2",
]

BUCKET_TITLES = {
    "correct_advanced": "Correct advanced T3/T4+ (high conf)",
    "correct_early": "Correct early T1/T2 (high conf)",
    "errors_high_conf": "High-confidence error",
    "t2_t3_boundary": "T2/T3 boundary",
    "t3_t4_understage": "T4+ under-staged as T3",
}
BUCKET_TITLES_ZH = {
    "correct_advanced": "正确 · 晚期 T3/T4+ 高置信",
    "correct_early": "正确 · 早期 T1/T2 高置信",
    "errors_high_conf": "误诊 · 高置信错误",
    "t2_t3_boundary": "边界 · T2/T3 难分",
    "t3_t4_understage": "边界 · T4+ 低估为 T3",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DINO case panels for prospective full test.")
    p.add_argument("--train-csv", type=Path, default=ANATOMIC_DIR / "train_clinical.csv")
    p.add_argument("--test-csv", type=Path, default=FULL_PROSP_DIR / "test_prospective_full_clinical.csv")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--copy-figures-dir", type=Path, default=FIG_RESULTS)
    p.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    p.add_argument("--image-size", type=int, default=512)
    p.add_argument("--layer-index", type=int, default=11)
    p.add_argument("--frames-per-case", type=int, default=3)
    p.add_argument("--seed", type=int, default=20260513)
    p.add_argument("--max-per-bucket", type=int, default=3)
    return p.parse_args()


def read_csv(path: Path) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(path, low_memory=False)
    if "anatomic_status" in df.columns:
        df = df[df["anatomic_status"].astype(str).eq("ok")].copy()
    df["class_label"] = pd.to_numeric(df["class_label"], errors="coerce")
    df = df[df["class_label"].notna()].copy()
    df["class_label"] = df["class_label"].astype(int)
    df["patient_id"] = df["patient_id"].astype(str)
    cols = [c for c in PREOP_COLS + ANATOMIC_COLS if c in df.columns]
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True), cols


def align_probs(model, x: np.ndarray) -> np.ndarray:
    raw = model.predict_proba(x)
    classes = model.steps[-1][1].classes_
    probs = np.zeros((x.shape[0], len(CLASS_NAMES)), dtype=np.float32)
    for idx, cls in enumerate(classes):
        probs[:, int(cls)] = raw[:, idx]
    return probs


def patient_aggregate(group: pd.DataFrame) -> np.ndarray:
    probs = group[[f"prob_{name}" for name in CLASS_NAMES]].to_numpy(dtype=np.float32)
    score = probs[:, 2] + probs[:, 3]
    take = np.argsort(score)[-min(3, len(score)) :]
    return probs[take].mean(axis=0)


def select_cases(patient_df: pd.DataFrame, max_per: int) -> pd.DataFrame:
    correct = patient_df[patient_df["label"].eq(patient_df["pred"])].copy()
    errors = patient_df[~patient_df["label"].eq(patient_df["pred"])].copy()
    advanced = correct[correct["label"].isin([2, 3])].sort_values(["confidence", "margin"], ascending=False)
    early = correct[correct["label"].isin([0, 1])].sort_values(["confidence", "margin"], ascending=False)
    err = errors.sort_values(["confidence", "margin"], ascending=False)
    t2t3 = patient_df[patient_df["label"].isin([1, 2])].copy()
    t2t3["boundary_conf"] = t2t3[["patient_prob_T2", "patient_prob_T3"]].max(axis=1)
    t2t3 = t2t3.sort_values("boundary_conf", ascending=False)
    understage = patient_df[(patient_df["label"] == 3) & (patient_df["pred"] == 2)].sort_values(
        "confidence", ascending=False
    )
    rows = []
    for bucket, frame in [
        ("correct_advanced", advanced.head(max_per)),
        ("correct_early", early.head(max_per)),
        ("errors_high_conf", err.head(max_per)),
        ("t2_t3_boundary", t2t3.head(max_per)),
        ("t3_t4_understage", understage.head(max_per)),
    ]:
        for _, r in frame.iterrows():
            rows.append({**r.to_dict(), "bucket": bucket})
    return pd.DataFrame(rows)


def plot_dino_case(
    model,
    patient_rows: pd.DataFrame,
    manifest_row: pd.Series,
    output_path: Path,
    args: argparse.Namespace,
    device: torch.device,
) -> dict:
    patient_id = str(patient_rows["patient_id"].iloc[0])
    true_label = CLASS_NAMES[int(manifest_row["label"])]
    pred_label = CLASS_NAMES[int(manifest_row["pred"])]
    patient_probs = np.array(
        [float(manifest_row[f"patient_prob_{n}"]) for n in CLASS_NAMES], dtype=np.float32
    )
    advanced = patient_rows[[f"prob_{name}" for name in CLASS_NAMES]].to_numpy(dtype=np.float32)[:, 2:].sum(axis=1)
    selected = patient_rows.iloc[np.argsort(advanced)[-min(args.frames_per_case, len(patient_rows)) :][::-1]].copy()
    n = len(selected)
    bucket = str(manifest_row["bucket"])
    fig, axes = plt.subplots(nrows=n, ncols=8, figsize=(25, 3.35 * n))
    if n == 1:
        axes = np.array([axes])
    fig.patch.set_facecolor("#1a2332")
    fig.suptitle(
        f"[{BUCKET_TITLES.get(bucket, bucket)}] Patient {patient_id} | "
        f"True {true_label} → Pred {pred_label} | "
        f"Patient probs {np.round(patient_probs, 3).tolist()}",
        fontsize=12,
        color="#e8edf4",
        y=0.995,
    )
    for row_i, (_, row) in enumerate(selected.iterrows()):
        image_path = resolve_path(row.get("image_path"))
        if image_path is None:
            continue
        original = read_image(image_path)
        overlay = read_image(row.get("anatomic_overlay_path"))
        probs = row[[f"prob_{name}" for name in CLASS_NAMES]].to_numpy(dtype=np.float32)
        maps = infer_dino_maps(model, image_path, row, args.image_size, args.layer_index, device)
        panels = [
            (original, "Original US", None),
            (overlay, "Anatomic overlay", None),
            (maps["rainbow_pca"], "Rainbow PCA (official)", None),
            (maps["query_cosine"], "Cosine @ lesion center", "magma"),
            (maps["token_norm"], "DINO token norm", "viridis"),
            (maps["lesion_affinity"], "Lesion region affinity", "magma"),
            (maps["wall_evidence"], "Outer−inner evidence", "coolwarm"),
        ]
        for col_i, (content, title, cmap) in enumerate(panels):
            ax = axes[row_i, col_i]
            if cmap is None and getattr(content, "ndim", 2) == 3:
                ax.imshow(content)
            else:
                ax.imshow(content, cmap=cmap)
            ax.set_title(title, fontsize=9, color="#e8edf4")
            ax.axis("off")
            ax.set_facecolor("#1a2332")
            if col_i == 3:
                mark_query_on_axis(ax, maps, maps["input_size"])
        axp = axes[row_i, 7]
        axp.set_facecolor("#243044")
        plot_probs(axp, probs, f"Frame P(T) · Adv={float(probs[2]+probs[3]):.2f}")
        for spine in axp.spines.values():
            spine.set_color("#8fa3bf")
        axp.title.set_color("#e8edf4")
        axp.tick_params(colors="#e8edf4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return {
        "patient_id": patient_id,
        "bucket": bucket,
        "true_label": true_label,
        "pred_label": pred_label,
        "correct": int(manifest_row["label"] == manifest_row["pred"]),
        "output_path": str(output_path),
        "public_figure": "",
    }


def copy_to_results(local_path: Path, copy_dir: Path, bucket: str, patient_id: str, true_l: str, pred_l: str) -> str:
    copy_dir.mkdir(parents=True, exist_ok=True)
    fname = f"case_framelevel_prosp_dino_{bucket}_{patient_id}_{true_l}_pred_{pred_l}.png"
    dest = copy_dir / fname
    shutil.copy2(local_path, dest)
    return f"figures/results/{fname}"


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train, cols = read_csv(args.train_csv)
    test, test_cols = read_csv(args.test_csv)
    cols = [c for c in cols if c in test_cols]

    model_rf = make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(
            n_estimators=900,
            max_depth=9,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=args.seed,
            n_jobs=-1,
        ),
    )
    model_rf.fit(train[cols].to_numpy(dtype=np.float32), train["class_label"].to_numpy(dtype=int))
    probs = align_probs(model_rf, test[cols].to_numpy(dtype=np.float32))
    for idx, name in enumerate(CLASS_NAMES):
        test[f"prob_{name}"] = probs[:, idx]

    patient_rows_list = []
    for patient_id, group in test.groupby("patient_id", sort=True):
        labels = group["class_label"].unique()
        if len(labels) != 1:
            continue
        pp = patient_aggregate(group)
        patient_rows_list.append(
            {
                "patient_id": patient_id,
                "label": int(labels[0]),
                "pred": int(pp.argmax()),
                "confidence": float(pp.max()),
                "margin": float(np.sort(pp)[-1] - np.sort(pp)[-2]),
                **{f"patient_prob_{name}": float(pp[i]) for i, name in enumerate(CLASS_NAMES)},
            }
        )
    patient_df = pd.DataFrame(patient_rows_list)
    manifest = select_cases(patient_df, args.max_per_bucket)
    if manifest.empty:
        raise RuntimeError("No cases selected for panels.")

    device = torch.device(args.device)
    dino_model, hub_model = load_model(args.config, device)

    panel_rows = []
    public_paths: list[dict] = []
    for _, mrow in manifest.iterrows():
        pid = str(mrow["patient_id"])
        rows = test[test["patient_id"].astype(str).eq(pid)].copy()
        bucket = str(mrow["bucket"])
        true_l = CLASS_NAMES[int(mrow["label"])].replace("+", "plus")
        pred_l = CLASS_NAMES[int(mrow["pred"])].replace("+", "plus")
        out = args.output_dir / bucket / f"{pid}_{true_l}_pred_{pred_l}_dino.png"
        rec = plot_dino_case(dino_model, rows, mrow, out, args, device)
        pub = copy_to_results(out, args.copy_figures_dir, bucket, pid, true_l, pred_l)
        rec["public_figure"] = pub
        panel_rows.append(rec)
        public_paths.append({"bucket": bucket, "patient_id": pid, "figure": pub, **rec})

    panel_df = pd.DataFrame(panel_rows)
    panel_df.to_csv(args.output_dir / "dino_panel_manifest.csv", index=False)
    test.to_csv(args.output_dir / "frame_predictions.csv", index=False)
    patient_df.to_csv(args.output_dir / "patient_predictions.csv", index=False)
    manifest.to_csv(args.output_dir / "case_selection.csv", index=False)

    summary = {
        "hub_model": hub_model,
        "layer_index": args.layer_index,
        "test_frames": int(len(test)),
        "test_patients": int(len(patient_df)),
        "panel_count": int(len(panel_df)),
        "buckets": panel_df["bucket"].value_counts().to_dict(),
        "public_figures": public_paths,
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (FIG_RESULTS / "framelevel_prosp_dino_cases_meta.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
