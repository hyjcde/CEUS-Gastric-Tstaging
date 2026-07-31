# Agent Platform Rollout

## Current implementation

The local platform now uses a hybrid architecture:

- Web product surface in `apps/gastric_scan_next`
- Product API in `apps/gastric_scan_next/app/api/agent/`
- Python Agent / tools / memory in `pipeline/agent/`

## Memory layers

### CaseMemory

Purpose:

- retrieve similar historical patients
- return stage distribution and cohort context

Implementation:

- `pipeline/agent/memory/current_case_memory.py`
- optional FAISS path via `pipeline/agent/memory/index/`

### SessionMemory

Purpose:

- preserve current review-session continuity
- accumulate multiple analyzed cases within the same UI workflow

Implementation:

- `pipeline/agent/memory/session_memory.py`
- persisted to `tmp/agent_sessions/`

### KnowledgeMemory

Purpose:

- retrieve process, governance, and evaluation snippets from local docs
- give the Agent a light knowledge layer even without remote RAG services

Implementation:

- `pipeline/agent/memory/knowledge_memory.py`

## Self-evolving memory extension

The larger research mainline treats memory as more than a product feature. It should become the mechanism that lets the medical Agent improve across reviewed cases without immediately retraining the foundation model or specialist tools.

### Episodic clinical memory

Purpose:

- store case-level diagnostic episodes
- connect similar cases, predictions, final pathology, tool traces, and retrospective error summaries
- support T2/T3 boundary review and external/prospective failure analysis

Current base:

- `pipeline/agent/memory/current_case_memory.py`
- `pipeline/agent/memory/case_memory.py`
- optional FAISS path via `pipeline/agent/memory/index/`

### Procedural heuristic memory

Purpose:

- store reusable diagnostic rules distilled from repeated successes and failures
- prioritize rules for high-risk situations such as T2/T3 ambiguity, poor ROI coverage, or conflicting clinical and imaging evidence
- make the Agent's reasoning policy auditable instead of only prompt-driven

Initial representation:

- short rule text
- target scenario
- priority
- evidence source
- usage count
- observed utility

### Tool-governance memory

Purpose:

- track when to trust, down-weight, or avoid each tool
- record reliability by source, modality, quality condition, and task
- prevent a noisy segmentation, classifier, report extractor, or video-frame selector from silently dominating the final report

Initial trust labels:

- `trusted`
- `caution`
- `avoid`

This extension is inspired by the Evo-MedAgent pattern: read memory before diagnosis, write reflected experience after feedback, and keep the base model frozen during the first test-time learning stage.

## Rollout phases

### Phase 1: Platform alignment

Goal:

- remove old `/data/research/gastric/Tstaging` path coupling
- expose a stable product API
- keep graceful degradation when models or indexes are unavailable

Validation:

- `POST /api/agent/analyze` returns structured JSON
- `GET /api/agent/session/[sessionId]` returns persisted session state

### Phase 2: RAG + memory UI

Goal:

- surface similar cases and knowledge snippets in the UI
- expose tool evidence and recommended stage in a clinician-readable panel

Validation:

- `AgentWorkbenchPanel` renders in the diagnosis view
- UI can launch analysis for a selected case and show similar cases

### Phase 3: System-level medical Agent

Goal:

- upgrade from product wrapper to full coordinator workflow
- plug in stronger segmentation/classification checkpoints
- add structured traces, richer report synthesis, and session replay

Validation:

- ReAct or planner-driven orchestration can call multiple tools per case
- session memory spans multiple patient reviews
- case memory index and knowledge retrieval both contribute to final reports

### Phase 4: Self-evolving research loop

Goal:

- update episodic, procedural, and tool-governance memory after pathology or physician feedback
- use T staging, especially T2/T3 error review, as the first closed-loop benchmark
- compare no-memory, episodic-memory, procedural-memory, and full-memory Agent variants

Validation:

- the same case stream can be replayed with and without evolving memory
- memory updates are traceable to specific cases and feedback
- tool trust labels change only after enough evidence accumulates
- external and prospective cohorts remain separated in reporting

## Operational notes

- If segmentation/classification checkpoints are unavailable, the platform still runs with fallback evidence.
- If API keys are absent, report synthesis remains local and rule-based.
- Once stable checkpoints and vector indexes are restored, the same API surface can serve stronger models without changing the frontend contract.
