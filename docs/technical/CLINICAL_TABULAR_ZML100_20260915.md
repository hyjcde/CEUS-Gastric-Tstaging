# 纯临床表格 T 分期 benchmark：zml100 阅片测试集

日期：2026-09-15
关联：[DINOV3_US_SSL_RESULTS_20260914.md](DINOV3_US_SSL_RESULTS_20260914.md)（影像模型 §6.5 每类分析）；zml100 测试集 `pipeline/data/zml_reader_100_testset_20260915/`

## 0. 一句话

**纯临床表格（11 个常规临床变量）在干净评测集上反超影像模型**：外部集 RF ACC 0.617 vs 影像 0.433，zml100 严格子集 0.69 vs 0.46–0.49、医生 0.54。但**肿瘤长径/厚径两个字段贡献巨大且来源待核实**（若源自病理报告则属特征级泄漏）；剔除后临床模型仍不劣于影像模型。最佳模型类型是**树集成（RF/XGB/LGBM）**；TabPFN v2.5 不是第一（ACC 中游，但外部集 QWK 最高）。

## 1. 设置

- **特征**（患者级，沿用 clin11 约定 + 缺失指示位）：
  - `clin11`（22 列）：age / sex / Lauren / 分化程度 / 肿瘤长径 / 厚径 / 部位 / CEA（值+二值）/ CA199（值+二值）的 `_norm` + `_missing`
  - `clin9_safe`（18 列）：剔除肿瘤长径/厚径——该两字段若来自病理报告则与 pT 直接相关，属泄漏；来源核实前以本变体为保守口径
- **训练池**：`region_contrastive_full` train+val，患者级去重后 **1,566 例**（T1 352 / T2 195 / T3 522 / T4+ 497）
- **评测集与泄漏审计**：
  | 集合 | n | 与训练池患者重叠 | 口径 |
  |---|---:|---:|---|
  | zml100_full | 76/100（有临床记录者） | 37 例 | 含记忆成分，仅作上界参考 |
  | zml100_strict | 39 | 0 | **干净**但样本小 |
  | prospective_full | 506 | **167 例**（训练池本身含 int/prospective 源） | 有污染，仅参考 |
  | external | 381 | 0 | **干净大样本，主读数** |
- 模型 11 个：prior 基线 / logreg / SVM-RBF / kNN15 / MLP-128×2 / RF / ExtraTrees / HistGB / XGBoost / LightGBM / **TabPFN v2.5**（本地缓存权重，`create_default_for_version`；v8 新权重需 license 未用）。类别不平衡用 class_weight/样本权重处理。
- 脚本：`scripts/bench_clinical_tabular_zml100_20260915.py`；产物 `pipeline/experiments/reports/clinical_tabular_zml100_20260915/`

## 2. 结果

### 2.1 zml100（病例级 ACC / QWK / macro-AUC）

**strict（n=39，无泄漏，主读数）**

| 模型 | 特征 | ACC | QWK | AUC |
|---|---|---:|---:|---:|
| logreg | clin9_safe | **0.692** | 0.488 | **0.849** |
| xgboost | clin11 | **0.692** | 0.387 | 0.798 |
| tabpfn_v25 | clin11 | 0.667 | 0.528 | 0.788 |
| svm_rbf | clin11 | 0.667 | 0.546 | 0.771 |
| random_forest | clin11 | 0.667 | 0.522 | 0.824 |
| lightgbm | clin11 | 0.667 | 0.523 | 0.756 |
| mlp_128x2 | clin9_safe | 0.667 | 0.598 | 0.766 |
| prior_majority | — | 0.308 | 0 | 0.5 |

**full（n=76，含 37 例训练池重叠，上界参考）**：RF/XGB/LGBM clin11 均 **0.829**（QWK 0.73–0.81，AUC 0.90–0.94）；TabPFN clin11 0.711。

### 2.2 external（n=381，干净大样本，主读数）

| 模型 | 特征 | ACC | QWK | AUC |
|---|---|---:|---:|---:|
| random_forest | clin11 | **0.617** | 0.689 | 0.795 |
| tabpfn_v25 | clin11 | 0.585 | **0.721** | **0.827** |
| mlp_128x2 | clin11 | 0.583 | 0.651 | 0.802 |
| extra_trees | clin11 | 0.580 | 0.665 | 0.773 |
| xgboost | clin11 | 0.564 | 0.686 | 0.805 |
| random_forest | clin9_safe | 0.480 | 0.369 | 0.653 |
| prior_majority | — | 0.378 | 0 | 0.5 |

### 2.3 prospective_full（n=506，167 例与训练池重叠，仅参考）

RF clin11 ACC 0.668 / QWK 0.490 / AUC 0.812；ET 0.646；LGBM 0.644；TabPFN 0.542。

### 2.4 同病例对照（医生 + 影像模型）

| 对象 | zml100@covered76 | zml100@strict39 |
|---|---:|---:|
| 医生 zml | 0.474 | 0.538 |
| 影像-官方 | 0.487 | 0.462 |
| 影像-激进 | 0.434 | 0.487 |
| 影像-温和 | 0.329 | 0.308 |
| **临床-RF/XGB（clin11）** | **0.829** | **0.667–0.692** |

## 3. 判读

1. **临床表格单独就有真实信号，且在干净集上超过影像单模态**。external（n=381，零泄漏）RF clin11 ACC 0.617 vs 影像官方 0.433；zml100 strict 0.67–0.69 vs 影像 0.46–0.49、医生 0.54。
2. **肿瘤长径/厚径是最大的单一信息源**：external 上剔除后 RF 从 0.617 → 0.480。**字段来源已核实（2026-09-15 晚，见 §5）——为术前超声测量值，非病理**，clin11 数字成立；但分化程度/Lauren 解析自病理文本，严格溯源场景可用 clin9_safe 作保守口径（external 0.480，仍略高于影像 0.433）。
3. **最佳模型类型 = 树集成**（RF/XGB/LGBM 互有胜负，整体第一梯队）。符合预期：n≈1.5k、22 维、含缺失指示与非线性交互（大小×部位×标志物）的表格数据正是 GBM/RF 的优势区。**TabPFN 不是第一**：ACC 中游（strict 0.667 / external 0.585），但 external QWK 0.721 全场最高——它的概率排序质量好，适合做对序敏感的融合成员而非单模型答案。
4. **T2 塌陷在临床模态下依旧**（external RF clin11 的 T2 recall 0.18；zml strict XGB 的 T2 recall 0）——T2 信号不在常规临床变量里，也不会从影像单帧里来，这是任务本身的天花板。唯一例外是 strict 子集上 logreg clin9_safe T2 recall 0.67，但 n=39（T2 仅数例），不足为据。
5. **提升路径明确指向融合**：临床（尤其大小+标志物）与影像（壁层次/纹理）信息互补——8 月的 TabPFN 融合曾到 acc80 档（`run_tabpfn25_fusion_acc80_20260820.py`）。建议：① ~~核实 size 字段来源~~（已核实，§5：术前超声测值，合法）；② 在干净划分上重做「影像 prob + clin11」融合（严格患者级去重）；③ 补齐 zml100 剩余 24 例临床记录后复测；④ 增设 clin7_strict 变体（再剔除病理来源的分化/Lauren）复核稳健性。

## 4. 产物

- 结果表：`clinical_tabular_benchmark_results.csv`（11 模型 × 2 特征 × 4 集合）
- 汇总：`clinical_tabular_benchmark_summary.json`
- zml100 逐例预测：`zml100_preds_<features>_<model>_<set>.csv`

## 5. 字段来源核实（2026-09-15 晚，工作站原始工作簿）

注册表 `dataset/tables/clinical_table_registry.csv`（6,585 行）按队列回溯到三个原始工作簿，表头与数值证据如下：

| 队列 | 原始工作簿 | 长径覆盖 |
|---|---|---:|
| internal_training | `data/clinical_tables_check_20260814/01_协和胃癌/2018直接手术.xlsx` | 97% |
| internal_prospective | 同目录 `2025胃癌直接手术.xlsx`（首列=**超声检查时间**） | 61% |
| external_test | `data/raw/legacy_external_direct_surgery/直接手术图片/三明市第二医院/三明胃癌临床资料.xlsx` | 82% |

证据链：

1. 三个工作簿为同一 CRF 模板，长径/厚径列名仅「长径：cm / 厚径：cm」，与「病理」列**并列独立**；
2. 2025 工作簿以「超声检查时间」为首列——表格围绕超声检查建立，长径/厚径为**超声测值**；
3. 数值证伪病理来源：167 行可同时解析病理文本中的「大小 X×Y cm」与长径——两者均值差 **+0.49cm**（超声偏大，符合超声含壁厚测量），完全一致的仅 **4.2%**。若为病理抄录应 ~100% 一致。

**结论**：肿瘤长径/厚径 = 术前充盈超声测量值，可合法用于术前 T 分期预测，clin11 结果成立。
**残留注意**：分化程度 / Lauren 分型解析自「病理」列文本（术后病理）；临床上术前活检可获得同名变量，但严格溯源时建议以 clin9_safe（再去掉这两个字段需另设变体，当前 clin9_safe 仅去大小）或后续增设 clin7_strict 变体复核。

## 6. 扩展模型池与冠军遴选（2026-09-15 晚，v2）

加测 6 类（脚本 `scripts/bench_clinical_tabular_v2_20260915.py`，产物 `clinical_tabular_benchmark_v2_results.csv`）：

- **CatBoost**、**Optuna 调参** RF/XGB/LGBM（30 trials，训练池 5 折患者级 CV，QWK 目标）
- **序数模型**：ridge-round、累积二分类 logreg 分解（T 分期是有序变量，理论上 QWK 受益）
- **软投票**：RF+XGB+LGBM+TabPFN 概率平均
- **影像+临床融合**：官方影像模型病例级 4 类概率 + 临床特征 → logreg/RF/LGBM 融合头（val n=127 上训练）

要点（clin11 口径）：

| 模型 | external ACC | external QWK | zml strict ACC |
|---|---:|---:|---:|
| softvote | 0.609 | 0.689 | 0.692 |
| **rf_tuned** | 0.593 | **0.707** | **0.744** |
| catboost | 0.593 | 0.702 | 0.692 |
| （v1 默认 RF，对照） | **0.617** | 0.683 | 0.667 |
| ordinal_logreg | 0.512 | 0.589 | 0.641 |
| fusion_rf（+影像 prob） | 0.599（n=172） | 0.660 | 0.590 |

1. **调参 RF 在 strict 上明显最好（0.744）且 external QWK 最高（0.707）**；调参 XGB/LGBM 与默认档持平。
2. **序数模型不占优**——类别间边界信号弱时，序数假设帮不上忙。
3. **融合暂未增益**：影像 prob 太弱（单模态 0.43）且融合头只有 127 例训练样本，external 上 0.599 ≤ 纯临床 0.617。§3 第 5 条②已完成，结论为「暂不融合」。8 月 acc80 档的融合是在有泄漏的划分上取得的，不可比。
4. 冠军遴选（预注册标准：external + zml strict 平均 QWK 优先、平均 ACC 决胜；脚本 `scripts/select_champion_clinical_20260915.py`，结果 `champion_selection_20260915.csv`）：clin11 口径 **rf_tuned** 胜（clean QWK 0.6814 / clean ACC 0.6684）。

## 7. 公网工作台后端模型更新（2026-09-15 晚已上线）

**部署口径 clin9_wb** = clin11 去掉 Lauren/分化程度。原因：工作台结构化临床记录永远没有这两个字段（只在病理文本里），**训练特征必须与推理时可用性一致**，否则分布偏移。

- 冠军：**rf_tuned**（n_est=456 / depth=6 / min_leaf=4 / max_feat=0.533，clin9_wb 重调参）：external 0.567、zml strict 0.641、prospective 0.585、clean QWK 0.631。仍高于影像单模态（0.433/0.462）。
- **编码规则精确反推并自检通过**（max diff 1e-15）：连续 = z-score（mean/std 与生产 `clinical_norm_stats.json` 完全一致）；类别 = raw/max_code；缺失 → norm 0 + flag 1。部位用注册表口径（0=贲门+胃底 / 1=胃体+胃角 / 2=胃窦+幽门 / 3=多部位）——注意 `clinical_vector.py` 的旧四分编码（cardia/fundus/body/antrum）与此不同，勿混用。
- 产物：`pipeline/models/clinical_tstage_champion_20260915/`（model.joblib 4.2MB + transform.json + meta.json）。
- 接入：新增 `pipeline/agent/tools/clinical_ml_tool.py`（工作台病例 → 18 维特征 → 4 类概率；<4 字段时静默不可用）；`analyze_case_lib.py::_build_rule_based_report` 融合点——ML 概率以**与影像分类器等权**进入 scores，T4+ 安全门（无浆膜证据不显示 T4+）保持不变。
- 链路：公网 Next → SSH 隧道 → 工作站 `gastric-next-public`（:3300）→ 每请求 spawn 研究仓 `analyze_case.py` → **改动即时生效，无需重启服务**。阿里云侧副本经 `deploy_public.sh` 同步（休眠兜底），公网 `/workbench/api/version` = `local-20260915-1834`。
- 验证：工具冒烟 3 例（大肿瘤+高标志物 → T4+ 0.65，合理；字段不足 → 静默跳过）；融合报告冒烟（ML 证据行出现，T4+ 门正常回落 T3）。
- 后续：① 若在工作台侧解析病理文本补 Lauren/分化，可升级 clin11 口径（clean QWK 0.681）；② 补齐 zml100 剩余 24 例临床记录后复测；③ 融合等影像 backbone 变强（Deblur-MAE probe 见 `DMAE_US_SSL_20260915.md`）后再评估。
