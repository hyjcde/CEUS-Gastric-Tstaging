# MASTER_LOGIC — LDH 投稿总逻辑

> 读者：写稿人、审稿自检、协作 agent  
> 原则：**临床决策叙事优先，工程叙事降级**

---

## 1. 核心临床命题（一句话）

术前 CEUS 能否在**多中心、前瞻、外部验证**条件下，可靠区分胃癌 T 分期，尤其是 **T2 vs T3**，从而减少不必要的根治术或漏诊需扩大切除的 T3？

---

## 2. 叙事主轴（对标 ldh1 SuRImage）

| 层级 | SuRImage（ldh1） | 本研究（GTstage） |
|------|------------------|-----------------|
| 临床时刻 | 术中切缘 → 手术范围 | **术前 CEUS** → 手术规划 |
| 金标准 | 冰冻切片 | 术后病理 T 分期 |
| 采集方式 | 手机拍手术切面 | 常规 CEUS + 口服造影 |
| 决策痛点 | 亚肺叶 vs 肺叶 | ESD/有限切除 vs 根治术 |
| 最关键边界 | 侵袭性识别 / IASLC 分级 | **T2/T3（浆膜下层）** |
| 验证层次 | 内开发 + 2 外部 + **读者研究** | 内前瞻 + 9 外部 + **读者研究（planned）** |
| 诚实报告 | vs 冰冻、ambiguous 率 | vs 文献基准、4 中心 b-acc<0.4 |

**禁止的主轴**：多智能体框架、late-fusion 模块数、Kanban 工作流——这些只能支撑 Methods，不能开篇。

---

## 3. 章节职责（每节只回答一个问题）

| 章节 | 必须回答的问题 | 禁止写什么 |
|------|----------------|------------|
| **Summary** | 为何做、怎么做、主要数字、临床意义、基金 | 模块名堆砌、TBD 指标 |
| **Research in context** | 既往缺什么、本文加什么、对领域意味着什么 | 无检索式的空泛声明 |
| **Introduction** | 指南→现有影像局限→T2/T3 难点→假设→贡献 | 双分支 ConvNeXt 细节 |
| **Methods** | 设计、入排、结局、模型概要、统计、伦理 | 逐行训练命令（→ Appendix） |
| **Results** | 队列→主指标→边界→多中心→失败模式 | 按代码模块而非临床任务 |
| **Discussion** | 逐临床任务解读、vs 文献、部署、strengths、limitations | 重复 Results 数字表 |
| **Conclusions** | 3–4 句可引用结论 | 新数据 |

---

## 4. LDH 结构模板（固定顺序）

```
Title（含 study design 副标题）
Summary
  Background → Methods → Findings → Interpretation → Funding
Introduction
  [Research in context 框]
  临床背景 → 现有方法 → 假设 → 贡献
Methods
  Study design and participants
  Outcomes
  Model development（概要）
  Statistical analysis
  Role of funding source
  Reporting / PPI（可合并子节）
Results（按临床任务，非按模型）
  1. Cohort + 流程图
  2. vs 文献/临床基准
  3. 主指标（AUC、patient-level）
  4. T2/T3 boundary
  5. Per-centre（含失败中心）
  6. 消融 / 失败模式 / Grad-CAM
  7. [读者研究 — 有数据后插入]
Discussion
  first-in-field → 按任务 → vs 文献 → 部署 → strengths → limitations
Conclusions
Contributors / Data sharing / COI / Acknowledgements
References
Appendix
```

当前稿映射见 [LDH_BENCHMARK.md](LDH_BENCHMARK.md) §6–§8。

---

## 5. 数字叙事链（投稿时每条必须可追溯）

```
临床命题
  └─ 主终点：macro-AUC external 0.8572 / prospective 0.8655
       ├─ 来源：06-03 acc_boost2 eval JSON
       ├─ 对比：04-23 baseline + Table benchmark（文献）
       └─ CI：bootstrap patient-level（待真跑）

决策边界
  └─ T2/T3 subset：T2 recall 0.25→0.90；T2→T3 over-stage 0.281→0.10
       ├─ 来源：test_predictions.csv 2×2
       └─ caveat：非同一 held-out split（model-family 对比）

泛化诚实性
  └─ 4/9 外部中心 b-acc < 0.4（22% 帧）
       └─ 来源：per_source_external / Table per-centre

待补（不可编造）
  └─ Reader study：sonographer ± GTstage
  └─ 基线 Table：跨队列 age/sex/Lauren p 值
```

路径详情：[SSOT_MAP.md](SSOT_MAP.md)

---

## 6. 图表叙事逻辑（LDH 顺序 vs 当前编号）

| 叙事顺序 | 内容 | 当前 tex label | 状态 |
|----------|------|----------------|------|
| 1 | 队列流程 | `fig:cohortflow` | ✅ v2.1 |
| 2 | 多中心图像变异 montage | `fig:montage` | ✅ |
| 3 | ROC 主结果 | `fig:roc` | ✅ |
| 4 | T2/T3 boundary | `fig:t2t3` | ✅ |
| 5 | 读者研究 | — | ❌ planned |
| 6 | 消融 | `fig:ablation` | ⚠️ 部分 TBD |
| 7 | Grad-CAM | `fig:gradcam` | ✅ |
| 8 | 全混淆 | `fig:confusion` | ✅ |

**投稿前建议**：读者研究完成后，将 reader figure 插入 Results 第 5 位，ablation 后移。

---

## 7. 对标论文选用逻辑

| 参考 | 学什么 | 不学什么 |
|------|--------|----------|
| **ldh1 SuRImage** | 诊断研究设计、vs 金标准、读者研究、Task 式 Discussion | 术中图像、三任务分级 |
| **ldh2 HCC ML** | 集成方法、多基准对比、诚实报告未超越项 | 生存预测、回顾队列 |
| **gao2022 ovarian US** | 超声 + 多中心 + reader study 设计 | 妇瘤任务 |
| **jiang2021/2022 gastric CT** | 胃癌多中心 + reader study | CT 模态 |

PDF 与提取文本：`docs/references/ldh/`

---

## 8. 改稿决策树（遇到冲突时）

```
新结果 vs 冻结 contract？
  ├─ 是 → 不开 test split；只改 val 或新 ablation 行；更新 SSOT_MAP
  └─ 否 → 直接写入 tex + 更新 GAP_TRACKER

叙事 vs 工程细节冲突？
  └─ 临床叙事赢 → 细节下沉 Appendix

对标 LDH vs 诚实性冲突？
  └─ 诚实性赢 → 写 planned / TBD / caveat（参照 ldh2 PFS 未超全部基准）

是否进正文？
  └─ 查 paper_governance/DECISION_LOG_paper.md
```

---

## 9. 版本记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-05 | v1.0 | 新建 `docs/ldh_mainline/`；确立临床主轴与 LDH 结构映射 |
| 2026-06-05 | 手稿 v2.1 | Summary 五段、Research in context、benchmark 表、扩 Discussion |
| 2026-06-10 | 手稿 v2.2 | 4-agent 审核→统一修复：T2→T3 over-stage 0.10→0.058 (4 处)；4 中心 22%→20% (3 处)；failure mode % 修正；fig:cohortflow 移至 Appendix S1；12 fake cite + 2 重复 + 14 unused 清理；Sounderajah/Liu2020claim/Zheng2025/Isensee 期刊/年份错引修正；Figure 5 caption 补 (e)；Appendix S8 加 IRB list；Discussion 扩至 1500 词；加 `tab:baseline` 14 行 + p 值；3 个 dangling PNG 归档 |
| 2026-06-10 | 手稿 v2.3 | 4-agent 审核 round 2→统一修复：M1 T1→T2 over-stage 6%→5.1% (16/312)；M2 1000-patient hypothetical 220 → 10% prevalence + 0.65 lift → ~100-110 additional T2 frames / 1,600 帧；M3 fig:confusion caption 0.10/0.19 → 0.058/0.20 + 加 boundary-subset 0.095/0.29；M4 Appendix S6 22% → 20% (495/2458)；P1 Introduction L106/L108 净化（移除工程术语） |
| 2026-06-10 | G04 闭环 | Bootstrap 2000 真跑：`scripts/bootstrap_tstaging_ci.py` 提交；tab:ci 8 metric × 2 cohort 全部替换为真 95% CI；§Limitations 第 4 条 / Appendix S5 "in progress" 声明删除；§Summary/§Findings/§Results/§Discussion/§Conclusions 全部 CIs 替换为真值 |
| 2026-06-11 | 筛图确认 | 真实 funnel 数字算清：ext 2966→2458 (508 dropped, 17.1%) / pro 2430→1659 (771 dropped, 31.7%)；新增 `scripts/make_screening_funnel_figure.py` + `fig:screening_funnel`（Appendix S1）；§Findings 加 funnel 数字 + 引用 |
