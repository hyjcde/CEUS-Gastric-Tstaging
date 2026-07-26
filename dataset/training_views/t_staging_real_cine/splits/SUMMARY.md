# Real-cine supervised splits

Generated: 2026-07-26T16:33:24Z

## Use which table?

| 目的 | 读 |
|------|----|
| 跟历史 registry 一致 | `by_legacy_split/` |
| **汇报 / 泛化评测（推荐）** | `by_eval_role/` |
| 病人级软链 | `../by_split/<eval_role>/` |

## eval_role 规模（病人 / 样本）

| role | patients | samples |
|------|--------:|--------:|
| `test_external` | 58 | 245 |
| `test_external_newzip` | 132 | 486 |
| `test_internal_holdout` | 13 | 83 |
| `test_prospective` | 46 | 234 |
| `train` | 280 | 1537 |
| `val` | 28 | 146 |

- remapped from legacy: **59**（prospective/internal 误落在 test_external*）
- external 仍在 train/val（遗留，福建省肿瘤医院）: **41**
- patient_id 跨 eval_role 泄漏: **PASS**

## 训练建议

1. Fit：`by_eval_role/train` + `val`
2. 外推：`test_external` + `test_external_newzip`
3. 前瞻：`test_prospective`（含从 test_external 纠正的 46 人）
4. 内部 holdout：`test_internal_holdout`（勿并进 external 汇报）
5. 划分单位：**patient_id**
