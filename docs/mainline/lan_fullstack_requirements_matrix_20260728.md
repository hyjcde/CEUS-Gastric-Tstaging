# 产品需求实现对照表（局域网全栈 · 2026-07-28）

> 来源合并：协和会议需求说明书（2026-07-12）、自进化记忆闭环计划、Next 边界编辑/Agent Workbench、远程阅片包。  
> 验收命令：`bash scripts/run_lan_merged_system.sh start` → `bash scripts/test_lan_full_stack.sh`

## 局域网入口

| 服务 | URL |
|------|-----|
| 完整工作台 Next | http://10.13.199.162:3000/ |
| 阅片合并入口 | http://10.13.199.162:8767/ai_assist.html |
| 交互 Agent（视频跟随） | http://10.13.199.162:8767/interactive_video_agent.html |
| 视频分层 demo | http://10.13.199.162:8767/video_mask_demo.html |
| 静图方向 | http://10.13.199.162:8767/direction_demo.html |
| Auth + DeepSeek | http://10.13.199.162:8766/api/health |

---

## A. 基础设施与 API

| ID | 需求 | 实现状态 | 证据 / 路径 |
|----|------|----------|-------------|
| A1 | 局域网三线（auth/SAM/Next）一键启动 | **已实现** | `scripts/run_lan_merged_system.sh` |
| A2 | Auth 健康检查 | **已实现** | `GET :8766/api/health` |
| A3 | DeepSeek API 接入阅片 LLM | **已实现** | `server/deepseek_llm.mjs` + `deepseek_api_key.txt`；`preferred=deepseek-harness` |
| A4 | DeepSeek 状态可探测（无密钥泄露） | **已实现** | `GET /api/llm/status` 公开；health 含 `llm.deepseek_configured` |
| A5 | MiniMax 报告（SAM 侧） | **已实现** | `:8767/api/sam/status` → minimax.configured |
| A6 | Python Agent LLM（Poe/OpenAI 兼容） | **部分** | 根 `.env` 有 `POE_API_KEY`/`AGENT_API_KEY`；Next `.env.local` 中 AGENT_LLM 仍注释，默认可不走 LLM 润色 |
| A7 | SAM2 交互分割服务 | **已实现** | `scripts/serve_interactive_sam_agent.py` · Dice≈0.87 finetune |
| A8 | 远程阿里云阅片 | **已部署（外部）** | `47.106.33.102`；本地以 LAN 8767 为开发真相 |

## B. 分割 / 边界编辑 / 视频跟随

| ID | 需求 | 实现状态 | 证据 / 路径 |
|----|------|----------|-------------|
| B1 | 静图病灶边界多边形编辑（移/加/删点） | **已实现** | `InteractiveSegPanel.tsx` |
| B2 | SAM 点击分割 | **已实现** | Next → `/api/agent/sam-interactive` → `:8767` |
| B3 | 边界覆盖持久化并进 Agent analyze | **已实现** | `mask-overrides` API + `doctor_override` / LesionSegAgent |
| B4 | 橙/绿双轮廓编辑（胃壁+病灶） | **阅片包已实现；Next 仅病灶** | `video_mask_demo` / `direction_demo`；Next 面板以病灶绿轮廓为主 |
| B5 | 视频 scrub + 本帧编辑 | **已实现（Next）** | InteractiveSegPanel「视频跟随」模式 |
| B6 | 播放时边界跟随（SAM re-track） | **已实现（Next + 阅片 Agent）** | Next：`播放时 SAM 跟随`；8767：`trackOnPlay` |
| B7 | 视频关键帧人手保存 | **阅片包已实现** | `video_mask_demo` |
| B8 | AI 邻域关键帧候选（G6） | **未完成** | 需求说明书 P2；仍人手 scrub |
| B9 | 全视频自动分割上线（G8） | **不做当前上线** | 仅本地 demo / 跟随模式 |

## C. 分层 / 达层 / 接触门控（阅片几何）

| ID | 需求 | 实现状态 | 证据 / 路径 |
|----|------|----------|-------------|
| C1 | 接触门控：无接触不可分期（G2） | **应已合入阅片包** | `ContactGeom` / demo；以 `:8767` direction/video_mask 验收 |
| C2 | 分层线 clip 在壁通道内（G1） | **应已合入阅片包** | 同 C1 |
| C3 | 层数 2–5 自适应 + 假想插层（G3） | **应已合入阅片包** | 同 C1 |
| C4 | 相邻胃壁延伸（G4/G5） | **部分 / 待回归** | 会议后迭代；需在 direction_demo 回归 |
| C5 | 放大图无文字、侧栏结论（G7） | **基本满足** | demo UI |

## D. Agent Workbench / 评分 / 记忆

| ID | 需求 | 实现状态 | 证据 / 路径 |
|----|------|----------|-------------|
| D1 | Agent 工具链分析（L0/L1/seg/wall/RAG） | **已实现** | `AgentWorkbenchPanel` + `pipeline/agent` |
| D2 | 流式 analyze | **已实现** | `/api/agent/analyze/stream` |
| D3 | 临床风险分 / composite_score / CBM CPS | **已实现（临床评分，非医生打星）** | DiagnosisPanel / ExplainableAnalysis / StatisticsPanel |
| D4 | 医生记忆候选 accept/reject/defer | **已实现** | `/api/agent/feedback` + Workbench |
| D5 | 三层自进化记忆 store + evolver | **已实现** | `pipeline/agent/memory/` |
| D6 | memory-on/off 评估脚本（P0-4） | **已实现** | `run_self_evolution_eval.py`；标题词 self-improving 仍 No-Go 直至阳性 |
| D7 | 阅片 Agent 结果回写 Next | **已实现** | `/api/reader-agent/result` + ReaderAgentResultCard |
| D8 | 上传视频多帧分析 | **已实现** | `VideoAnalysisUpload` + `/api/agent/video/analyze` |

## E. 正式阅片 / 远程

| ID | 需求 | 实现状态 | 证据 / 路径 |
|----|------|----------|-------------|
| E1 | 盲法 task1/task2 150 例 | **已实现（包内）** | `:8767/task1.html` |
| E2 | 账号登录进度同步 | **已实现** | auth_server users/progress |
| E3 | 远程同步脚本 | **已实现** | `sync_remote_reader_study.py` |

---

## 本轮补齐项（2026-07-28）

1. LAN 三线拉起并验收。  
2. DeepSeek 状态公开探测 + lan 启动注入 key file。  
3. Next 边界编辑增加**视频跟随**（scrub + 播放 SAM 跟踪 + `video_time_sec` 持久化）。  
4. `/api/patients/videos` 样例/模糊匹配。  
5. `scripts/test_lan_full_stack.sh` 自动化验收。

## 仍打开的缺口（按优先级）

1. **B8** 视频邻域 AI 关键帧候选。  
2. **B4** Next 工作台双轮廓（橙壁+绿灶）与阅片包几何完全对齐。  
3. **C4** 相邻延伸回归证明。  
4. **A6** 把 AGENT_LLM/DeepSeek-V4 显式接到 Next→Python Agent 润色（可选）。  
5. **D6** 自进化主终点阳性证据（才能改标题词）。
