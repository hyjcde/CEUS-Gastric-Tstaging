# pipeline/autoresearch

Autoresearch 结果与试验账本工作区。

> 当前阶段：已冻结的主线证据 + 人机协同收口脚手架汇总到 `results/`。  
> 新增离线主循环 `main_loop.py`（proposer / trainer stub / evaluator / reflector），**不得**写入临床 Agent active memory，也不得改冻结 mainline checkpoint。

## 目录

```text
pipeline/autoresearch/
  README.md                 # 本文件
  main_loop.py              # 离线预算约束主循环（默认 dry-run）
  results/
    README.md
    trial_ledger.csv        # 追加式汇总记录
    latest/                 # 最新汇总快照
    offline_loop/           # main_loop 产物
    YYYYMMDD/               # 带日期的快照
```

## 离线主循环

```bash
python3 pipeline/autoresearch/main_loop.py --max-trials 5 --dry-run
```

硬预算：最多 30 trial，每 trial 最多 2 epoch；warm-start 自冻结 `acc_boost2`，不改原 run。

## 重建最新汇总

```bash
python3 scripts/build_autoresearch_results_summary.py
```

读入口：

- `pipeline/autoresearch/results/latest/RESULTS_SUMMARY.md`
- `pipeline/autoresearch/results/latest/RESULTS_SUMMARY.json`

## 声称规则

| 可写进汇总主结论 | 不可写（门控未过） |
|------------------|--------------------|
| Round1 无 AI 医生基线 | AI-assisted 准确率提升 |
| acc_boost2 / Phase 0 分表模型基础 | 低年资+AI 超过高年资无 AI |
| Agent 20+20 offline 验收 | 报告质量改善 / 医生间变异缩小 |
| Round2 freeze / scaffold / gate 状态 | 用离线 v150 AI 0.57 替代医生 Round2 |
| 离线 autoresearch dry-run 账本 | 把 dry-run 伪指标写成真实训练提升 |

`clinical_claims_allowed` 以 `results/latest/round2_gate_status.json` 为准。
