# REVISION_LOOP — 每轮改稿 LDH 对照 SOP

> 触发：任何对 `gastric_tstaging_paper_v2.tex` 的实质性修改  
> 耗时：约 15–30 分钟/轮

---

## Step 0 — 改前确认

- [ ] 本轮改的是**叙事**还是**数字**还是**结构**？
- [ ] 若动数字：eval JSON 路径是否在 [SSOT_MAP.md](SSOT_MAP.md)？
- [ ] 若动结构：是否违背 [MASTER_LOGIC.md](MASTER_LOGIC.md) §3 章节职责？

---

## Step 1 — 读标杆片段（5 min）

```bash
# LDH 参考文本
sed -n '14,60p' docs/references/ldh/ldh1.txt    # Summary
sed -n '769,800p' docs/references/ldh/ldh1.txt   # Discussion 开篇
```

对照本轮修改的章节，问：

1. ldh1 该节**第一句**讲临床还是讲模型？
2. 是否有 **数字 + 95% CI + 对比对象**？
3. 是否有 **limitation / caveat** 同段出现？

---

## Step 2 — 跑自动检查（2 min）

```bash
python3 docs/ldh_mainline/scripts/check_ldh_alignment.py
```

记录：主文词数、各节词数、缺失 `\cite`、Summary 五段是否齐全。

---

## Step 3 — 手动五问（LDH 审稿人视角）

| # | 问题 | 通过标准 |
|---|------|----------|
| Q1 | Summary 能否独立读懂临床贡献？ | 不出现 acc_boost2、六智能体 |
| Q2 | Research in context 是否有检索式+空白？ | 三要素齐全 |
| Q3 | Results 是否按**临床任务**而非代码模块？ | T2/T3 有独立小节 |
| Q4 | 是否有**与临床/文献**的对照？ | benchmark 表或 reader |
| Q5 | 失败是否透明？ | 4 中心、TBD、split caveat |

---

## Step 4 — 更新治理文件

| 改了什么 | 更新哪个文件 |
|----------|--------------|
| 数字 | SSOT_MAP + REVIEWER_SELF_CHECK R4 |
| 结构/叙事 | MASTER_LOGIC 版本记录 |
| 新差距/关差距 | GAP_TRACKER |
| 对标评分 | LDH_BENCHMARK 总览表 |
| 图/表决策 | paper_governance/FIGURE_MANIFEST 或 TABLE_MANIFEST |

---

## Step 5 — 本轮记录（追加到 GAP_TRACKER 或 DECISION_LOG）

模板：

```markdown
### YYYY-MM-DD 改稿轮次 N
- 改动：<章节/文件>
- 对标参照：ldh1 §X / ldh2 §Y
- 关闭 GAP：G0X（如有）
- 新增 GAP：（如有）
- 下一轮优先：
```

---

## 词数目标（主文）

| 节 | 下限 | 目标 | ldh1 参考 |
|----|------|------|-----------|
| Summary | 200 | 280 | ~300 |
| Introduction | 500 | 800 | ~1200 |
| Methods | 800 | 1000 | ~1100 |
| Results | 1200 | 1800 | ~2500 |
| Discussion | 1000 | 1500 | ~2000 |
| **合计** | 3500 | 4200 | ~4500 |

Discussion/Results 仍低于标杆 → 优先扩写，不新增工程章节。
