# SSOT_MAP — 论文数字 / 图 / 表 溯源一张图

> 任何 tex 中的数字必须能追到本表路径  
> 冻结日：train/val 2026-05-31 · external 2026-05-29 · mainline 2026-06-03

---

## 主终点数字

| 手稿中的数 | 队列 | 来源文件 |
|------------|------|----------|
| macro-AUC **0.8572** | test_external | `pipeline/experiments/tree/.../acc_boost2_.../eval/latest_screened_external_reeval/test_external/test_results.json` |
| macro-AUC **0.8655** | test_prospective | 同 run 下 `eval/test_prospective/test_results.json` |
| macro-AUC 0.7326 / 0.7455 | baseline 04-23 | `classification/dual_mask4ch/.../eval/.../test_results.json` |
| patient acc 0.72 / 0.63 | pro / ext | patient-level aggregation on 上述 JSON |
| T2 recall 0.548 (4-class) | prospective | 06-03 `test_results.json` per_class |
| T2 recall 0.094 | baseline pro | 04-23 `test_results.json` |
| T2 bdry recall 0.90 / 0.25 | T2/T3 2×2 | `test_predictions.csv` 边界子集 |
| **T2→T3 over-stage 0.058 (4-class frame-level) / 0.281 (baseline)** | 同上 | 04-23 pro 9/32 (T2→T3) over T2 truth 4-class; 06-03 pro 6/104 = 0.0577 |
| **4 中心 b-acc < 0.4 占 20% (495/2458 frames)** | external | `docs/mainline/per_source_external.md` |
| b-acc 0.6454 / 0.6886 | ext / pro | `test_results.json` |
| T4→T3 17.2% / T3→T4 18.1% of T truth | pro confusion | 06-03 pro row T4=149/868; row T3=68/375 |
| T2→T1 30.8% of T2 / T2→T2 54.8% | pro confusion | 06-03 pro row T2 32/104 + 57/104 |
| T1→T2 over-stage (T1→T2) | 0.051 (16/312 T1 frames, 5.1%) | 06-03 pro row T1 16/312 | `test_predictions.csv` 4×4 |
| Discussion hypothetical 算式 | 10% T2 prevalence + 0.65 boundary lift → ~100-110 additional T2 frames / 1,600 帧 | paper §Discussion (M2 重写) |
| tab:ci 真 95% CI | 2000-replicate patient-level bootstrap | `scripts/bootstrap_tstaging_ci.py` (committed); `pipeline/experiments/tree/.../eval/bootstrap_ci_2000.json` (audit raw) |
| 筛图 funnel 数字 | ext 2966→2458 (508, 17.1%) / pro 2430→1659 (771, 31.7%) | `pipeline/data/tstaging_4class_screened_latest_external_2966_20260529/test_external_with_reject_flag.csv` (ext) + `screened_build_summary.json` (pro) |

---

## 数据 contract

| 用途 | 路径 |
|------|------|
| 4-split 指针 | `pipeline/data/tstaging_4class_screened_eval_20260531/SPLIT_POINTERS.md` |
| external 9 中心 | `pipeline/data/tstaging_4class_screened_latest_external_2966_20260529/` |
| 临床 22 维 | `pipeline/clinical/feature_spec_v1.yaml` |
| 外部临床 CSV | `pipeline/data/.../test_external_clinical.csv` |

---

## 图表 → 文件

| 手稿 label | 文件 | 生成 |
|------------|------|------|
| `fig:cohortflow` | Appendix S1 tikz | v2.1 手写 |
| `fig:montage` | `tex_v2_ldh/figures/figure1_montage_centers.png` | make_figure1.sh |
| `fig:roc` | `figure2_mainline_roc.png` | eval JSON |
| `fig:t2t3` | `figure3_t2t3_boundary.png` | eval JSON |
| `fig:ablation` | `figure4_ablation_panel.png` | ablation_matrix.csv |
| `fig:gradcam` | `figure5_gradcam_representative.png` | 真实 Grad-CAM |
| `fig:confusion` | `figure6_confusion_panel.png` | test_results.json |
| `tab:cohort` | tex 内嵌 | SPLIT + 统计 |
| `tab:baseline` | tex 内嵌 | cross-cohort 临床特征 + p 值 |
| `tab:benchmark` | tex 内嵌 | 文献 + 本文 JSON |
| `tab:main` | tex 内嵌 | 04-23 vs 06-03 JSON |
| `tab:percentre` | tex 内嵌 | per_source_external |
| `tab:ablation` | tex 内嵌 | 6-axis 行 |
| `tab:ci` | Appendix S5 | ⚠️ bootstrap 待真跑 |

---

## 标杆论文（逻辑参照，非数据源）

| ID | 路径 |
|----|------|
| ldh1 SuRImage | `docs/references/ldh/ldh1.pdf` |
| ldh2 HCC ML | `docs/references/ldh/ldh2.pdf` |
| 提取文本 | `docs/references/ldh/ldh1.txt`, `ldh2.txt` |

---

## 已知 caveat（写入正文，不可删）

1. **04-23 vs 06-03 非同一 prospective split**（0 image_path overlap）→ model-family 对比
2. **Bootstrap CI 表为估计值** → Appendix S5 声明
3. **Ablation 部分行 TBD** → 进行中
4. **Reader study 无数字** → Appendix S10 planned
