# 胃癌超声 T 分期 Agent 方法学架构图规范（Poe GPT-Image-2）

## 1. 用途

为论文 Methods、组会 slide、或 `gastric_tstaging_project_logic.html` 提供**一张可追溯的方法学总图**，说明：

- 医生不直接问大模型下诊断；
- 固定工具链 + 多源证据 + 门控 RAG + 医生复核；
- 冻结模型资产与协和-only 训练 manifest 的关系。

## 2. 生成方式

```bash
# 仅导出 prompt（无需 API Key）
python scripts/generate_agent_architecture_image_poe.py --variant detailed --dry-run

# 使用 Poe GPT-Image-2 生成（需 POE_API_KEY）
export POE_API_KEY="your_key"
python scripts/generate_agent_architecture_image_poe.py \
  --variant detailed \
  --model GPT-Image-2 \
  --quality high \
  --out docs/mainline/gastric_us_agent_methodology_architecture_poe.png
```

默认 prompt 文件：

- 简版：`docs/mainline/gastric_us_agent_architecture_poe_prompt.txt`
- **细版（推荐）**：`docs/mainline/gastric_us_agent_methodology_architecture_poe_prompt_detailed.txt`

## 3. 五层泳道（细图必须包含）

| 泳道 | 内容 |
|------|------|
| A 临床 UI | 医生 → Next.js Workbench → 病例/帧/ROI |
| B API | `/api/agent/analyze` + stream；payload 含 `frames[]`, clinical22 |
| C 编排 | `analyze_case.py` 15 步（含 lumen→seg→wall→cls） |
| D 证据 | 各 Tool 输出 + Fusion（RAG gate、conflicting_evidence） |
| E 模型/数据 | YOLO lumen、UNet++ seg、mask4ch 20260423、FAISS、Xiehe-only split |

## 4. 主路径（与代码一致，2026-05）

```text
Case intake
→ LumenDetectionTool (YOLO11l)
→ SegmentationTool (UNet++ primary)
→ WallEvidenceTool (lumen signed-distance)
→ MorphologyTool
→ ClassificationTool (mask4ch + clinical22, ≤3 frames mean prob)
→ ClinicalTool
→ ReportTool
→ SimilarityTool + KnowledgeMemory
→ Rule fusion (+ optional Poe LLM)
→ JSON report v0.3.0 + artifacts + trajectory
→ Clinician review → memory candidates
```

## 5. 输出 JSON 要点（图中 Fusion 框内）

- `recommended_t_stage`, `confidence`
- `supporting_evidence`, `conflicting_evidence`, `uncertainty_flags`
- `rag_gate.rag_weight`, `rag_gate_reason`
- `tool_evidence.lumen_detection`, `wall_evidence`
- `frame_evidence.aggregation` = `mean_probability` | `single_frame`
- `prediction_artifacts.real_wall_analysis_panel_source` = `live_lumen_signed_distance`

## 6. 图例约定

| 线型/颜色 | 含义 |
|-----------|------|
| 蓝色实线 | 冻结主路径（mask4ch 20260423） |
| 紫色 | 相似病例 / memory |
| 琥珀虚线 | 不确定性 / 需人工复核 |
| 灰色虚线 | 可选（LLM、region-aware 次级） |

## 7. 与简版架构图区别

| 项目 | 简版 `gastric_us_agent_architecture_poe.png` | 细版 methodology |
|------|---------------------------------------------|------------------|
| 工具顺序 | 旧版（缺 lumen/wall） | 与 `analyze_case.py` 一致 |
| 多帧 | 未标 | ≤3 帧概率平均 |
| 模型资产 | 泛称 | 点名 frozen checkpoint / split manifest |
| 融合 | 仅 Evidence Fusion | RAG gate + conflicts |

## 8. 相关文档

- [`gastric_us_agent_current_flow_and_poe_architecture.md`](gastric_us_agent_current_flow_and_poe_architecture.md)
- [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md)
- [`model_asset_audit.md`](model_asset_audit.md)
