# 项目范围与阶段目标

## 项目目标

本项目面向 **胃癌术前胃充盈超声**，构建 **以 T 分期为核心** 的 **辅助诊断 Agent 系统**。

临床主问题：**T1 / T2 / T3 / T4+ 术前分期辅助**（患者级、多帧、胃壁侵犯深度）。

工程形态：**固定工具链 + 多源证据融合 + 医生复核**，不是单模型黑盒，也不是 LLM 直接看图下诊断。

## 当前阶段判断（2026）

项目已积累大量单点模型结果（胃腔 YOLO、nnU-Net/DINO 分割、ConvNeXt T 分期主线、DINO 特征与 RAG 原型）。**当前阶段重点从「继续训练新模型」转向「审计已有结果 → 选型接入 Agent → 冻结多中心验证」。**

详见 [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md)。

## 任务优先级

| 优先级 | 内容 |
|--------|------|
| P0 | T 分期四分类（主终点、论文主表） |
| P1 | 术前辅助诊断 Agent（整合、证据链、工作台） |
| P2 | T-centric Case-RAG 与证据门控 |
| P3 | 良恶性二分类与边缘监督（方法验证，从属） |
| P4 | 新 backbone 大规模训练（需充分理由） |

## 两阶段技术底座（仍然成立，但角色调整）

| 阶段 | 内容 | 当前角色 |
|------|------|----------|
| **Stage 1** | 胃腔检测、病灶分割、ROI/mask | **资产已有多条 baseline**；Agent 消费其输出与可信度 |
| **Stage 2** | T 分期分类（+ 临床/壁区特征） | **核心能力**；从 scoreboard 选型，接入 ClassificationTool |

良恶性任务：**先做、不重要**——用于验证局部监督与域泛化，有效再服务于 T2/T3 边界，不替代 T 主叙事。

## 数据与验证范围

- 开发：**福建协和单中心**（时间切分 train/val/test/prospective）
- 验证：**11 家外部中心** 冻结评估（Tier-1 主外部表）
- 纪律：外部不参与训练、SSL、RAG memory

见 `dataset/DATASET_GUIDE.md` 与科研计划 §1.1。

## 更大研究范围

T 分期 Agent 也是 **多模态循证医学 Agent 自进化平台** 的首个强验证场景（图像、mask、临床、报告、视频、指南、病例记忆）。平台叙事见：

- [`multimodal_evidence_agent_self_evolution_mainline.md`](multimodal_evidence_agent_self_evolution_mainline.md)

近期工程仍收敛在：**split 治理、T 模型选型、Agent 整合、T2/T3 证据链、冻结验证**。

## 当前主要任务

### 第一优先级

- 读懂并登记已有 T 分期 / 分割 / YOLO / DINO 实验结果
- 固定协和-only split 与外部冻结评估协议
- Agent 接入选定 T checkpoint 与证据 schema
- T2/T3、T3/T4+ 错误分析与 Case-RAG 边界设计

### 第二优先级

- Case-RAG 门控与科学基准全矩阵
- 前端 Workbench 与真实推理对齐
- 论文级表图（T 主表 + Agent 消融 + 外部森林图）

### 第三优先级

- 良恶性边缘监督迁移实验（在 A/B 阶段空隙进行）
- 新分割/DINO 训练（仅当审计证明现有 mask 不够）

## 当前不做什么

- 无目标的四分类 backbone 竞赛
- 以外部数据训练后冒充「干净外部验证」
- 良恶性 Agent 作为临床主产品叙事
- 未接入 T 主线的孤立 RAG 或 VLM 演示

## 成功标准

1. 新成员 10 分钟内能说出：**主任务 = T 分期 Agent**，以及默认 T 模型与 AUC 出处。
2. Agent 单次运行可追溯：用了哪些 checkpoint、哪些证据支持/冲突 T 结论。
3. 冻结验证下：**Full Agent ≥ base T-only**（或更好的边界不确定性识别），外部 T 指标可报告。
4. 任一结论可追溯到 split 版本、配置与 `pipeline/experiments/reports/` 中的数字。
