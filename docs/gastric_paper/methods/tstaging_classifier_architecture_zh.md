# T 分期分类器架构说明（当前实现 vs 目标形态）

> 回答常见问题：**「是不是多分支 + 本例 patch + 相似病例一起推理？」**  
> 相关代码：`pipeline/lib/models.py`、`pipeline/lib/contrastive_models.py`、`pipeline/agent/tools/classification_tool.py`、`pipeline/agent/product/analyze_case.py`

---

## 1. 一句话结论

| 问题 | 答案 |
|------|------|
| 现在 Agent 里的 `ClassificationTool` 是多分支吗？ | **是**：Global + ROI 双 backbone +（可选）mask 第 4 通道 + 临床向量。 |
| 推理时是否用**本例** direction / arcband patch？ | **当前 Agent 主线：否**。patch 只在 `contrastive_dual` **训练**里做 SupCon，标准 eval 时 patch **不进**分类 logits。 |
| 推理时是否用**相似病例**特征？ | **否（不在分类器 forward 里）**。相似病例在 `SimilarityTool` + 规则融合层，与 `classify` 工具**并列**，不是同一个网络。 |
| 分类头要不要很大？ | **不必**。表征在 ConvNeXt + cross-attention fusion；头默认 `hidden_dim=256`（`ClassificationHead`），可再缩小，优先加 patch/病例证据进 **融合层** 而非堆大 MLP 头。 |

---

## 2. 系统里实际有三层（不要混成「一个分类模型」）

```text
┌─────────────────────────────────────────────────────────────┐
│ L3  Agent 证据融合（analyze_case._build_rule_based_report）   │
│     base_T_probs + similar_cases 投票 + 报告/临床 cue       │  ← 相似病例在这里
└───────────────────────────┬─────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────┐
│ L2  工具链（并列调用，非单一 nn.Module）                      │
│     ClassificationTool | SegmentationTool | SimilarityTool   │
│     ClinicalTool | ReportTool | DINO 可视化                  │
└───────────────────────────┬─────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────┐
│ L1  可训练 checkpoint（多条主线，见 model_asset_audit.md）   │
│     dual_branch (mask4ch) | contrastive_dual (region-aware)  │
└─────────────────────────────────────────────────────────────┘
```

**科研叙事上的「多模态 T 分期」** = L1 一条（或多条）checkpoint + L2 工具 + L3 门控融合；**不是**「一个 end-to-end 网络同时吃相似病例 embedding」。

---

## 3. 路线 A：当前 Agent 默认 — `dual_branch`（冻结 mask4ch）

**类**：`DualBranchClassifier`（`pipeline/lib/models.py`）

**推理输入**（`ClassificationTool.execute`）：

| 分支 | 输入 | Backbone |
|------|------|----------|
| Global | 全图 RGB + 可选 mask 第 4 通道 | ConvNeXt-Base @ 384 |
| Local | ROI crop（医生框 / 分割 bbox） | ConvNeXt-Small @ 224 |
| Clinical | 22D 真临床 **或** Agent 里 9D seg 代理特征 | 小 MLP `clinical_hidden=32` |

**融合**：`CrossAttentionFusion` → `fusion_hidden=256` → `ClassificationHead(in→256→4)`

**没有**：

- 本例 direction_patch / arcband_strip / control_band
- 相似病例向量
- DINO 区域 token（仅 Agent 侧可视化 / 未来 RAG）

```text
  [Global 4ch] ──► g_backbone ──┐
                                 ├── cross_attn ──► cls_head(256) ──► T1..T4+
  [ROI 3ch]    ──► l_backbone ──┘
  [clinical]   ──► clinical_mlp ─┘ (concat)
```

**设计含义**：结构先验主要靠 **predicted mask 进 global 第 4 通道**；胃壁方向带尚未进入该路线的 forward。

---

## 4. 路线 B：scoreboard external 最强 — `contrastive_dual`（region-aware）

**类**：`DualContrastiveClassifier`（`pipeline/lib/contrastive_models.py`）  
**数据**：`RegionContrastiveDataset` — 每样本除 global/roi 外还有：

| 字段 | 含义 |
|------|------|
| `border_patches[0]` | direction_patch（指向病灶的定向 patch） |
| `border_patches[1]` | arcband_strip（弧带条） |
| `distant_patches[0]` | control_arcband_strip（对照壁带） |

**训练时**（`contrastive_mode: joint`）：

- **分类路径**：与 dual_branch 相同 — global + ROI (+ clinical) → `cls_head` → CE/ordinal
- **对比路径**：border/distant patches → local backbone → `ProjectionHead` → SupCon（`lambda_con` 较小，如 0.05）

**评估 / 推理时**（`ContrastiveTrainer._evaluate` 对 `DualContrastiveClassifier`）：

```python
# 非 GastricWallEvidenceNet 时，eval 显式丢弃 patch，只 forward global+roi+clinical
border_patches = None
distant_patches = None
logits = model(global_image=..., local_image=..., clinical=...)
```

因此 **region-aware 在报表上的 AUC，来自「训练时 patch 监督过的 backbone」，而不是「推理时把 patch 拼进分类头」**。  
这与「推理时多分支带 patch」的直觉 **不一致** — 需要在论文/产品文案里写清楚，或改推理路径（见 §6）。

**分类头规模**（region-aware config）：`head_hidden: 256`，`fusion_hidden: 256` — 与 dual_branch 同级，**不是**大模型瓶颈；瓶颈在双 ConvNeXt backbone。

---

## 5. 路线 C：胃壁证据显式进 forward — `GastricWallEvidenceNet`

**类**：`GastricWallEvidenceRouter` + patch bag  
**特点**：推理时 **会** 把 border/distant patch 编成 wall token，与 global/ROI 一起做 Transformer 融合（`uses_wall_evidence_tokens=True`）。  
**eval**：`ContrastiveTrainer` 对这类模型 **保留** patch 输入。

box-guided wall contrastive 等优化 run 多属此族或 residual fusion 变体 — **更接近**「本例 patch 参与定稿 logits」，但 Agent **尚未接入**。

---

## 6. 相似病例：在哪里、不是什么

| 组件 | 作用 | 是否进入分类器 forward |
|------|------|------------------------|
| `SimilarityTool` + FAISS | 17 维（概率+形态+临床）近邻 | **否** |
| `similar_cases` in `analyze_case` | 展示 + 规则层 `_summarize_similarity` | **否** |
| adapter-DINO Case-RAG（`train_learned_dino_case_rag.py`） | 科研分支 R0–R5 | **否**（小权重融合在 eval 脚本里） |

**目标形态**（Case-RAG 计划）：`final_T = base_T * (1-λ) + case_vote_T * λ`，λ 由 `RAGGate` 决定 — 仍是 **融合层**，不是把邻居特征 concat 进 `cls_head`。

若要做 **端到端「邻居特征进网络」**，属于新架构（memory attention / set transformer），**当前仓库未实现**。

---

## 7. 「分类头不用太大」— 工程建议

当前 `ClassificationHead` 仅为 `Linear(fused_dim, 256) → ReLU → Dropout → Linear(256, 4)`。

| 优先级 | 建议 |
|--------|------|
| P0 | 保持 backbone + fusion 为主；头可试 `head_hidden=128` 或单层 `Linear(fused_dim, 4)` 做 ablation |
| P1 | **推理时**让 region-aware / wall-evidence 模型的 **patch 分支进入融合**（改 eval 或专用 `ContrastiveTStagingTool`），而不是加大 cls_head |
| P2 | Agent 层：相似病例作为 **有门控的 second opinion**，不替代 L1 checkpoint |
| P3 | 患者级：多帧 MIL 聚合 logits，而非每帧加大头 |

**参数大头**：`convnext_base` + `convnext_small` >> `cls_head`。

---

## 8. 与 Agent 选型表的关系

| backend | 架构族 | Agent 推理是否含本例 patch | Agent 推理是否含相似病例 |
|---------|--------|---------------------------|-------------------------|
| mask4ch 20260423（primary） | dual_branch | 否（仅 mask 4th ch） | 否（融合层） |
| region-aware 20260426 | contrastive_dual | **训练有 / 默认 eval 无** | 否 |
| boxguided wall 20260506 | wall_evidence / contrastive_dual | 若接 EvidenceNet：**可有** | 否 |

详见 [`model_asset_audit.md`](model_asset_audit.md)、[`agent_backend_registry.yaml`](../../pipeline/agent/config/agent_backend_registry.yaml)。

---

## 9. Phase B 文档/代码待对齐项

1. **`ContrastiveTStagingTool`**：加载 `DualContrastiveClassifier` 或 `GastricWallEvidenceNet`；可选开关 `use_patches_at_inference: true`（与训练 eval 纪律对齐或故意改为 true 做产品实验）。
2. **manifest 在线构建**：direction/arcband 需与 `build_region_contrastive_manifest.py` 同源，否则 patch 路径为空。
3. **统一写清** `tool_evidence.classification` 的 `architecture_family` 字段，避免前端误以为「相似病例已进网络」。
4. **头容量 ablation**：在固定 backbone 下扫 `head_hidden ∈ {64,128,256}`，验证「缩小头」不损 prospective AUC。
