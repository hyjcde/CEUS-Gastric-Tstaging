# 产品需求总清单（可勾选 · 实现 SSOT）

> **文档角色**：所有产品需求的唯一勾选清单。实现前后必须更新本文件状态。  
> **创建**：2026-07-28 · **状态图例**：`[x]` 已完成 · `[~]` 部分完成 · `[ ]` 未做 · `[-]` 明确不做（本期）  
> **验收入口**：`bash scripts/run_lan_merged_system.sh start` → `bash scripts/test_lan_full_stack.sh`  
> **来源**：协和会议需求书（2026-07-12）、人机互助计划（2026-07-16/17）、自进化记忆闭环、LAN/Next/Agent 集成

---

## 0. 使用约定

1. **先勾清单、再改代码**：新需求先在本文件加 ID，再实现。  
2. **一条需求 = 一条验收**：每条写「Done when」。  
3. **实现顺序**：按 §1 优先级队列，从 P0 往下做；不做列表见 §9。  
4. **改状态时**同步改「证据路径」与「最近更新」。  
5. 旧对照表 [lan_fullstack_requirements_matrix_20260728.md](./lan_fullstack_requirements_matrix_20260728.md) 保留为快照；**以本文件为准**。

**最近更新**：2026-07-29（U1–U3 加法融合：AssistHub + 人机互助 callback 回写；不删旧入口）

---

## 1. 实现优先级队列（当前）

| 序 | ID | 优先级 | 标题 | 状态 |
|----|-----|--------|------|------|
| 1 | A6 | P0 | Next→Python Agent LLM 显式接线（DeepSeek/Poe） | `[x]` |
| 2 | B4 | P0 | Next 双轮廓编辑（橙=胃壁，绿=病灶） | `[x]` |
| 3 | B8 | P1 | 视频邻域 AI 关键帧候选（最小可用） | `[x]` |
| 4 | C-VERIFY | P1 | 阅片包 G1–G5 几何门控自动化回归 | `[x]` |
| 5 | F1 | P1 | Next 内嵌/深链人机互助页（关键帧+征象报告） | `[x]` |
| 6 | U1–U3 | P1 | 医生统一入口加法融合（AssistHub / callback / 主推 :3000） | `[x]` |
| 7 | D6b | P2 | 自进化 held-out 主终点阳性实验（标题词门控） | `[ ]` **← 下一刀** |
| 8 | B9 | — | 全视频分割上云 | `[-]` 本期不做 |

---

## 2. A · 基础设施 / API / 局域网

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | A1 | 一键启动 auth:8766 + SAM:8767 + Next:3000 | `run_lan_merged_system.sh status` 三线 ready | `scripts/run_lan_merged_system.sh` |
| [x] | A2 | Auth `/api/health` | HTTP 200 + `ok:true` | `:8766/api/health` |
| [x] | A3 | DeepSeek 接入阅片 LLM（click-brief / wall-reason） | key 可加载；`preferred` 含 deepseek | `deepseek_llm.mjs` + keyfile |
| [x] | A4 | LLM 状态公开探测（无密钥） | 未登录可 `GET /api/llm/status` | auth_server |
| [x] | A5 | MiniMax 配置于 SAM 侧 | sam status 显示 minimax.configured | `:8767/api/sam/status` |
| [x] | A6 | **Python Agent 润色 LLM 从 Next 进程可用** | analyze 时 `AGENT_LLM_*`/`POE`/`DEEPSEEK` 经环境注入；有探测 API 或日志证明 | `lib/agent-python-env.ts` + `GET /api/agent/llm-status` |
| [x] | A7 | SAM2 交互服务 GPU | `ready:true` + cuda | serve_interactive_sam_agent.py |
| [x] | A8 | 远程阿里云阅片包可访问 | 外部 URL（非本机阻塞项） | 47.106.33.102 |
| [x] | A9 | LAN 自动化验收脚本 | `test_lan_full_stack.sh` RESULT: OK | `scripts/test_lan_full_stack.sh` |
| [x] | A10 | SAM Next 代理 base URL 正确（非 HTML 路径） | POST `/api/agent/sam-interactive` → 200 + polygon | `lib/reading-agent-url.ts` |

---

## 3. B · 分割 / 边界编辑 / 视频

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | B1 | 静图病灶多边形：移/加/删顶点 | UI 可编辑并保存 | `InteractiveSegPanel.tsx` |
| [x] | B2 | SAM 点击分割（含归一化坐标→像素） | 点击返回 ≥3 顶点像素多边形 | SAM proxy + denorm |
| [x] | B3 | 覆盖持久化并进入 Agent analyze | `doctor_override` / mask_override 生效 | mask-overrides + LesionSegAgent |
| [x] | B4 | **双轮廓**：橙=胃壁/腔外缘，绿=病灶；编辑后重算上下文 | 两套多边形可切换编辑、保存、回放；Agent 至少消费绿灶（壁轮廓可选进 wall tool） | InteractiveSegPanel + `wall_polygon` |
| [x] | B5 | 视频 scrub + 当前帧编辑 | 视频条可 seek，边界叠在当前帧 | 视频跟随模式 |
| [x] | B6 | 播放时 SAM 边界跟随 | checkbox「播放时 SAM 跟随」更新多边形 | trackOnPlay |
| [x] | B7 | 阅片包视频关键帧人手保存 | video_mask_demo 可保存关键帧 | `:8767/video_mask_demo.html` |
| [x] | B8 | **邻域 AI 关键帧候选** | 给定锚点时间窗，返回 Top-K 帧+分数+理由，点击跳转 | `/api/agent/video/keyframes` + Panel |
| [-] | B9 | 全视频自动分割上线小服务器 | — | 本期不做（G8） |
| [x] | B10 | 视频目录 API / 模糊匹配 | `GET /api/patients/videos` | `app/api/patients/videos` |
| [x] | B11 | 覆盖含 `video_time_sec` / `video_url` | 保存后再读可见 | `MaskBoundaryOverride` |

---

## 4. C · 分层几何 / 达层 / 接触门控（阅片包）

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | C1 | 无接触不报达层（G2） | 点远离病灶 → 侧栏「无接触/不可分期」 | ContactGeom；`test_contact_geometry_regression.mjs` |
| [x] | C2 | 分层线 clip 在橙绿通道内（G1） | 线不进入绿轮廓、不穿出橙侧 | wallLayerArcsSvg + C-VERIFY |
| [x] | C3 | 层数 2–5 自适应 + 假想插层（G3） | 糊图不切线风暴；侧栏可标假想 | analyzeEchoRay + C-VERIFY |
| [x] | C4 | 相邻胃壁搜索 + 通道等分延伸（G4/G5） | 关注点失败时从邻段延伸 | extendLayersAlongChannel + C-VERIFY |
| [~] | C5 | 放大图无度量中文；结论侧栏（G7） | 放大 SVG 无「达/%/px」类字 | demo UI |
| [x] | C-VERIFY | **自动化几何回归**（10 静图用例） | 脚本跑 contact/clip/层数断言，进 test_lan | `scripts/test_contact_geometry_regression.mjs` |

---

## 5. D · Agent Workbench / 评分 / 记忆

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | D1 | 工具链 analyze（seg/cls/wall/RAG…） | Workbench 可跑完整流 | pipeline/agent |
| [x] | D2 | 流式 analyze | `/api/agent/analyze/stream` | stream route |
| [x] | D3 | 临床风险 / composite / CBM CPS 展示 | UI 有分数条 | Diagnosis/Explainable/Stats |
| [x] | D4 | 记忆候选 accept/reject/defer | feedback API + UI | AgentWorkbenchPanel |
| [x] | D5 | 三层记忆 store + evolver | reflect/promote CLI | `pipeline/agent/memory/` |
| [x] | D6 | memory-on/off 评估脚本骨架 | 产出 summary/metrics | run_self_evolution_eval.py |
| [ ] | D6b | **自进化主终点阳性**（标题词门控） | held-out T2↔T3 错误复发率显著下降 | 实验后改状态 |
| [x] | D7 | 阅片 Agent 结果回写 Next | ReaderAgentResultCard | reader-agent/result |
| [x] | D8 | 上传视频多帧分析 | VideoAnalysisUpload | video/analyze |
| [x] | D9 | LLM 不主诊 T（硬约束） | 最终 T 来自 ClassificationTool | 架构约定 |

---

## 6. E · 正式阅片 / 远程 / 账号

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | E1 | 盲法 task1/task2 | 包内可开 | `:8767/task1.html` |
| [x] | E2 | 登录 + 进度 | auth session | auth_server |
| [x] | E3 | 远程同步脚本 | 文档/脚本存在 | sync_remote_reader_study.py |

---

## 7. F · 人机互助（human_assist）

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | F0 | 阅片包内 human_assist P0 三件套 | 关键帧/征象报告/ROI+补扫 | `direction_demo.html`（现网等价；原 human_assist_v2 未独立部署） |
| [x] | F1 | **Next 可打开/深链到人机互助** | Header 或面板一键打开对应 case | Header「人机互助」→ `direction_demo.html?sample=` |
| [x] | F1b | **Next 内嵌胃壁特征分析 + 会议纪要** | SAM 侧栏显示接触/占壁厚/达层/纪要 | `WallFeatureAnalysisCard` + vendor ContactGeom/LayerBridge |
| [~] | F2 | 医生 ≥10 例试用问题表 | 流程工具已有；人工试用待做 | 进度核对 2026-07-17 |
| [ ] | F3 | 征象字典老板确认 v1 | 非工程阻塞；字典替换后勾选 | 待业务确认 |

---

## 7b. U · 医生统一入口（加法融合，不删旧）

| 勾选 | ID | 需求 | Done when | 证据 |
|------|-----|------|-----------|------|
| [x] | U1 | **AssistHub**：主页可发现日常辅助 | 左上辅助中心聚合 /reader、边界、Agent、人机互助、标注、研究链；Header 四按钮仍在 | `components/AssistHub.tsx` + `app/page.tsx` |
| [x] | U2 | **人机互助 callback 回写** | `buildHumanAssistUrl` 带 `callback=`；`direction_demo`「回写工作台」POST；ResultCard 展示分层/边界 | `reading-agent-url.ts` + `direction_demo.html` + `ReaderAgentResultCard.tsx` |
| [x] | U3 | **LAN 主推 :3000**（不藏旧 URL） | `run_lan_merged_system.sh` 顶部推荐医生入口；下列原 URL 仍全部打印 | `scripts/run_lan_merged_system.sh` |

---

## 8. 每条待实现的详细规格

### A6 — Agent LLM 接线

- Next `dev_server` / analyze spawn 继承根目录 `.env` 的 `POE_API_KEY`/`AGENT_API_KEY`/`AGENT_LLM_*`。  
- `.env.local` 增加可复制模板；可选 `DEEPSEEK` OpenAI 兼容 base。  
- Done when：`GET` 探测或 analyze 日志出现 LLM backend≠heuristic（无 key 时明确 fallback）。

### B4 — 双轮廓

- UI：图层切换「胃壁(橙) / 病灶(绿)」；各自移加删点；可从 LabelMe 双 shape 载入。  
- 存储：`MaskBoundaryOverride.wall_polygon` + `mask_polygon`。  
- Agent：病灶 mask 继续 override；wall_polygon 写入 report/tool 上下文（至少 JSON 透传）。  
- Done when：保存→刷新→两轮廓仍在；analyze payload 含两者。

### B8 — 邻域关键帧

- API：`POST /api/agent/video/keyframes`：`video_url|path`, `anchor_sec`, `window_sec`, `top_k`。  
- 打分：清晰度+对比度+（可选）相对锚点距离惩罚。  
- UI：视频跟随模式下展示候选条，点击 seek。  
- Done when：自动化测试对样例 mp4 返回 ≥1 候选。

### C-VERIFY — 几何回归

- 对 `direction_cases` 抽 ≥3 例：接触点 / 非接触点断言。  
- 独立脚本 `scripts/test_contact_geometry_regression.mjs`，已并入 `test_lan_full_stack.sh`。

### F1 — Next 深链人机互助

- Header「人机互助」→ `:8767/direction_demo.html?sample=<key>`（现网等价页）。
- `buildHumanAssistUrl` + `direction_demo` `resolveBootCaseIndex()`。

### F1b — Next 内嵌特征分析

- Vendor：`apps/gastric_scan_next/public/vendor/human-assist/{contact_geometry,interactive_layer_bridge}.js`（自 reader_study_v150 拷贝）。
- UI：`InteractiveSegPanel` 侧栏 `WallFeatureAnalysisCard`（接触 / 占壁厚 / 达层 / 壁厚栈 SVG / 会议纪要）。
- Alt+点击设浸润取样点；达层为软提示，不作病理金标准。

### U1–U3 — 加法融合

- **只增不删**：Header 标注/视频平台/阅片Agent/人机互助、全部 `:8767` HTML、外链均保留。
- AssistHub 为额外发现层；人机互助在原 `window.open` 上追加 callback；LAN 脚本加主推行但不删 URL 列表。

---

## 9. 明确不做（本期）

- [-] B9 全视频分割部署到阿里云小服务器  
- [-] 在线微调 ConvNeXt/YOLO 权重作「自进化」  
- [-] LLM/VLM 作为 T 分期主诊器  
- [-] 医生星级「打分 App」（当前评分=临床/CPS/composite）

---

## 10. 验收命令速查

```bash
# 启动
bash scripts/run_lan_merged_system.sh start

# 总验收
bash scripts/test_lan_full_stack.sh

# 本清单实现后应追加的用例（随代码补）
# - A6: llm env probe
# - B4: dual-polygon save/load
# - B8: keyframe candidates API
# - C-VERIFY: node scripts/test_contact_geometry_regression.mjs
# - F1: Header humanAssist → direction_demo?sample=
```

---

## 11. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-28 | 初版清单建立；队列 A6→B4→B8→C-VERIFY→F1 |
| 2026-07-28 | **A6/B4/B8 完成**：llm-status、双轮廓、邻域关键帧；`test_lan_full_stack.sh` 32 PASS；下一刀 C-VERIFY |
| 2026-07-28 | **C-VERIFY/F1 完成**：几何回归 75 PASS；Header 人机互助深链 `direction_demo?sample=`；下一刀 D6b |
| 2026-07-28 | **F1b**：ContactGeom/LayerBridge 迁入 Next；`WallFeatureAnalysisCard` + 会议纪要；下一刀 D6b |
| 2026-07-29 | **U1–U3**：AssistHub + direction_demo callback 回写 + LAN 主推 `:3000`（加法，不删旧入口）；下一刀仍为 D6b |
