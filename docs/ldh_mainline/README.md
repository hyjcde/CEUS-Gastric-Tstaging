# LDH 投稿总逻辑维护中心

> **本文件夹职责**：维护胃癌 CEUS T 分期 → *Lancet Digital Health* 投稿的**总逻辑**（叙事链、结构对标、差距追踪、改稿循环），不替代数据 SSOT 与 LaTeX 源稿。  
> 创建：2026-06-05

## 一句话定位

**临床问题（T2/T3 手术决策）→ 多中心前瞻诊断研究 → 外部+前瞻双验证 → 透明失败中心 → 读者研究（待做）**

工程细节（多智能体、late-fusion、ablation）降维为 Methods/Appendix，不得抢占 Introduction/Discussion 主轴。

---

## 文件索引

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| [MASTER_LOGIC.md](MASTER_LOGIC.md) | **总逻辑**：叙事主轴、章节职责、LDH 结构映射 | 改叙事/定稿前 |
| [LDH_BENCHMARK.md](LDH_BENCHMARK.md) | 与 ldh1/ldh2 逐节对标清单 | 每轮改稿后 |
| [GAP_TRACKER.md](GAP_TRACKER.md) | P0/P1 差距 живой 状态 | 每次闭环任务后 |
| [REVISION_LOOP.md](REVISION_LOOP.md) | 改稿对照 SOP（5 步） | 稳定，偶尔增补 |
| [SSOT_MAP.md](SSOT_MAP.md) | 数字/图/表 → 仓库路径一张图 | 数据冻结或 eval 变更时 |

---

## 与其他目录的关系

```
docs/ldh_mainline/          ← 你在这里：总逻辑 + LDH 对标 + 差距
    │
    ├── 手稿 LaTeX          → docs/paper_drafts/tex_v2_ldh/gastric_tstaging_paper_v2.tex
    ├── 审稿自检            → docs/paper_drafts/tex_v2_ldh/REVIEWER_SELF_CHECK.md
    ├── 数据/图表治理       → docs/paper_governance/（PAPER_INDEX, FIGURE_MANIFEST, …）
    ├── LDH 参考论文        → docs/references/ldh/（ldh1.pdf, ldh2.pdf, *.txt）
    ├── 主实验数字 SSOT     → docs/mainline/MAINLINE_FACTS_v2.md, experiment_index_v2.csv
    └── 数据 contract       → pipeline/data/tstaging_4class_screened_*/
```

**分工原则**

- `paper_governance/`：资产清单（哪张图、哪张表、哪次 run）
- `ldh_mainline/`：**为什么这样写、还缺什么、怎么对标 LDH**
- `tex_v2_ldh/`：可编译英文稿 + 图 + appendix

---

## 当前版本

| 项 | 值 |
|----|-----|
| 手稿版本 | v2.3（2026-06-10 4-agent 审核 round 2→统一修复：M1-M4 + P1 净化） |
| 标杆论文 | ldh1 SuRImage；ldh2 HCC ML |
| 主线模型 | 06-03 `acc_boost2` |
| 基线 | 04-23 frozen primary |
| 开放差距 | 见 [GAP_TRACKER.md](GAP_TRACKER.md) |

---

## 快速入口命令

```bash
# 读总逻辑
cat docs/ldh_mainline/MASTER_LOGIC.md

# 查差距
cat docs/ldh_mainline/GAP_TRACKER.md

# 改稿后跑对标（词数 + 引用）
python3 docs/ldh_mainline/scripts/check_ldh_alignment.py
```
