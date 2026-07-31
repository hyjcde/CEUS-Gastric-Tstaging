# Self-evolving multimodal memory (Evo-MedAgent 3-store)

JSONL-backed **episodic**, **procedural**, and **tool governance** memory for the LangGraph case pipeline. Memory **does not** update ConvNeXt/YOLO weights or override `ClassificationTool` final T stage; it biases evidence weights, review priority, and boundary prompts only.

## Layout

```
pipeline/agent/memory/
  store/
    paths.py           # store_data/<run_id>/ layout
    schema_validate.py # JSON Schema 0.1.0
    jsonl_store.py     # append / load / filter
    retriever.py       # episodic + procedural + governance read
  evolver.py           # reflect / promote / quality_score CLI
  memory_apply.py      # soft_prior fusion into report
  schemas/self_evolving_multimodal_memory.schema.json
  store_data/<run_id>/
    episodes.jsonl
    procedural_rules.jsonl
    tool_governance.jsonl
    candidates.jsonl
    audit.jsonl
```

## Quick start

### 1. Analyze with memory (Workbench / API)

Enable via payload or env:

```bash
export AGENT_MEMORY_ENABLED=1
export AGENT_MEMORY_STORE=pipeline/agent/memory/store_data/default
```

Frontend analyze routes pass `memory_enabled: true` when Workbench runs the agent.

### 2. Doctor / pathology feedback

```bash
echo '{
  "patient_id": "P001",
  "predicted_t_stage": "T3",
  "final_t_stage": "T2",
  "feedback_type": "pathology_result",
  "memory_store": "pipeline/agent/memory/store_data/default"
}' | python pipeline/agent/product/apply_feedback.py --stdin
```

Or `POST /api/agent/feedback` from Workbench (accept / reject / defer on candidates).

### 3. Batch reflect + promote

```bash
python -m agent.memory.evolver \
  --action reflect-batch \
  --feedback-csv path/to/memory_write_feedback.csv \
  --out-store pipeline/agent/memory/store_data/self_evolution_eval

python -m agent.memory.evolver \
  --action promote \
  --min-support 3 \
  --out-store pipeline/agent/memory/store_data/self_evolution_eval
```

### 4. P0-4 evaluation (memory off vs on)

```bash
python pipeline/agent/evaluation/run_self_evolution_eval.py \
  --feedback-csv path/to/memory_write.csv \
  --held-out-csv path/to/held_out.csv \
  --out pipeline/experiments/reports/gastric_us_agent_self_evolution_v1
```

Primary endpoint: **held-out T2↔T3 adjacent error rate**.

## Report fields

After memory-enabled analyze:

- `memory_applied`
- `active_rules_used`
- `governance_trust_labels`
- `memory_update_candidates` (with `record_id` for Workbench confirm)

## Registry

See `pipeline/agent/config/agent_backend_registry.yaml` → `memory:` section.
