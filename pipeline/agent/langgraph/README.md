# LangGraph Agent 编排

生产路径 **`run_case_pipeline`** 已切换为 LangGraph 12 节点 case pipeline。

## 两条 LangGraph 路径

| 路径 | 入口 | 用途 |
|------|------|------|
| **Case pipeline（生产）** | `run_case_pipeline` → `run_langgraph_case_pipeline` | 12 Agent 节点，每步 plan+interpret LLM + CV 工具 |
| **ReAct loop（评测）** | `run_langgraph_react_loop` | LLM 逐步选 tool，e2e demo |

## Case pipeline 图结构

```
triage → frame_extract → quality → binary_gate → lumen_detect → lesion_seg
  → morphology → t_staging → wall_evidence → dinov3_seg → case_rag → report_synth → END
```

每个节点：
1. **LLM plan** — 执行前 reasoning（完整 messages 写入 trace）
2. **Agent.run()** — 原有 pipeline_steps 工具链
3. **LLM interpret** — 解读 observation（完整 messages 写入 trace）

产物：`llm_trace.json`（24 次调用 = 12 步 × 2）、每步 JSON 含 `llm_calls`。

## LLM 后端优先级

1. `MINIMAX_API_KEY` → MiniMax-M3
2. `AGENT_API_KEY` / `VLM_API_KEY` / … → OpenAI 兼容
3. 无 Key → `StepNarrativeLLM` 模板（仍可跑通并记录 I/O）

## 运行

```bash
pip install -r pipeline/agent/requirements-langgraph.txt

# 生产 pipeline + 前瞻视频完整报告
python3 scripts/build_case001_video_report.py \
  --case CASE-002 --video-source internal_prospective_crop --clip-index 1

# 仅 pipeline
python3 -m agent.pipeline.run_case --case CASE-002 --input-mode video --out /tmp/out
```

## ReAct（评测）

```bash
python3 scripts/run_e2e_react_demo.py --cases CASE-001 --orchestrator langgraph
```

## 目录

```
pipeline/agent/langgraph/
├── case_pipeline/     # 生产 12-step
├── graph.py           # ReAct 图
├── run_react.py
└── README.md
```
