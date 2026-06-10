# GAP_TRACKER — LDH 对标差距 живой 表

> 最后更新：2026-06-10  
> 规则：完成一项 → 改状态 + 在 MASTER_LOGIC 版本记录留痕

---

## 总览

| 类别 | 已完成 | 进行中 | 未开始 |
|------|--------|--------|--------|
| 结构对标 | 7 | 0 | 0 |
| 内容丰富度 | 7 | 1 | 1 |
| 数据/验证 | 2 | 1 | 2 |

**投稿就绪度（诚实估计）**：结构 ~92% · 内容 ~78% · 验证 ~50%

---

## P0 — 投稿前必须

| ID | 差距 | 对标 | 状态 | 负责动作 |
|----|------|------|------|----------|
| G01 | Reader study 实测数据 | ldh1 Fig4 | ❌ | 设计见 Appendix S10；执行多中心读者试验 |
| G02 | 基线特征 Table（跨队列 + p 值） | ldh1 Table1 | ✅ | `tab:baseline` 已加，age/sex/Lauren/location/Diff/CEA/CA19-9 14 行 + Kruskal/χ² p |
| G03 | ChiCTR 注册号 | ldh1 ChiCTR | ❌ | 占位保留，投稿前补 |
| G04 | Bootstrap 2000 真跑 | LDH CI 规范 | ⚠️ | `tab:ci` 仍为 median estimate，Appendix S5 已诚实声明 in progress |
| G05 | pdflatex 编译通过 | 投稿包 | ⚠️ | `which pdflatex` 空；本仓库不能编译；CI 容器待配 |
| G15 | 数字一致性（T2→T3 over-stage 0.10 vs 0.058） | 内部 SSOT | ✅ | 4-class 改 0.058；L75/L107/L285/L361/L376/F2 caption 全部一致 |
| G16 | "22% of external frames" → 20% | 内部算术 (495/2458) | ✅ | L75/L296/L359 全部改 20% |
| G17 | Failure mode 百分比 56%/26% 错 | 内部算术 | ✅ | 改 17.2%/65%（T4）/ 18.1%/55%（T3） |
| G18 | bibitem 重复 (gao/jiang) | IEEEtran | ✅ | L442/L445 重复已删 |
| G19 | 12 fake 风险 2026 cite | Crossref | ✅ | liv/mccradden23/liu26/wang26/chen26/khan26/tanaka26/kumar26/smith26/podina26/kaida26/lai26 全部删除 |
| G20 | 14 unused bibitem | IEEEtran | ✅ | buisson22/soltan22/balestrucci26 全部删除 |
| G21 | fig:cohortflow 编号 vs 6 fig 冲突 | LDH 编号 | ✅ | cohort flow tikz 移到 Appendix S1；主文 6 fig (montage→confusion) 编号对齐 |
| G22 | Figure 5 gradcam caption 缺 (e) | 图实有 5 case | ✅ | caption 补 (e) T4+ correctly classified |
| G23 | Appendix S8 缺 IRB list | ldh1 IRB 中心+号 | ✅ | 加 10 中心 IRB 编号段 |

---

## P1 — 强烈建议

| ID | 差距 | 状态 | 动作 |
|----|------|------|------|
| G06 | Discussion 词数 ~730 vs ldh1 ~2000 | ✅ | 扩到 ~1500 词（4-class/T2T3/Multi-agent/Deployment/Comparison 5 段 + Strengths + 8 Limitations） |
| G07 | Results 词数 ~790 vs ldh1 ~2500 | ⚠️ | 加了 `tab:baseline` 段；其余小节扩写余地有；next iteration 目标 1500 词 |
| G08 | Fig 编号与 LDH 叙事顺序 | ✅ | 6 fig (montage→confusion) 与 LDH 一致；cohort flow 在 S1 |
| G09 | refs 补 DOI | ✅ | 全部 bibitem 补卷/期/pages；A 类 4 条 + B 类 8 条 DOI 全部补 |
| G10 | PPI 患者代表 disclaimer | ✅ | Limitations #8 + Methods 末段加 "planned engagement" 说明 |
| G24 | Sounderajah 期刊错（LDH→Nat Med） | Crossref | ✅ bibitem 改 Nat. Med. 2025;31(10):3283-9 |
| G25 | Liu2020claim 错引（Nat Med→Radiol AI） | Crossref | ✅ 改 Mongan/Moy/Kahn 2020 Radiology AI |
| G26 | Zheng2025 interpretable 错引（Abdom Radiol→npj DM） | Crossref | ✅ 改 npj Digit. Med. 8:624 (2025) |
| G27 | Isensee 年份错（2021→2020） | Crossref | ✅ 改 Nat. Methods 18(2):203-211 (2020) |

---

## P2 — 润色

| ID | 差距 | 状态 |
|----|------|------|
| G11 | Contributors 占位 → 真名 CRediT | ❌ 占位保留 |
| G12 | Funding 占位 → 真基金号 | ❌ 占位保留 |
| G13 | Ablation TBD 行填实或删 | ⚠️ TBD 保留 (待下个 iteration 跑) |
| G14 | 3 个 dangling PNG | ✅ 已移到 `_build/` 归档 |

---

## 已完成（v2.2 — 2026-06-10）

- [x] Summary 五段 + Funding 占位
- [x] Research in context 三要素框
- [x] 标题含 prospective multicentre diagnostic study
- [x] 队列流程图 `fig:cohortflow`（在 Appendix S1）
- [x] Table benchmark vs EUS/CEUS/CT 文献
- [x] Table baseline 跨队列 14 行 + p 值
- [x] Methods: Outcomes + Statistical analysis + Role of funding + IRB list
- [x] Discussion 扩到 1500+ 词 + strengths + 8 limitations
- [x] Contributors / Data sharing 模板
- [x] Appendix S10 reader study planned
- [x] LDH 参考论文入库 `docs/references/ldh/`
- [x] 28 unique bibitem（A 类 4 + B 类 8 + 真实 cite 16）+ 期刊/年份/DOI 全部修正
- [x] 数字一致性 0.058/0.281 over-stage 4 处一致
- [x] 20% (495/2458) 4 中心 帧占比 3 处一致
- [x] 3 个 dangling PNG 归档到 `_build/`
- [x] 6 fig (montage→confusion) 与 LDH 顺序对齐
- [x] fig:gradcam (e) 补全

---

## 关闭差距时的检查项

每关闭一条 GAP，必须同时：

1. 改 `gastric_tstaging_paper_v2.tex`
2. 更新本表状态
3. 若涉及数字 → 更新 `SSOT_MAP.md` + `REVIEWER_SELF_CHECK.md` R4
4. 若涉及结构 → 更新 `LDH_BENCHMARK.md` 总览评分
