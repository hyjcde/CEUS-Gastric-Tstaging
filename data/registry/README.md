# 数据注册表说明

本目录保存进入正式实验前必须维护的表格。

## 机器可读登记（由脚本生成）

```bash
python scripts/build_dataset_registry.py
```

产出：

- `dataset_registry.csv` — 数据集与 split 角色
- `patient_registry.csv` — 各 split 的 `patient_id` 计数
- `patient_media_sample_index.csv` — 样本级图片+视频索引
- `patient_media_registry.csv` — 患者级图片+视频主表
- `patient_media_registry_summary.json` — 构建统计
- `patient_split_leakage_report.json` — 患者级 split 泄漏检查
- `data/metadata/data_sources_inventory.csv` — zip / 临床表来源清单

患者级图片+视频 registry：

```bash
python scripts/build_patient_media_registry.py
python scripts/export_patient_media_splits.py
python scripts/verify_patient_split_leakage.py
```

训练导出目录：`pipeline/data/patient_media_tstaging_v1/`

## Split 指针（冻结）

见 [SPLIT_POINTERS.md](SPLIT_POINTERS.md)。

## 模板（参考）

- `dataset_registry_template.csv`
- `split_manifest_template.csv`

## 人机协同 Round2 冻结表（2026-08-10）

| 文件 | 含义 |
|------|------|
| `reader_round2_study_freeze_20260810.json` | 研究冻结契约（版本、命名空间、洗脱、主分析集） |
| `reader_round2_ai_assisted_manifest.csv` | 同医生同病例配对清单 |
| `reader_round2_case_order_20260810.csv` | Round2 呈现顺序（seed `20260810`） |
| `reader_expertise_registry_20260810.csv` | 医生资历登记（揭盲前；当前多为 pending） |
| `reader_early_subset_profiles_20260810.csv` | 早期 100 例子集 profile；不得自动映射 Doctor_XX |

重建：

```bash
python3 scripts/build_reader_round2_freeze_tables.py
python3 scripts/export_reader_round2_paired_tables.py
python3 scripts/validate_reader_round2_gate.py --allow-prepared
python3 scripts/analyze_reader_round2_expertise_uplift.py
```

导出与门控产物：`docs/clinical_validation/reader_round2_exports/`。
临床 AI-assisted 结论在 `clinical_claims_allowed=false` 时禁止写入主文。

正式 `research` 队列由 Next 服务端根据认证反向代理身份应用
`reader_round2_case_order_20260810.csv` 的 `presentation_index`。身份使用
`x-authenticated-reader-id` 加 HMAC 签名，不能通过 URL 的 `reader_id` 伪造。
