# LDH 对标清单 — 胃癌 CEUS T 分期稿 vs ldh1/ldh2

> 更新：2026-06-12 (v2.4 修订 — reader study 2-arm 视频优先重设计)  
> 参考：`docs/references/ldh/ldh1.pdf`（SuRImage, LDH 2026;8:100965）  
> 参考：`docs/references/ldh/ldh2.pdf`（HCC ML, LDH 2026;8:100952）  
> 目标稿：`docs/paper_drafts/tex_v2_ldh/gastric_tstaging_paper_v2.tex`  
> 总逻辑入口：`docs/ldh_mainline/README.md`

## 总览评分（结构 × 内容丰富度）

| 维度 | ldh1 标杆 | ldh2 标杆 | v2.1 (2026-06-05) | v2.2 (2026-06-10) | v2.3 (2026-06-10 r2) | v2.4 (2026-06-12 r3) | 差距 |
|------|-----------|-----------|-------------------|-------------------|------------------------|----------------------|------|
| Summary 五段式 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Research in context | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Introduction 临床铺垫 | ~1200 词 | ~900 词 | ~690 词 | ~720 词 | ~470 词 (净化) | ~470 词 | 中 |
| Methods 子节完整度 | 6+ 子节 | 5+ 子节 | ✅ 6+ | ✅ 6+ | ✅ 6+ | ✅ 6+ | 小 |
| 队列流程图 (Fig1) | ✅ CONSORT | 数据流 | ✅ tikz in §Methods | ✅ tikz in S1 | ✅ tikz in S1 | ✅ tikz in S1 | — |
| 筛图 funnel figure | — | — | ❌ 无 | ❌ 无 | ✅ `fig:screening_funnel` (S1, 真实数字) | ✅ | 小 |
| 基线特征表 (Table1) | 20+ 行 + p | 15+ 行 | 仅 split | ✅ 14 行 + p | ✅ 14 行 + p | ✅ | 小 |
| 与临床金标准对照 | vs 冰冻 | vs 8 基准 | ✅ benchmark 表 | ✅ benchmark 表 | ✅ benchmark 表 | ✅ | 小 |
| Reader study | ✅ Fig4 | — | planned | planned | planned | ⚠️ 子集 + UI 完成，2-arm n=150 (Arm A 91 + Arm B 59)，3 reader 含 site PI Dr. Zhuo，a priori 80% power；待 reader 跑通拿数 | 中 (GAP G01) |
| Results 叙事长度 | ~2500 词 | ~2000 词 | ~790 词 | ~1100 词 | ~1063 词 | ~1063 词 | 中 |
| Discussion 长度 | ~2000 词 | ~1800 词 | ~730 词 | ~1500 词 | ~1143 词 | ~1143 词 | 小 |
| Limitations | 4–6 条 | 7 条 | 7 条 | 8 条 | 8 条 | 9 条 (+子集算法准确率警示) | 小 |
| Contributors | ✅ | ✅ | 占位 | 占位 | 占位 | 占位 | 中 (GAP G11) |
| Data sharing | ✅ 细则 | ✅ | ✅ | ✅ | ✅ | ✅ | 小 |
| Appendix | pp 2–23 | pp 14–28 | S1–S10 | S1–S10 + IRB list | S1–S10 + IRB list | S1–S10 + IRB list + §app:reader 重写 | 小 |
| 数字一致性 (SSOT 0.058/20%/5.1%/hypothetical 100-110) | — | — | ❌ (0.10/22%) | ✅ (0.058/20%) | ✅ + 5.1%/100-110 | ✅ | — |
| 引用完整性 (no fake) | — | — | ❌ 12 fake | ✅ 0 fake, 28 unique | ✅ 0 fake, 27 unique | ✅ 0 fake, 27 unique | — |
| Figure 编号连贯 | 6 fig | 5+ fig | ❌ 7 fig (tikz 算) | ✅ 6 fig + tikz in S1 | ✅ 6 fig + tikz in S1 | ✅ 6 fig + tikz in S1 | — |
| Introduction 临床语言纯度 (LDH 标杆) | ✅ | ✅ | ❌ 工程术语堆砌 | ⚠️ 残留 | ✅ 临床导向 | ✅ 临床导向 | — |

**v2.4 结论（2026-06-12 r3）**：G33 闭环 — Reader study 2-arm 视频优先重设计：子集 n=150 (Arm A 91 AI-clean + Arm B 59 AI-uncertain) 替换单臂设计；3 reader 含 site PI Dr. Zhuo (Fujian Med Univ Xiehe Hospital)；a priori 80% power 检 0.10 abs 提升 (α=0.05, ρ=0.5, baseline 0.65)；2-pass (no-AI / with-AI) 减 carry-over；极简阅片包 `apps/tstage_reader_study/` (4 选 1 T-stage + 0.25/0.5/1/2× 倍速 + scrubber) 替换原 5 选项 app。**主文 AI raw test-set 数字仍不报**（boss + 卓医生 微信 2026-06-12 共识：测试集 AI 太低，论文里不合适；先 AI 筛出相对不错的 150 例让人测）；子集算法准确率不直接代表全队列已在 §Limitations #3 明示。**剩余 P0 差距**仅 reader study 实测数据 + ChiCTR 真号 + Contributors/CRediT + Funding 真号。

---

## 逐节对标

### 1. 标题

| LDH 范式 | 当前稿 v2.1 | 状态 |
|----------|-------------|------|
| 方法 + 疾病 + 研究设计副标题 | GTstage + prospective multicentre diagnostic | ✅ |

### 2. Summary

| 段落 | 状态 |
|------|------|
| Background / Methods / Findings / Interpretation / Funding | ✅ |

### 3. Research in context

三要素（Evidence / Added value / Implications）→ ✅ v2.1

### 4. Methods 子节

| 子节 | v2.1 |
|------|------|
| Study design and participants | ✅ |
| Outcomes | ✅ |
| Statistical analysis | ✅ |
| Role of funding | ✅ |
| Reader study protocol | Appendix S10 planned |

### 5. Results 叙事顺序

| LDH 叙事块 | 当前稿 | 缺口 |
|------------|--------|------|
| 队列流程 | `fig:cohortflow` | — |
| 基线 Table | split only | age/sex/Lauren p 值 |
| vs 基准 | `tab:benchmark` | — |
| ROC | `fig:roc` | — |
| T2/T3 | `fig:t2t3` | — |
| 读者研究 | — | **planned** |
| Per-centre | `tab:percentre` | — |
| Grad-CAM / 混淆 | `fig:gradcam`, `fig:confusion` | — |

### 6. Discussion

| 段落 | v2.1 |
|------|------|
| first-in-field | ✅ |
| 按临床任务 | ✅ 4-class / T2T3 / T3T4 |
| vs 文献 / ldh1&2 平行 | ✅ |
| 部署路径 | ✅ |
| Strengths | ✅ 5 条 |
| Limitations | ✅ 7 条 |

---

## 内容诚实性红线

| 项目 | 状态 | 策略 |
|------|------|------|
| Reader study | ❌ | protocol + planned |
| Bootstrap CI | ⚠️ | Appendix 声明 |
| Ablation TBD | ⚠️ | 保持 TBD |
| ChiCTR | ❌ | 投稿前补 |

---

## 修订优先级

### P0 结构 — 已完成 v2.1
- [x] Research in context
- [x] Summary 五段
- [x] Methods 统计/结局/funding
- [x] benchmark 表、cohort flow、Contributors

### P1 数据
- [ ] Reader study（G01）
- [ ] 基线 Table（G02）
- [ ] ChiCTR（G03）
- [ ] Bootstrap 真跑（G04）

### P2 润色
- [ ] Discussion/Results 扩词
- [ ] Fig 编号与 reader 插入后重排
- [ ] refs DOI

---

## 持续对照工作流

见 [REVISION_LOOP.md](REVISION_LOOP.md)。每轮改稿后：

1. `python3 docs/ldh_mainline/scripts/check_ldh_alignment.py`
2. 更新本表总览评分
3. 更新 [GAP_TRACKER.md](GAP_TRACKER.md)
