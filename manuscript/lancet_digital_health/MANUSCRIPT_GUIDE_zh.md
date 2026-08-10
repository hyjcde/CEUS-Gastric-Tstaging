# Lancet Digital Health 撰稿指南（中文）

本指南配合 `main.tex` 使用，帮助你在定稿前逐项完成投稿准备。

## 一、期刊硬性要求速查

| 项目 | 要求 |
|------|------|
| 文章类型 | Original research (Article) |
| 正文字数 | 通常 ≤3500 词（RCT 可到 4500） |
| 摘要 | ≤300 词，五段标题：Background / Methods / Findings / Interpretation / Funding |
| 必备板块 | Research in context（三段，无参考文献） |
| 图表 | 按期刊 artwork PDF 导出高分辨率 |

## 二、本项目论文的“故事主线”

1. **临床问题**：胃充盈超声 T 分期可及，但 T2/T3 难、且不能替代 EUS。  
2. **工程问题**：训练时有 mask/ROI，真实视频推理时没有 → 必须报告可部署模型。  
3. **方法贡献**：患者级多中心验证 + 两阶段（定位/分割 → 分类）+ 边界注意力两阶段训练。  
4. **结果要点**：前瞻 AUC 两阶段 0.739；外部仍低于 mask 参考 0.659；T2 召回仍低。  
5. **结论定位**：分诊/转诊辅助，而非替代病理或 EUS。

## 三、当前稿内图表清单

| 编号 | 文件 | 内容 |
|------|------|------|
| Fig 1 | `figures/study_flow.tex` | 研究流程（TikZ） |
| Fig 2 | `figures/pipeline_diagram.tex` | 技术流水线（TikZ） |
| Table 1 | `tables/cohort_tstage.tex` + main | 队列与 T 分布 |
| Table 2 | main `tab:cohort` | Split 概览 |
| Table 3 | main `tab:classification` | 分类主结果 |
| Table 4 | `tables/clinical_harm.tex` | 误判临床代价 |

## 四、定稿步骤（建议顺序）

1. 填写 `authors_template.tex` → 合并进 `main.tex` 标题页。  
2. 补伦理批件、注册号（如有前瞻性成分）。  
3. 从 `results/visualizations/` 导出真实 ROC/混淆矩阵图，替换 Results 中的文字占位。  
4. 运行 `scripts/wordcount.sh`（需 `texcount`）核对词数。  
5. 文献：完成 PubMed/Embase 系统检索，更新 `references.bib`。  
6. 附录：编译 `supplementary_appendix.tex`，上传为 Supplementary material。  
7. 完成 ICMJE 利益冲突表、数据共享声明、AI 使用披露（若使用生成式 AI 改稿）。

## 五、常见审稿意见预防

- **只报图像级 AUC**：务必强调患者级聚合。  
- **外部验证不足**：突出莆田 + 肿瘤医院 + 前瞻集。  
- **T2 样本量**：在 Limitations 主动讨论，并报告 T2 召回而非仅总 AUC。  
- **与 EUS 对比缺失**：在 Discussion 明确经腹超声定位，并计划亚组与 EUS 对照。  
- **可重复性**：给出 GitHub 与（计划中的）数据访问流程。

## 六、编译命令

```bash
cd manuscript/lancet_digital_health
latexmk -pdf main.tex
latexmk -pdf supplementary_appendix.tex
```

若缺少 TikZ 库，安装 `texlive-pictures` 或完整 TeX Live。
