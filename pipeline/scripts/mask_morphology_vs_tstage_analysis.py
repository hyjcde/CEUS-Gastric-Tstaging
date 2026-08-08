"""
Mask 形态学特征 & 边界外侧纹理 vs T分期 关联性分析

目标：验证以下假设
1. 病灶 mask 的形态学特征（不规则度、凸度、偏心率等）是否随 T 分期变化
2. 病灶边界外侧的纹理特征（均匀性、梯度、层次感）是否随 T 分期变化
3. 沿轮廓不同方向的特征异质性是否和 T 分期有关

如果以上成立，就说明 GT mask 蕴含了 T 分期的隐式信息，
且医生标注"侵犯方向"的方案是有理论依据的。
"""
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats, ndimage
from skimage import measure
from tqdm import tqdm

BASE_DIR = Path("/data/research/gastric/Tstaging")
DATA_DIR = BASE_DIR / "pipeline/data/tstaging_4class"
OUTPUT_DIR = BASE_DIR / "pipeline/analysis/mask_vs_tstage"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
N_SECTORS = 8


def load_mask_from_annotation(ann_path, img_shape):
    with open(ann_path) as f:
        data = json.load(f)
    h, w = img_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for shape in data.get("shapes", []):
        pts = np.array(shape["points"], dtype=np.int32)
        if len(pts) >= 3:
            cv2.fillPoly(mask, [pts], 255)
    return mask


def compute_morphology_features(mask):
    binary = (mask > 0).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None

    cnt = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(cnt)
    if area < 50:
        return None
    perimeter = cv2.arcLength(cnt, True)
    if perimeter == 0:
        return None

    hull = cv2.convexHull(cnt)
    hull_area = cv2.contourArea(hull)

    circularity = 4 * np.pi * area / (perimeter ** 2)
    solidity = area / hull_area if hull_area > 0 else 0
    convexity_deficiency = 1.0 - solidity

    rect = cv2.minAreaRect(cnt)
    w_r, h_r = rect[1]
    aspect_ratio = max(w_r, h_r) / min(w_r, h_r) if min(w_r, h_r) > 0 else 1.0

    if len(cnt) >= 5:
        ellipse = cv2.fitEllipse(cnt)
        (_, (ma, MA), _) = ellipse
        eccentricity = np.sqrt(1 - (min(ma, MA) / max(ma, MA)) ** 2) if max(ma, MA) > 0 else 0
    else:
        eccentricity = 0

    h_img, w_img = mask.shape
    mask_ratio = area / (h_img * w_img)

    # boundary roughness: std of distances from centroid to contour points
    M = cv2.moments(cnt)
    if M["m00"] == 0:
        return None
    cx = M["m10"] / M["m00"]
    cy = M["m01"] / M["m00"]

    dists = np.sqrt((cnt[:, 0, 0] - cx) ** 2 + (cnt[:, 0, 1] - cy) ** 2)
    mean_dist = dists.mean()
    roughness = dists.std() / mean_dist if mean_dist > 0 else 0

    # curvature variance along contour
    pts_f = cnt[:, 0, :].astype(float)
    n_pts = len(pts_f)
    if n_pts > 10:
        step = max(1, n_pts // 50)
        curvatures = []
        for i in range(0, n_pts, step):
            p0 = pts_f[(i - step) % n_pts]
            p1 = pts_f[i]
            p2 = pts_f[(i + step) % n_pts]
            v1 = p1 - p0
            v2 = p2 - p1
            cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)
            denom = n1 * n2 * (n1 + n2) / 2
            curvatures.append(cross / denom if denom > 0 else 0)
        curvature_var = np.var(curvatures)
        curvature_max = np.max(curvatures)
    else:
        curvature_var = 0
        curvature_max = 0

    return {
        "area": area,
        "perimeter": perimeter,
        "circularity": circularity,
        "solidity": solidity,
        "convexity_deficiency": convexity_deficiency,
        "aspect_ratio": aspect_ratio,
        "eccentricity": eccentricity,
        "mask_ratio": mask_ratio,
        "roughness": roughness,
        "curvature_var": curvature_var,
        "curvature_max": curvature_max,
        "centroid_x": cx,
        "centroid_y": cy,
        "n_contour_points": n_pts,
    }


def compute_border_texture_features(img_gray, mask, centroid, n_sectors=8):
    """Analyze texture just outside the mask boundary in N angular sectors."""
    binary = (mask > 0).astype(np.uint8)

    kernel_inner = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    kernel_outer = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    dilated = cv2.dilate(binary, kernel_outer, iterations=1)
    eroded = cv2.erode(binary, kernel_inner, iterations=1)

    # outer band: dilated - original mask
    outer_band = dilated.astype(int) - binary.astype(int)
    outer_band = np.clip(outer_band, 0, 1).astype(np.uint8)

    # inner band: original - eroded
    inner_band = binary.astype(int) - eroded.astype(int)
    inner_band = np.clip(inner_band, 0, 1).astype(np.uint8)

    if outer_band.sum() < 10 or inner_band.sum() < 10:
        return None

    cx, cy = centroid
    h, w = img_gray.shape
    yy, xx = np.mgrid[:h, :w]
    angles = np.arctan2(cy - yy, xx - cx)  # radians, -pi to pi
    angles = (angles + 2 * np.pi) % (2 * np.pi)  # 0 to 2pi

    grad_x = cv2.Sobel(img_gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(img_gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_mag = np.sqrt(grad_x ** 2 + grad_y ** 2)

    sector_features = []
    sector_angle_bins = np.linspace(0, 2 * np.pi, n_sectors + 1)

    for i in range(n_sectors):
        a_lo, a_hi = sector_angle_bins[i], sector_angle_bins[i + 1]
        sector_mask = (angles >= a_lo) & (angles < a_hi)

        outer_sector = outer_band & sector_mask.astype(np.uint8)
        inner_sector = inner_band & sector_mask.astype(np.uint8)

        outer_pixels = img_gray[outer_sector > 0]
        inner_pixels = img_gray[inner_sector > 0]
        outer_grad = grad_mag[outer_sector > 0]

        if len(outer_pixels) < 5 or len(inner_pixels) < 5:
            sector_features.append({
                "sector": i,
                "angle_center_deg": np.degrees((a_lo + a_hi) / 2),
                "valid": False,
            })
            continue

        # contrast between inner (tumor) and outer (wall) in this sector
        intensity_diff = float(np.mean(outer_pixels)) - float(np.mean(inner_pixels))

        sector_features.append({
            "sector": i,
            "angle_center_deg": np.degrees((a_lo + a_hi) / 2),
            "valid": True,
            "outer_mean": float(np.mean(outer_pixels)),
            "outer_std": float(np.std(outer_pixels)),
            "inner_mean": float(np.mean(inner_pixels)),
            "inner_std": float(np.std(inner_pixels)),
            "intensity_diff": intensity_diff,
            "outer_grad_mean": float(np.mean(outer_grad)),
            "outer_grad_std": float(np.std(outer_grad)),
            "outer_entropy": float(stats.entropy(np.histogram(outer_pixels, bins=32, density=True)[0] + 1e-10)),
        })

    valid_sectors = [s for s in sector_features if s.get("valid", False)]
    if len(valid_sectors) < 3:
        return None

    diffs = [s["intensity_diff"] for s in valid_sectors]
    outer_stds = [s["outer_std"] for s in valid_sectors]
    outer_grads = [s["outer_grad_mean"] for s in valid_sectors]

    # sector with max contrast → likely wall layers preserved
    # sector with min contrast → tumor may have merged with outside
    max_diff_sector = max(valid_sectors, key=lambda s: s["intensity_diff"])
    min_diff_sector = min(valid_sectors, key=lambda s: s["intensity_diff"])

    # heterogeneity: how much the border texture varies across sectors
    diff_range = max(diffs) - min(diffs)
    diff_std = np.std(diffs)
    grad_heterogeneity = np.std(outer_grads)

    # the sector where outer texture is most "disordered" (high std, high entropy)
    most_disordered = max(valid_sectors, key=lambda s: s["outer_std"])

    return {
        "n_valid_sectors": len(valid_sectors),
        "intensity_diff_mean": np.mean(diffs),
        "intensity_diff_std": diff_std,
        "intensity_diff_range": diff_range,
        "intensity_diff_max": max(diffs),
        "intensity_diff_min": min(diffs),
        "max_diff_sector_angle": max_diff_sector["angle_center_deg"],
        "min_diff_sector_angle": min_diff_sector["angle_center_deg"],
        "outer_grad_mean_all": np.mean(outer_grads),
        "outer_grad_heterogeneity": grad_heterogeneity,
        "most_disordered_angle": most_disordered["angle_center_deg"],
        "most_disordered_std": most_disordered["outer_std"],
        "sector_details": sector_features,
    }


def main():
    print("Loading data...")
    df = pd.read_csv(DATA_DIR / "train.csv")
    # also load internal test sets for more T2 samples
    for f in ["val.csv", "test_prospective.csv"]:
        fp = DATA_DIR / f
        if fp.exists():
            extra = pd.read_csv(fp)
            extra["split_origin"] = f.replace(".csv", "")
            df = pd.concat([df, extra], ignore_index=True)

    df["split_origin"] = df.get("split_origin", "train")
    print(f"Total samples: {len(df)}")
    print(f"Label distribution:\n{df['label'].value_counts().sort_index()}")

    all_records = []
    errors = 0

    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Analyzing"):
        img_path = BASE_DIR / row["image_path"]
        ann_dir = img_path.parent.parent / "annotations"
        ann_path = ann_dir / (img_path.stem + ".json")

        if not ann_path.exists() or not img_path.exists():
            errors += 1
            continue

        try:
            img = cv2.imread(str(img_path))
            if img is None:
                errors += 1
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            mask = load_mask_from_annotation(str(ann_path), img.shape)

            if mask.sum() == 0:
                errors += 1
                continue

            morph = compute_morphology_features(mask)
            if morph is None:
                errors += 1
                continue

            centroid = (morph["centroid_x"], morph["centroid_y"])
            texture = compute_border_texture_features(gray, mask, centroid, N_SECTORS)

            record = {
                "image": row["image_path"],
                "patient_id": row["patient_id"],
                "label": row["label"],
                "source": row["source"],
            }
            record.update({f"morph_{k}": v for k, v in morph.items()
                          if k not in ("centroid_x", "centroid_y")})

            if texture is not None:
                record.update({f"tex_{k}": v for k, v in texture.items()
                              if k != "sector_details"})

            all_records.append(record)
        except Exception as e:
            errors += 1

    print(f"\nProcessed: {len(all_records)}, Errors/Skipped: {errors}")

    results = pd.DataFrame(all_records)
    results.to_csv(OUTPUT_DIR / "mask_features_all.csv", index=False)

    # === Statistical Analysis ===
    print("\n" + "=" * 70)
    print("MORPHOLOGY FEATURES vs T-STAGE")
    print("=" * 70)

    morph_cols = [c for c in results.columns if c.startswith("morph_")]
    tex_cols = [c for c in results.columns if c.startswith("tex_")]

    sig_results = []

    for col in morph_cols + tex_cols:
        if results[col].dtype not in [np.float64, np.float32, float, int, np.int64]:
            continue
        groups = [results[results["label"] == i][col].dropna() for i in range(4)]
        groups = [g for g in groups if len(g) >= 10]
        if len(groups) < 3:
            continue

        try:
            stat, p_val = stats.kruskal(*groups)
        except:
            continue

        means = [f"{g.mean():.4f}" for g in groups]
        sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"

        sig_results.append({
            "feature": col,
            "kruskal_H": stat,
            "p_value": p_val,
            "significance": sig,
            "T1_mean": groups[0].mean() if len(groups) > 0 else None,
            "T2_mean": groups[1].mean() if len(groups) > 1 else None,
            "T3_mean": groups[2].mean() if len(groups) > 2 else None,
            "T4_mean": groups[3].mean() if len(groups) > 3 else None,
        })

        if p_val < 0.05:
            print(f"\n  {col} ({sig}, p={p_val:.2e}, H={stat:.1f})")
            print(f"    T1={means[0]}  T2={means[1]}  T3={means[2]}", end="")
            if len(means) > 3:
                print(f"  T4={means[3]}")
            else:
                print()

    sig_df = pd.DataFrame(sig_results).sort_values("p_value")
    sig_df.to_csv(OUTPUT_DIR / "statistical_tests.csv", index=False)

    # === Visualization ===
    print("\n\nGenerating figures...")

    # internal data only for cleaner analysis
    internal = results[results["source"].str.startswith("int/")]

    # Fig 1: top significant morphology features box plots
    top_morph = sig_df[sig_df["feature"].str.startswith("morph_") & (sig_df["p_value"] < 0.05)]
    top_morph = top_morph.head(6)

    if len(top_morph) > 0:
        n_plots = len(top_morph)
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        axes = axes.flatten()
        for i, (_, row_s) in enumerate(top_morph.iterrows()):
            if i >= 6:
                break
            feat = row_s["feature"]
            ax = axes[i]
            data_by_t = [internal[internal["label"] == t][feat].dropna() for t in range(4)]
            bp = ax.boxplot(data_by_t, labels=CLASS_NAMES, patch_artist=True,
                           widths=0.6, showfliers=False)
            colors = ["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"]
            for patch, color in zip(bp["boxes"], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
            ax.set_title(f"{feat}\n(p={row_s['p_value']:.2e})", fontsize=11)
            ax.grid(axis="y", alpha=0.3)

        for j in range(i + 1, 6):
            axes[j].set_visible(False)

        fig.suptitle("Morphology Features vs T-Stage (Internal Data)", fontsize=14, fontweight="bold")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "fig1_morphology_boxplots.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved fig1_morphology_boxplots.png")

    # Fig 2: top significant texture features
    top_tex = sig_df[sig_df["feature"].str.startswith("tex_") & (sig_df["p_value"] < 0.05)]
    top_tex = top_tex.head(6)

    if len(top_tex) > 0:
        n_plots = len(top_tex)
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        axes = axes.flatten()
        for i, (_, row_s) in enumerate(top_tex.iterrows()):
            if i >= 6:
                break
            feat = row_s["feature"]
            ax = axes[i]
            data_by_t = [internal[internal["label"] == t][feat].dropna() for t in range(4)]
            bp = ax.boxplot(data_by_t, labels=CLASS_NAMES, patch_artist=True,
                           widths=0.6, showfliers=False)
            colors = ["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"]
            for patch, color in zip(bp["boxes"], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
            ax.set_title(f"{feat}\n(p={row_s['p_value']:.2e})", fontsize=11)
            ax.grid(axis="y", alpha=0.3)

        for j in range(i + 1, 6):
            axes[j].set_visible(False)

        fig.suptitle("Border Texture Features vs T-Stage (Internal Data)", fontsize=14, fontweight="bold")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "fig2_texture_boxplots.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved fig2_texture_boxplots.png")

    # Fig 3: Correlation heatmap of significant features
    sig_features = sig_df[sig_df["p_value"] < 0.05]["feature"].tolist()
    if len(sig_features) >= 3:
        sig_features_clean = [f for f in sig_features if f in internal.columns and internal[f].dtype in [float, np.float64, int, np.int64]]
        if len(sig_features_clean) >= 3:
            corr = internal[sig_features_clean + ["label"]].corr()
            fig, ax = plt.subplots(figsize=(12, 10))
            im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
            ax.set_xticks(range(len(corr.columns)))
            ax.set_yticks(range(len(corr.columns)))
            labels = [c.replace("morph_", "M:").replace("tex_", "T:") for c in corr.columns]
            ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels(labels, fontsize=8)
            fig.colorbar(im, ax=ax, shrink=0.8)
            ax.set_title("Feature Correlation Matrix (significant features + T-stage label)")
            fig.tight_layout()
            fig.savefig(OUTPUT_DIR / "fig3_correlation_heatmap.png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            print(f"  Saved fig3_correlation_heatmap.png")

    # Fig 4: T2 vs T3 specific comparison
    t2_data = internal[internal["label"] == 1]
    t3_data = internal[internal["label"] == 2]

    if len(t2_data) > 10 and len(t3_data) > 10:
        print("\n" + "=" * 70)
        print("T2 vs T3 SPECIFIC COMPARISON (the hardest pair)")
        print("=" * 70)

        t2t3_sig = []
        for col in sig_features_clean:
            t2_vals = t2_data[col].dropna()
            t3_vals = t3_data[col].dropna()
            if len(t2_vals) >= 10 and len(t3_vals) >= 10:
                u_stat, p_val = stats.mannwhitneyu(t2_vals, t3_vals, alternative="two-sided")
                effect_size = abs(t2_vals.mean() - t3_vals.mean()) / np.sqrt(
                    (t2_vals.std() ** 2 + t3_vals.std() ** 2) / 2) if (t2_vals.std() + t3_vals.std()) > 0 else 0
                t2t3_sig.append({
                    "feature": col,
                    "T2_mean": t2_vals.mean(),
                    "T3_mean": t3_vals.mean(),
                    "p_value": p_val,
                    "cohens_d": effect_size,
                })
                if p_val < 0.05:
                    print(f"  {col}: T2={t2_vals.mean():.4f} vs T3={t3_vals.mean():.4f}  p={p_val:.4f}  d={effect_size:.3f}")

        t2t3_df = pd.DataFrame(t2t3_sig).sort_values("p_value")
        t2t3_df.to_csv(OUTPUT_DIR / "t2_vs_t3_comparison.csv", index=False)

    # Summary
    n_sig = len(sig_df[sig_df["p_value"] < 0.05])
    n_morph_sig = len(sig_df[(sig_df["feature"].str.startswith("morph_")) & (sig_df["p_value"] < 0.05)])
    n_tex_sig = len(sig_df[(sig_df["feature"].str.startswith("tex_")) & (sig_df["p_value"] < 0.05)])

    summary = {
        "total_analyzed": len(results),
        "errors_skipped": errors,
        "n_features_tested": len(sig_df),
        "n_significant_p05": n_sig,
        "n_morph_significant": n_morph_sig,
        "n_texture_significant": n_tex_sig,
        "conclusion": "POSITIVE" if n_sig >= 3 else "INCONCLUSIVE" if n_sig >= 1 else "NEGATIVE",
    }

    with open(OUTPUT_DIR / "analysis_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"  Total analyzed: {len(results)}")
    print(f"  Features tested: {len(sig_df)}")
    print(f"  Significant (p<0.05): {n_sig} ({n_morph_sig} morphology, {n_tex_sig} texture)")
    print(f"  Conclusion: {summary['conclusion']}")
    print(f"  All results saved to: {OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
