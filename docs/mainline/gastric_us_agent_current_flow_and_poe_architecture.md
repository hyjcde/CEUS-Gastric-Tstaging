# 胃癌超声多模态 Agent 当前流程与 Poe GPT-Image 架构图方案

## 1. 当前流程定位

当前系统不是让大模型直接看图并替代医生下诊断，而是一个“固定工具链 + 多源证据融合 + 医生复核”的临床辅助 Agent。

核心目标是把一个病例的图像、ROI、分割、形态、分类概率、临床结构化字段、术前报告线索、历史相似病例和知识库证据整理成可追溯结果。最终输出不是一句自然语言结论，而是结构化 JSON，再由前端拆成医生容易看懂的模块。

主流程可以概括为：

```text
医生选择病例
-> Next.js 前端展示图像、ROI、诊断面板和临床信息
-> 点击“运行 Agent”
-> POST /api/agent/analyze
-> Next.js API 把病例对象转换成 Python payload
-> pipeline/agent/product/analyze_case.py 执行固定工具链
-> 多工具证据融合
-> 返回推荐 T 分期、概率、证据、相似病例、不确定性和报告草稿
-> Agent Workbench 展示
-> 医生复制、修改、确认或驳回
-> 后续写入 memory 候选
```

## 2. 前端入口

前端位于：

```text
apps/gastric_scan_next
```

主要文件：

```text
apps/gastric_scan_next/app/api/patients/route.ts
apps/gastric_scan_next/app/api/agent/analyze/route.ts
apps/gastric_scan_next/lib/agent-server.ts
apps/gastric_scan_next/components/AgentWorkbenchPanel.tsx
apps/gastric_scan_next/components/DiagnosisPanel.tsx
```

医生操作路径：

1. 打开胃癌 T 分期智能辅助系统。
2. 左侧选择患者或 frame-level 病例。
3. 中间查看超声图像。
4. 右侧查看诊断、病理推理、临床数据。
5. 在 `Agent Workbench` 点击运行。
6. 前端调用 `POST /api/agent/analyze`。
7. 页面展示 Agent 返回的结构化结果。

前端显示层包含：

- 推荐 T 分期；
- 模型概率；
- 支持证据；
- 冲突证据；
- 工具状态；
- 相似病例；
- 知识上下文；
- 动态报告草稿；
- 轨迹引用；
- 后续医生反馈入口。

## 3. Next.js 到 Python Agent 的桥接

`app/api/agent/analyze/route.ts` 不直接运行模型，而是调用 `lib/agent-server.ts`，把前端患者对象整理成 Python 可读 payload。

典型 payload 字段包括：

```text
patient_id
case_token
cohort_year
treatment_type
dataset
data_source
frame_count
clinical
report_text
segmentation
image_path
roi_path
annotation_path
overlay_path
```

然后 Next.js API 通过子进程启动：

```text
pipeline/agent/product/analyze_case.py
```

Python 脚本从标准输入读取 JSON，执行工具链后，把结果 JSON 写到标准输出。Next.js 再把这个 JSON 转发给浏览器。

这种设计的好处是：

- 前端不直接接触模型权重；
- Python 端可以复用现有实验脚本和医学特征工具；
- 每次 Agent 运行可以保存 trajectory；
- 工具失败时可以降级，不会让前端整页崩溃。

## 4. Python Agent 工具链

当前 `analyze_case.py` 是固定顺序工具链，不是完全自主规划型 Agent。固定顺序更适合医疗场景，因为每一步都可追踪、可复核。

执行顺序（2026-05 已接 lumen / wall / clinical22 / 多帧）：

```text
1. Case intake
2. LumenDetectionTool (YOLO11l)
3. SegmentationTool (UNet++ primary)
4. WallEvidenceTool (lumen signed-distance)
5. MorphologyTool
6. ClassificationTool (mask4ch + clinical22; ≤3 frames mean prob)
7. ClinicalTool
8. ReportTool
9. SimilarityTool + KnowledgeMemory
10. DINO feature panel (visualization)
11. Rule-based evidence fusion (rag_gate, conflicting_evidence)
12. Optional LLM synthesis (Poe)
13. Dynamic report draft + runtime verification + trajectory
11. Dynamic report draft builder
12. Memory update candidate builder
13. Session memory save
14. Trajectory JSON save
```

各工具角色如下：

| 工具 | 输入 | 输出 | 临床意义 |
|---|---|---|---|
| `SegmentationTool` | 超声图像、已有 mask/ROI | lesion mask、ROI bbox、面积比例 | 判断病灶区域是否可用 |
| `MorphologyTool` | mask / ROI | convexity、solidity、irregularity、compactness | 描述边界和形态异常 |
| `ClassificationTool` | 图像、ROI、mask、结构化特征 | T1/T2/T3/T4+ 概率 | 给出模型分期倾向 |
| `ClinicalTool` | 年龄、性别、肿瘤长度、厚度、CEA、CA199 等 | 临床风险评分 | 判断临床信息是否支持模型 |
| `ReportTool` | 术前报告文本 | 胃壁增厚、层次破坏、浆膜侵犯等 cue | 抽取文本证据 |
| `SimilarityTool` | 当前病例向量 | 历史相似病例 | 给医生相似病例参考 |
| `KnowledgeMemory` | 项目知识库 | T 分期规则、解释片段 | 支撑报告生成 |

## 5. 当前模型层

### 5.1 分割

当前主流程使用 UNet / UNet++ / ConvNeXt encoder 分割工具作为 primary segmentation。

它输出：

```text
available
mask_available
roi_source
roi_bbox
lesion_area_ratio
image_height
image_width
```

如果模型不可用，会降级到中心裁剪或已有 ROI。这个 fallback 能保证后续流程可运行，但前端应提示分割证据较弱。

### 5.2 DINOv3 / SegDINO

项目已有 DINOv3 / SegDINO 候选分割和 DINO rich scalar 特征。

目前状态：

- SegDINO/DINOv3 分割已在实验中证明 ROI 正确时 Dice 可显著提升；
- `dinov3_segmentation_tool.py` 已存在，但还不是主流程 primary tool；
- DINO rich scalars 已用于 T 分期下游分支；
- DINO region token / wall-band embedding 是下一步相似病例和证据解释的重点。

建议后续变成：

```text
UNet++ primary segmentation
+ DINOv3 / SegDINO candidate segmentation
+ lumen / wall ROI constraint
-> segmentation consensus
-> ROI confidence
-> manual review flag
```

### 5.3 CLIP / OpenCLIP

当前 CLIP 不做端到端微调，而是冻结 OpenCLIP 图像 encoder 提取 embedding。

当前有效方式：

```text
OpenCLIP image embedding
-> frame-level / patient-level branch classifier
-> late fusion
```

CLIP 图像分支在 clean late fusion 中是强分支，文本 prompt/report 分支已构建但当前权重为 0，主要原因是英文 CLIP text encoder 与中文临床报告不完全匹配。

### 5.4 分类与融合

当前 Agent 里接入的分类工具仍偏旧，主要是 dual-v2 / mask4ch 一类输入协议。

当前实验主线里更好的 clean 候选包括：

```text
OpenCLIP image branch
+ DINO clinical branch
+ clinical/anatomic features
+ history retrieval
-> validation-selected probability late fusion
```

其中 clean `late_fusion_v2` 的权重为：

```json
{
  "clinical_anatomic": 0.0,
  "dino_clinical": 0.35,
  "clip_image": 0.60,
  "clip_report": 0.0,
  "history": 0.05
}
```

最近继续训练的结论是：

- `clean_boundary_expert_continue_20260518_120624_dino24` external AUC 接近 `0.8184`；
- `clean_model_zoo_continue_20260518_152542_dino32_seed19_top20` external AUC 到 `0.8037`，test AUC 到 `0.7753`；
- 后处理式 ordinal calibration 和 T2/T3 refiner 不稳定；
- 继续盲目调 top-k 或阈值收益有限。

## 6. 证据融合逻辑

Agent 不是简单取分类模型 top1，而是把多个证据源汇总：

```text
classification probabilities
+ segmentation / morphology evidence
+ clinical risk
+ report cues
+ similar case distribution
+ knowledge memory
-> evidence fusion
-> recommended T stage
-> confidence
-> uncertainty flags
-> report draft
```

当前融合以规则式逻辑为主。若配置了 API key，才会进入可选 LLM synthesis。

LLM synthesis 的默认 Poe 接入在：

```text
pipeline/agent/core/llm_client.py
```

默认配置：

```text
base_url = https://api.poe.com/v1
model = DeepSeek-V4-Flash-EL
```

读取 key 的顺序：

```text
AGENT_API_KEY
VLM_API_KEY
POE_API_KEY
OPENAI_API_KEY
```

如果没有 key，Agent 会跳过 LLM synthesis，直接返回规则式报告。这样可以保证系统无 key 时仍可用。

## 7. Memory 与相似病例

当前相似病例检索主要使用：

```text
classification probabilities
+ morphology features
+ clinical features
```

也就是 17 维左右的病例向量。严格说，当前线上 Agent 的相似病例还不是显式 DINO embedding 检索。

建议升级为多块向量：

```text
patient_vector =
  classification_probs
  + ordinal_boundary_probs
  + morphology_features
  + clinical22_features
  + report_cue_features
  + dino_global_embedding
  + dino_roi_embedding
  + dino_wall_band_embedding
  + contrastive_border_intact_embedding
```

这样医生看到相似病例时，不只是“概率相似”，还能知道：

- 图像域是否相似；
- ROI 纹理是否相似；
- 胃壁侵犯模式是否相似；
- 临床风险是否相似；
- 分期边界是否相似。

## 8. Poe GPT-Image 方法学架构图（细图推荐 GPT-Image-2）

脚本：

```text
scripts/generate_agent_architecture_image_poe.py
```

Poe OpenAI-compatible endpoint：`https://api.poe.com/v1/images`

| 变体 | 模型默认 | Prompt 文件 | 输出 PNG |
|------|----------|-------------|----------|
| `overview` | GPT-Image-1 | `gastric_us_agent_architecture_poe_prompt.txt` | `gastric_us_agent_architecture_poe.png` |
| **`detailed`** | **GPT-Image-2** | `gastric_us_agent_methodology_architecture_poe_prompt_detailed.txt` | `gastric_us_agent_methodology_architecture_poe.png` |

中文规范（泳道、图例、与代码对齐的主路径）：[`gastric_us_agent_methodology_architecture_spec_zh.md`](gastric_us_agent_methodology_architecture_spec_zh.md)

```bash
# 导出细版 prompt（无需 Key）
python scripts/generate_agent_architecture_image_poe.py --variant detailed --dry-run

# 生成细版方法学架构图
export POE_API_KEY="your_poe_api_key"
python scripts/generate_agent_architecture_image_poe.py \
  --variant detailed \
  --model GPT-Image-2 \
  --quality high
```

简版总览：

```bash
python scripts/generate_agent_architecture_image_poe.py --variant overview --model GPT-Image-1
```

## 9. 架构图应表达的结构

架构图应使用四层结构：

```text
Clinical UI
Agent Orchestration
Evidence Tools
Model / Data Layer
```

图中的主路径：

```text
Doctor selects case
-> Next.js Frontend (Agent Workbench)
-> POST /api/agent/analyze  (frames[], clinical22)
-> Python analyze_case.py
-> Lumen YOLO -> Segmentation -> Wall SDF -> Morphology
-> Classification (mask4ch 20260423) + Clinical + Report
-> Similarity (RAG gate) + Knowledge
-> Evidence Fusion (conflicts + uncertainty)
-> T-stage recommendation + Dynamic report draft + artifacts
-> Doctor feedback -> Memory update
```

模型与数据层要显示：

```text
Ultrasound frames
ROI / lesion mask
UNet++ primary segmentation
DINOv3 / SegDINO candidate
OpenCLIP image embeddings
DINO rich scalars
Clinical/anatomic features
Preoperative report cues
FAISS similar cases
```

这张图的重点不是炫技，而是让读者一眼看懂：医生不是直接问大模型，而是通过可追溯工具链整合证据，再由医生复核。
