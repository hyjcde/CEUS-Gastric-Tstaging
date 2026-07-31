---
name: "t-staging-evidence-review"
description: "Review one gastric T-staging case with structured multimodal evidence, tool outputs, uncertainty flags, and similar-case context."
---

# T Staging Evidence Review

Use this skill when the Agent reviews one gastric cancer T-staging case in the frontend workbench or offline batch mode.

## Goal

Produce a clinician-readable evidence report, not a one-shot diagnosis.

The report must explain:

- which modalities were available
- which model tools were called
- which evidence supports the recommended T stage
- which evidence conflicts with the recommendation
- whether manual review is needed
- which memory records should be updated after feedback

## Required Inputs

- `patient_id`
- image path or frame reference
- ROI path or ROI bbox when available
- lesion mask source and quality status
- clinical variables when available
- classification backend ID when a model was used
- similar-case retrieval result
- knowledge snippets or guidelines when available

## Tool Order

1. Validate image and ROI availability.
2. Run or reuse lesion segmentation.
3. Extract morphology evidence from mask or annotation.
4. Run T-stage classification backend.
5. Compute clinical risk features.
6. Retrieve similar cases.
7. Retrieve knowledge snippets.
8. Fuse evidence into a structured report.

## Output Contract

Return a JSON-compatible report with:

- `recommended_t_stage`
- `confidence`
- `supporting_evidence`
- `conflicting_evidence`
- `uncertainty_flags`
- `manual_review_recommended`
- `tool_status`
- `memory_update_candidates`

## Safety Rules

- Do not let one classifier output dominate the report.
- Always include uncertainty when segmentation, ROI, clinical variables, or memory retrieval is missing.
- If T2 and T3 probabilities or evidence are close, mark the case as boundary-sensitive.
- If external-newzip or unseen-center evidence is weak, use a tool-governance caution flag.
- Never mix benign/video data into the T1/T2/T3/T4+ split.

## Memory Update Candidates

After doctor or pathology feedback, propose records for:

- `case_episode`
- `procedural_rule`
- `tool_governance`
- `model_backend_evidence`

Do not promote candidates directly into stable memory without review.
