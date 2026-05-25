# Lancet Digital Health 论文稿（LaTeX）

本目录为基于项目主线结果撰写的 **The Lancet Digital Health** 原创研究稿（英文），结构对齐期刊投稿要求。

## 内容来源

- 研究主线：`docs/mainline/research_mainline.md`
- 验证协议：`docs/evaluation/validation_protocol.md`
- 历史结果与实验矩阵：`docs/archive_refs/legacy_selected/`

## 编译

```bash
cd manuscript/lancet_digital_health
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

或使用 `latexmk`：

```bash
latexmk -pdf main.tex
```

## 投稿前待填项

在 `main.tex` 中搜索 `TODO`：

- 作者单位、通讯作者、ORCID
- 伦理批件号与临床试验注册号（如适用）
- 各中心具体名称与数据贡献声明
- 最终图表文件（`figures/`）
- 利益冲突与数据共享的具体联系方式

## 字数说明

正文目标约 3500 词（RCT 可至 4500）。当前为完整框架稿，定稿前请用期刊工具核对词数并压缩 Methods 技术细节至 Supplementary appendix。
