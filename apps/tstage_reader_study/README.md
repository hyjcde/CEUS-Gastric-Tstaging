# tstage_reader_study

胃癌 CEUS T 分期独立阅片包 — 卓医生团队

## 设计原则（按 boss + 卓医生 2026-06-12 微信沟通）

1. **UI 极简**：单页 = 视频播放器 + 4 选 1 T-stage 按钮 + 下一例。无其他控件、无个人信息收集表单。
2. **视频优先**：只看视频（默认 0.5× 慢速；可手动调 0.25 / 0.5 / 1 / 2× 倍速；可拖动 scrubber）。
3. **2-pass 设计**：
   - Pass 1：医生独立判断（不展示 AI）
   - Pass 2：同 150 例（顺序不同），展示 AI 判断 + 置信度
4. **子集 n=150**：Arm A (91 例, AI 100%) + Arm B (59 例, AI 17%)，测 AI 在不同难度下的 uplift。

## 子集来源

`docs/clinical_validation/reader_study_150/reader_subset_v2.csv`（由 `scripts/select_reader_study_subset.py` 跑出，基于 06-03 frozen primary，从 185 视频患者中选）

| Arm | n | AI 准确率 | 用途 |
|-----|---|-----------|------|
| A · AI-clean | 91 | 100% | 测医生独立 vs AI 一致性 |
| B · AI-uncertain | 59 | 17% | 测 AI 在困难病例上能否帮医生 |
| **Total** | **150** | — | — |

T-stage 分布：T1=18 / T2=28 / T3=44 / T4+=60
Cohort：external 78 + prospective 72

## 启动

```bash
# 启动本地静态服务器（必走 http://，file:// 路径在浏览器跨域上不稳）
./start.sh
# 打开
# Pass 1: http://127.0.0.1:8765/?reader=zhuo&pass=1
# Pass 2: http://127.0.0.1:8765/?reader=zhuo&pass=2
```

Windows：`start.bat`

## 文件结构

```
apps/tstage_reader_study/
├── index.html         # 单页（视频 + 4 选 1 + 顶栏 pass/case/arm/AI）
├── reader.js          # 2-pass 流程 + 倍速 + scrubber + localStorage
├── reader.css         # 暗色主题，无干扰
├── public/
│   └── cases.json     # 150 例 + 视频绝对路径
├── start.sh / start.bat
└── README.md
```

## 视频文件

`public/cases_videos/<case_id>/<stem>.mp4` 路径下应有视频。若该路径下没有，JS 会自动 fall back 到 `cases.json` 里的绝对 `file://` 路径（要求 reader 端机器能访问 `/data/research/gastric/GastricTstaging/data/raw/...`）。

## 数据导出

每例选完后 220ms 自动跳下一例。所有结果存 `localStorage`，完结时自动下载 JSON：

```
tstage_reader_<reader_id>_pass<1|2>_<YYYY-MM-DD>.json
```

JSON schema:
```json
{
  "reader_id": "zhuo",
  "pass": 1,
  "generated_at": "2026-06-12T...",
  "n_cases": 150,
  "n_completed": 150,
  "results": [
    { "reader_id": "zhuo", "pass": 1, "case_id": "CASE-001", "arm": "A_ai_clean", "t_choice": "T3", "ts": "..." }
  ],
  "case_order": ["CASE-001", "CASE-007", ...]
}
```

医生可中途点页面底部"导出结果"下载部分结果（断电恢复用）。

## 与论文 Appendix S10 的关系

本文稿 Appendix S10 引用本 app 作为 reader study 工具入口。完整协议（n=150、2-arm、2-pass、3-reader 设计、a priori power 计算）见 `docs/paper_drafts/tex_v2_ldh/gastric_tstaging_paper_v2.tex` §app:reader。
