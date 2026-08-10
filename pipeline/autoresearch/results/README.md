# Autoresearch results

本目录是人机协同收口与模型基础证据的**汇总 SSOT 快照**。

## 读这个

1. `latest/RESULTS_SUMMARY.md` — 人类可读总览
2. `latest/RESULTS_SUMMARY.json` — 机器可读总览
3. `latest/evidence_index.csv` — 证据路径与声称级别
4. `trial_ledger.csv` — 历次汇总追加账本

## 重建

```bash
python3 scripts/build_autoresearch_results_summary.py
```

源数据仍以原路径为准（freeze JSON、Round2 exports、asset freeze、Agent acceptance）。本目录是汇总，不是第二套数字真相。
