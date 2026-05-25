# 研究主线

## 默认入口

当前项目请先读：

- `docs/mainline/tstaging_current_mainline.md`
- `docs/mainline/multimodal_evidence_agent_self_evolution_mainline.md`

其中 `tstaging_current_mainline.md` 是近期执行入口，已经把会议纪要、旧实验和当前 baseline 的关系重新收口；`multimodal_evidence_agent_self_evolution_mainline.md` 是更大的课题叙事入口，用来说明 T 分期如何成为多模态循证医学 Agent 自进化平台的核心验证场景。

## 当前路线的最短理解

**总框架入口**：[`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md)

当前默认路线不是继续大规模扩 `T 分期四分类` backbone，而是：

```text
审计已有 YOLO / 分割 / ConvNeXt T / DINO 训练结果
  -> 选定 Agent 默认 T 与分割 backend
  -> 构建以 T 分期为核心的术前辅助诊断 Agent
  -> T-centric Case-RAG 与证据门控（边界场景）
  -> 协和-only 训练 + 多中心冻结验证
  -> 良恶性/边缘监督仅作方法验证（从属，非主终点）
```

## 当前只看 3 条判断标准

1. 新工作是否帮助 **T 分期**（尤其患者级输出、T2/T3、外部验证）。
2. 新工作是否帮助 **整合已有模型进 Agent**（而不是重复训同类模型）。
3. 新工作是否帮助 **解释或缓解 T2/T3 / T3/T4+ 错误**（含 RAG、wall 证据）。

如果一个方向不能回答上面 3 点中的至少 1 点，就不应进入近期优先级。

## 更大的课题定位

在总课题层面，当前 T 分期不是孤立的分类任务，而是多模态循证医学 Agent 系统的第一条强验证主线。这个系统将图像、mask/ROI、临床表、报告文本、视频、指南知识和历史病例组织成可追溯证据链，并通过病例记忆、诊断规则记忆和工具可信度记忆形成长期自进化闭环。

因此，近期实验仍然按 T 分期主线收敛推进；对外叙事和中长期平台设计则按多模态 Agent 主线组织。

## 每条主线仍然必须保留的证据

- 数据版本记录
- 配置文件
- 训练日志
- 患者级结果表
- 内部验证结果
- 外部验证结果
- 失败案例复盘材料
