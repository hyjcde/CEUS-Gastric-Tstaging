/**
 * Separate doctor-facing assist stage from research/classifier prediction.
 *
 * - assist_display_stage / contour_diagnosis.display_stage: ContourEvidenceGate output (often cTx)
 * - recommended_t_stage / classification.top1: research / fusion tendency (not formal cT)
 */

import type { AgentAnalysisResponse } from '@/types';

function normalizeStage(value: unknown): string | null {
  const raw = String(value || '').trim();
  if (!raw) return null;
  if (/^c?tx$/i.test(raw) || /^utx$/i.test(raw)) return 'cTx';
  if (/t4\s*\+/i.test(raw)) return 'T4+';
  const t4 = raw.toUpperCase().match(/\bT4([AB])\b/);
  if (t4) return `T4${t4[1].toLowerCase()}`;
  const match = raw.toUpperCase().match(/\bT([1-3])\b/);
  if (match) return `T${match[1]}`;
  if (/^(benign|良性)$/i.test(raw)) return 'benign';
  if (/^(malignant|恶性)$/i.test(raw)) return 'malignant';
  return raw;
}

/** Doctor-facing suggestion only. Prefer ContourEvidenceGate; never invent definite cT from missing gate. */
export function getAssistDisplayStage(result: AgentAnalysisResponse | null | undefined): string | null {
  if (!result?.report) return null;
  const gated = result.report.assist_display_stage
    || result.report.contour_diagnosis?.display_stage
    || null;
  if (gated) return normalizeStage(gated);
  // No gate payload: stay honest — do not fall back to fusion recommended_t_stage.
  return 'cTx';
}

/** Research / classifier tendency (acc_boost2 fusion top). Label as tendency, not formal cT. */
export function getResearchPredictionStage(result: AgentAnalysisResponse | null | undefined): string | null {
  if (!result) return null;
  const cls = normalizeStage(result.tool_evidence?.classification?.top1_stage);
  if (cls) return cls;
  return normalizeStage(result.report?.recommended_t_stage);
}
