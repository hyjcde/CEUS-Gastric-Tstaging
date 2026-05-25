# Lancet Digital Health 论文稿（LaTeX）

本目录为基于项目主线结果撰写的 **The Lancet Digital Health** 原创研究稿（英文），结构对齐期刊投稿要求。

## 内容来源

- 研究主线：`docs/mainline/research_mainline.md`
- 验证协议：`docs/evaluation/validation_protocol.md`
- 历史结果与实验矩阵：`docs/archive_refs/legacy_selected/`

## 文件结构

| 路径 | 说明 |
|------|------|
| `main.tex` | 主文稿（含 TikZ 图 1–2） |
| `supplementary_appendix.tex` | 附录（扩展实验表、报告清单） |
| `figures/*.tex` | TikZ 图源文件 |
| `tables/*.tex` | 可复用表格 |
| `MANUSCRIPT_GUIDE_zh.md` | 中文定稿指南 |
| `authors_template.tex` | 作者/单位模板 |
| `scripts/wordcount.sh` | 词数核对脚本 |

## 编译

```bash
cd manuscript/lancet_digital_health
latexmk -pdf main.tex
latexmk -pdf supplementary_appendix.tex
bash scripts/wordcount.sh
```

依赖：`texlive-latex-base`, `texlive-pictures`（TikZ）, `texlive-extra-utils`（texcount，可选）。

## 投稿前待填项

在 `main.tex` 中搜索 `TODO`：

- 作者单位、通讯作者、ORCID
- 伦理批件号与临床试验注册号（如适用）
- 各中心具体名称与数据贡献声明
- 最终图表文件（`figures/`）
- 利益冲突与数据共享的具体联系方式

## 字数说明

正文目标约 3500 词（RCT 可至 4500）。当前为完整框架稿，定稿前请用期刊工具核对词数并压缩 Methods 技术细节至 Supplementary appendix。
