---
name: "t2-t3-error-analysis"
description: "Analyze T2/T3 boundary errors using image, ROI, mask, model probabilities, Grad-CAM or local evidence, clinical context, and source-specific failure patterns."
---

# T2/T3 Error Analysis

Use this skill when a case is predicted as T2 or T3, when T2/T3 probabilities are close, or when a retrospective error review targets the T2/T3 boundary.

## Goal

Explain whether the error is more likely caused by:

- ambiguous biology or pathology boundary
- poor ROI or lesion mask
- shortcut learning from background or high-brightness regions
- weak wall-layer or lesion-edge evidence
- source-specific distribution shift
- clinical feature conflict
- model backend calibration failure

## Required Evidence

- image and ROI references
- mask source: GT, predicted, unavailable, or fallback
- model backend ID and probability distribution
- T2/T3 probability gap
- morphology evidence
- source/cohort/split
- similar-case distribution
- available Grad-CAM or local patch evidence when generated

## Review Steps

1. Confirm whether the case is truly T2/T3 boundary-sensitive.
2. Check whether ROI and mask cover the lesion edge and gastric wall region.
3. Compare classifier evidence with morphology and clinical risk.
4. Inspect whether model attention or local evidence is near the lesion boundary.
5. Compare similar cases and source-specific failure patterns.
6. Decide whether the case should update procedural memory or tool-governance memory.

## Output Contract

Return:

- `boundary_sensitive`: boolean
- `likely_error_sources`: array of strings
- `evidence_for_t2`
- `evidence_for_t3`
- `conflicting_evidence`
- `manual_review_priority`: high | medium | low
- `memory_update_candidates`

## Procedural Rule Candidates

Create a procedural rule candidate when the same pattern appears repeatedly, for example:

- T3 overcalled when predicted mask includes far background.
- T2 undercalled when lesion-edge patch is missing.
- External-center cases require lower trust in segmentation-derived ROI.
- T2/T3 should be reviewed manually when T3 probability is high but morphology is smooth and clinical risk is low.

## Tool Governance Candidates

Create a tool-governance candidate when a backend repeatedly helps or harms:

- segmentation tool misses lesion edge
- classifier collapses into T4+ or T1 for a source
- similarity retrieval returns stage distribution inconsistent with pathology
- report extractor produces unsupported staging language

Do not update trusted/caution/avoid labels without enough repeated evidence.
