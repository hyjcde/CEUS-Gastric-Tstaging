# Agent 记忆系统与相似度设计（医学 × AI）

> **定位**：定义 GastricTstaging Agent 如何 **取特征、判相似、写记忆、门控 RAG**，服务 **T2/T3/T4+ 边界** 而非替代 base 分类器。  
> **配套代码**：`pipeline/agent/memory/` · `SimilarityTool` · `analyze_case.py`

---

## 1. 医学问题：什么叫「相似病例」？

经腹超声 T 分期里，**相似 ≠ 图像长得像**，而是：

| 相似维度 | 临床含义 | 应对 T 分期 |
|----------|----------|-------------|
| **胃壁侵犯模式** | 病灶是否突破浆膜、外侧壁是否连续 | T2↔T3、T3↔T4+ |
| **过渡带形态** | 病灶–胃腔间壁层厚度、外突深度 | T2/T3 核心证据 |
| **病灶形态** | 不规则度、面积比、低回声范围 | 辅助，非充分 |
| **临床协变量** | 部位、分化、肿瘤大小 | T4+、整体校准 |
| **分类器 logits** | 模型当前信念 | **弱先验**（避免循环论证） |

**反例（不应高相似）**：
- 两帧 **亮度/增益** 接近但 **pT 不同**
- **T2 浅浸润** vs **T3 浆膜突破** 外观相近
- **伪突破**（亮壁伪影）vs 真 T3

因此相似度必须是 **分块加权 + 壁层优先**，不能单一全图 cosine。

---

## 2. 记忆系统三层架构

```text
L1  episodic case memory（病例情节记忆）
     train 患者 → 28-d 分块向量 / Adapter-DINO NCA 嵌入
     用途：Case-RAG top-k 检索

L2  session memory（会话记忆）
     tmp/agent_sessions/*.json — 本次工作台浏览过的患者摘要

L3  knowledge memory（知识记忆）
     docs/mainline/*.md 关键词检索 — 指南/方法学片段

L4  trajectory（审计轨迹，非检索）
     tmp/agent_trajectories/ — 完整 JSON 落盘供科研复核
```

**纪律（顶刊 split）**：
- **仅协和 train** 写入 L1 case memory
- val 选 retriever 超参 / RAG gate
- prospective + external **只读** memory，禁止回写

---

## 3. 特征怎么取？（28 维分块向量）

实现：`multimodal_case_vector.py`

| 块 | 维度 | 来源工具 | 内容 |
|----|------|----------|------|
| classification | 4 | ClassificationTool | P(T1..T4+) 帧均值 |
| morphology | 5 | MorphologyTool | 凸度、不规则度、面积比… |
| clinical | 8 | ClinicalInfo | 年龄、部位、CEA、分化… |
| **wall** | **7** | **WallEvidenceTool** | 穿透风险、SDF 外突深度、壁接触弧 |
| **boundary** | **4** | 派生 | T2+T3 质量、T3+T4+ 质量、entropy、margin gap |

**Adapter-DINO 路径（39936-d → NCA 32-d）**：
- 区域：lesion / wall_band / breakthrough / intact_control / 差分
- 患者级：帧 mean pooling → PCA(128) → NCA(32) → cosine 检索
- 脚本：`cache_adapter_dinov3_case_rag_features.py` · `export_adapter_dino_case_retriever.py`

---

## 4. 相似度怎么判？

实现：`case_similarity.py`

### 4.1 分块加权 cosine（Agent 默认，有 wall 时）

```text
sim = Σ_b  w_b · cosine(query_block_b, memory_block_b)

默认权重：
  wall       0.40  ← T2/T3 核心
  boundary   0.25  ← 相邻期混淆区
  morphology 0.13
  classification 0.12  ← 故意压低，防循环
  clinical   0.10
```

**边界加强（boundary_boost）**：当 P(T2)+P(T3)≥0.45 或 wall_risk≥medium 时，wall/boundary 权重 +10%。

### 4.2 Legacy FAISS L2（无 extended index 时）

`similarity = 1 / (1 + L2)`，仅 17 维 — **缺 wall，T2/T3 能力有限**。

### 4.3 Adapter-DINO NCA + softmax vote

```text
sims = query · memory^T
weights = softmax(sims / temperature)
P_RAG(T) = Σ_k w_k · onehot(T_mem_k)
```

val 最优：top_k=9, temperature=0.2, fusion_alpha=0.3（与 base 分类器融合）。

---

## 5. Agent 运行时流程

```text
分割 + 胃腔 YOLO
  → WallEvidenceTool（SDF / 穿透风险）
  → ClassificationTool（mask4ch 冻结线）
  → MorphologyTool + ClinicalTool
  → extract_multimodal_case_vector (28-d)
  → SimilarityTool
        ├─ block_weighted_extended（优先）
        ├─ faiss_l2_legacy（fallback）
        └─ adapter_dino_nca（有缓存特征时）
  → _compute_rag_gate（仅 T 边界 + 低 margin 时 rag_weight≤0.35）
  → _build_rule_based_report（融合 base + RAG + wall + 冲突证据）
```

**RAG 门控（医学规则）**：

| 条件 | rag_weight | 理由 |
|------|------------|------|
| T2/T3/T3/T4+ 边界 & (uncertainty≥0.35 或 margin<0.12) | **0.35** | 最需要 case 证据 |
| 同上 + wall_risk medium/high | 0.25 | 壁层与分类冲突 |
| 高 uncertainty 无边界 | 0.15 | 弱辅助 |
| 稳定非边界 | 0 | 抑制 RAG 过拟合历史 |

---

## 6. 构建与更新 memory

```bash
# 1) 28-d 分块 case matrix + legacy FAISS
CUDA_VISIBLE_DEVICES=0 python pipeline/agent/memory/case_memory.py \
  --csv pipeline/data/tstaging_4class/splits/xiehe_single_center_v1/train_clinical.csv

# 2) Adapter-DINO retriever 工件
python scripts/export_adapter_dino_case_retriever.py
```

医生确认后的 `memory_update_candidates` → 未来增量 append（当前 status=candidate）。

---

## 7. 评估指标

| 类型 | 指标 | 目标 |
|------|------|------|
| 检索 | top-1 same T-stage @5 | >0.45（adapter val） |
| 检索 | T2/T3 子集 majority @5 | 高于 legacy 17-d |
| 分类 | RAG plus_base Δacc vs M0 | val +2–4% |
| Agent | Full vs base T-only | prospective T2 recall +5% |
| 临床 | 冲突证据可解释率 | 医生可复核 |

---

## 8. 与旧 17 维方案对比

| | 旧 17-d FAISS | 新 28-d 分块 | Adapter-DINO |
|--|---------------|-------------|--------------|
| wall 信息 | ❌ | ✅ SDF 7 维 | ✅ 区域 embedding |
| T2/T3 导向 | 弱 | **强（权重 65%）** | 强（NCA 监督） |
| 在线成本 | 低 | 低 | 中（需特征缓存/编码） |
| 科研验证 | 基线 | Agent 默认 | R5 gated 分支 |

---

## 9. 下一步

1. 用 **xiehe-only train** 重建 `case_matrix_extended.npy`
2. 在线 Adapter 编码器（`image_path` → 39936-d）接入 Agent
3. T2/T3 hard negative 挖掘写入 retriever 训练
4. 前端展示 **block_similarity** 雷达图（为何相似）
