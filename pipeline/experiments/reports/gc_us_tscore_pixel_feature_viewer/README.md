# GC-US T-score 特征包本地镜像（2026-08-03）

从工作站 `ssh ws` 整包拉取，对应报告：

`/data/research/gastric/GastricTstaging/pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/index.html`

本地入口：打开 `reports/gc_us_tscore_feature_stats_v1/index.html`（中文）或 `index_en.html`。

---

## 目录

| 路径 | 内容 |
|------|------|
| `reports/gc_us_tscore_feature_stats_v1/` | 主报告 HTML + 全部图/表（~90MB） |
| `reports/tscore_*` | 离散积分草案、全队列图、A5 review、更深分析 |
| `data/gc_us_tscore_features_v1/` | 原始分通道特征 + `feature_pack_v1/patient_features.csv` |
| `data/gc_us_tscore_features_v2/` | G17 形态三元组 v2 重算 |
| `scripts/` | 提取 / 打包 / 建模 / 出图全部 Python（48 个） |
| `apps/gastric_scan_next/lib/gc-us-tscore.ts` | 面向医生的离散 GC-US T-score 打分实现 |
| `docs/` | 算法说明、会议路线、文献算法笔记 |
| `pixel_feature_viewer/index.html` | 像素级可视化：mask、轮廓、NRL、曲率、soft-band、局部梯度 |

工作站源根：`/data/research/gastric/GastricTstaging/`

---

## 结果在说什么（方法取舍）

N≈2170 患者级特征包（train 1219 / external 456 / prosp 254 / val 135 / holdout 106）。病理 T 是 GT；胃壁字段全是软代理，不是组织学 L1–L5。

### 1. 特征怎么来（算法链）

单帧 → 分通道计算 → 患者聚合（median / max / P90 / frac_high）→ 与临床表合并。

| 通道 | 核心库 / 脚本 | 方法要点 |
|------|----------------|----------|
| morphology | `gc_us_contour_features.py` + `extract_gc_us_morphology_features_v1.py` | 最大轮廓 → NRL(256) → 平滑 → roughness / Fourier；峰锐度、solidity、circularity |
| margin | 同上 + `extract_gc_us_margin_features_v1.py` | soft-band + BoF 圆周频谱 + 强平滑形状；`margin_spic_robust` |
| growth | `extract_gc_us_growth_features_v1.py` | lumen SDF 外向深度、外凸比；优先 `__max`/`__p90` |
| wall v1 | `gc_us_wall_layer_features.py` + `extract_gc_us_wall_layer_features_v1.py` | lumen SDF / 壁厚归一化 depth_frac、浆膜中断覆盖 |
| wall v2 | `extract_gc_us_wall_layer_axis_v2.py` | 合成浆膜 + 深部 sector ContactGeom 风格代理 |
| dynamics | `extract_gc_us_multiframe_dynamics_v1.py` | frac_high / frac_low / `dyn_invasion_agree` |
| pack | `build_gc_us_tscore_feature_pack_v1.py` | 拼成建模用 37 字段患者表 |

详细公式见报告第二节「每个特征怎么算」，以及 `docs/CCUS_T_征象积分算法说明_v1.md`。

### 2. 建模怎么做（报告主结论）

- **主任务**：T3+ vs T1–T2（AUC）；辅任务四分类 QWK。
- **基线很强**：临床长径 alone 外部 AUC ≈ **0.934**；形状 alone 外部只有 ~0.70。
- **推荐建模入口**：`size / length` 作主轴 + 形态/边界 core 作补充；全 pack 或厨房水槽并不稳赢长度。
- **LASSO（train-fit）**：非零项以 `size_max_diameter_cm`、`seg_short_axis_ratio`、`dyn_invasion_agree`、厚/长比、`bt_v2_max_outward_depth` 为主；完整队列 prosp AUC 会掉，complete-case 后更稳。
- **3D 三元组**：G17 形态三元组（peak sharpness / solidity / spic）+ 若干 size×CEA×形态组合，用于可视化与论文图，不是最终 staging 模型。

### 3. 产品侧打分（另一条线）

`gc-us-tscore.ts` 是 **ACR 风格离散积分**（长径/厚度/不规则度/短轴比/CEA/壁层软分）→ 总分映射 cT1–cT4b。  
它吃的是特征抽取结果，但**不是**上面 LASSO 连续概率模型。两条线要分清：

1. **研究/特征证据**：本报告 + feature pack + Python 提取器  
2. **临床展示积分**：`gc-us-tscore.ts` + `tscore_discrete_draft_v1`

---

## 若要「接着做」建议路径

1. 先读 `reports/gc_us_tscore_feature_stats_v1/index.html`  
2. 算法细节跟 `scripts/gc_us_contour_features.py`、`gc_us_wall_layer_features.py`  
3. 患者表：`data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv`  
4. 建模对照：`reports/.../feature_pack_models_v1/SUMMARY.md`、`full_split_v1/SUMMARY.md`、`lasso_latest_v1/SUMMARY.md`  
5. 医生端积分：`apps/gastric_scan_next/lib/gc-us-tscore.ts`
6. 像素级算法核查：`pixel_feature_viewer/index.html`（也可从 `docs/plans/ccus_t_scoring/GC_US_像素特征可视化.html` 打开）

重建 feature pack（需完整工作站数据树）：

```bash
python3 scripts/build_gc_us_tscore_feature_pack_v1.py
```


## 2026-08-03 更新：3D 按提分期解读

- 主表改为病理分期关联：T3+ AUC / Δ vs 长径 / QWK / 相邻期 AUC；KMeans ARI 仅对照。
- 新增 `reports/.../lasso_latest_v1/triplet_stage_metrics.csv` 与中文详解。
- 重建：`python3 scripts/compute_gc_us_triplet_stage_metrics_v1.py` → `python3 scripts/build_gc_us_tscore_results_html_zh_v1.py`
