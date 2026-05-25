#!/usr/bin/env python3
"""Build docs/gastric_paper/ bundle for GitHub (methods, metrics, figures <= 1MB)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "docs/gastric_paper"
MAX_BYTES = 1_048_576

FIGURE_SOURCES = [
    "docs/mainline/figures/fig_agent_architecture_overview.png",
    "docs/mainline/figures/fig_agent_methodology_detailed.png",
    "docs/mainline/figures/fig_results_auc_comparison.png",
    "docs/mainline/figures/fig_wall_lumen_evidence.png",
    "docs/mainline/figures/results/metric_comprehensive_panel.png",
    "docs/mainline/figures/results/metric_auc_comparison.png",
    "docs/mainline/figures/results/metric_cm_external.png",
    "docs/mainline/figures/results/metric_cm_prospective.png",
    "docs/mainline/figures/results/metric_recall_heatmap.png",
    "docs/mainline/figures/results/metric_confusion_dual.png",
    "docs/mainline/figures/results/dinov3_classification_auc_summary.png",
    "docs/mainline/figures/results/dinov3_classification_auc_multimetric.png",
    "docs/mainline/figures/results/framelevel_prosp_frame_vs_patient_metrics.png",
    "docs/mainline/figures/results/t2t3_gradcam_ppt_case_pt105_T3correct.png",
    "docs/mainline/figures/results/t2t3_gradcam_ppt_case_pt189_T2correct.png",
    "docs/mainline/figures/results/t2t3_gradcam_ok_T3_pt105-4.png",
    "docs/mainline/figures/results/t2t3_gradcam_err_T2_to_T3_pt189-3.png",
    "docs/mainline/figures/results/t2t3_gradcam_panel_err_T3_to_T4.png",
]

METRIC_SOURCES = [
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301/experiment_summary.json",
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_v2_finetune_20260520_151540/experiment_summary.json",
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_v3_head_finetune_20260522_200526/experiment_summary.json",
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_v4_multitask_20260523_191522/experiment_summary.json",
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_ensemble_baseline0.3_v3_0.7/eval/test_external/test_predictions.metrics.json",
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/CHECKPOINT_RECOMMENDATIONS_T2T3.md",
    "docs/mainline/figures/results/metric_figures_meta.json",
    "docs/mainline/figures/results/t2t3_gradcam_ppt_grid_8x5_multicenter.json",
]

METHOD_DOCS = [
    "docs/mainline/research_mainline.md",
    "docs/mainline/project_scope.md",
    "docs/mainline/tstaging_classifier_architecture_zh.md",
    "docs/mainline/t2_t3_boundary_metrics_zh.md",
    "docs/mainline/dinov3_framelevel_scalar_prospective_architecture_zh.md",
    "docs/mainline/gastric_tstaging_project_framework_zh.md",
    "docs/mainline/gastric_us_agent_methodology_architecture_spec_zh.md",
    "docs/mainline/tstaging_current_mainline.md",
    "docs/mainline/model_asset_audit.md",
]


def copy_if_small(src: Path, dst: Path) -> bool:
    if not src.is_file():
        print(f"  skip missing: {src}")
        return False
    size = src.stat().st_size
    if size > MAX_BYTES:
        print(f"  skip >1MB ({size/1e6:.2f}MB): {src.name}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "figures").mkdir(parents=True)
    (OUT / "metrics").mkdir(parents=True)
    (OUT / "methods").mkdir(parents=True)

    copied_figs = []
    for rel in FIGURE_SOURCES:
        src = PROJECT / rel
        if copy_if_small(src, OUT / "figures" / src.name):
            copied_figs.append(src.name)

    # Downscale 8x5 gradcam grid for paper if source exists
    grid_src = PROJECT / "docs/mainline/figures/results/t2t3_gradcam_ppt_grid_8x5_multicenter.png"
    grid_dst = OUT / "figures/t2t3_gradcam_ppt_grid_8x5_multicenter_preview.png"
    if grid_src.is_file():
        try:
            from PIL import Image

            img = Image.open(grid_src)
            w, h = img.size
            scale = 0.48
            small = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            small.save(grid_dst, optimize=True, quality=85)
            if grid_dst.stat().st_size <= MAX_BYTES:
                copied_figs.append(grid_dst.name)
                print(f"  resized grid -> {grid_dst.name} ({grid_dst.stat().st_size/1e3:.0f}KB)")
            else:
                grid_dst.unlink(missing_ok=True)
                print("  skip grid: still >1MB after resize")
        except Exception as e:
            print(f"  skip grid resize: {e}")

    for rel in METRIC_SOURCES:
        src = PROJECT / rel
        if src.is_file() and src.stat().st_size <= MAX_BYTES:
            copy_if_small(src, OUT / "metrics" / src.name)

    for rel in METHOD_DOCS:
        src = PROJECT / rel
        if src.is_file() and src.stat().st_size <= MAX_BYTES:
            copy_if_small(src, OUT / "methods" / src.name)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_file_bytes": MAX_BYTES,
        "figures": copied_figs,
        "note": "Large raw PNGs (>1MB) stay on server; use preview or metrics JSON here.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    readme = """# Gastric T-staging 论文支撑包

本目录由 `scripts/build_gastric_paper_assets.py` 生成，**单文件 ≤ 1MB**，便于 GitHub 同步与写稿引用。

## 目录

| 子目录 | 内容 |
|--------|------|
| `methods/` | 方法学主文档副本（架构、Agent、DINOv3、T2/T3 指标） |
| `metrics/` | 实验 `experiment_summary.json`、融合指标、checkpoint 推荐 |
| `figures/` | 论文用结果图（AUC、混淆矩阵、Grad-CAM 单病例/预览） |

## 主要模型结果（外部 test）

| 模型 | AUC | T2+T3→T4+ |
|------|-----|-----------|
| baseline mask4ch full | 0.733 | 28.0% |
| antioverstage v2 | 0.705 | 18.0% |
| **antioverstage v3（推荐）** | 0.698 | 18.6% |
| ensemble 30% baseline + 70% v3 | 0.723 | 19.3% |

详见 `metrics/CHECKPOINT_RECOMMENDATIONS_T2T3.md`。

## 复现对比

```bash
python pipeline/scripts/compare_t2t3_model_variants.py --split test_external
python scripts/build_gastric_paper_assets.py   # 重建本目录
```

## 完整文档

仓库内 `docs/mainline/` 含更完整的方法与图表索引；本包为**写 gastric paper 的轻量快照**。
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Built {OUT} with {len(copied_figs)} figures")


if __name__ == "__main__":
    main()
