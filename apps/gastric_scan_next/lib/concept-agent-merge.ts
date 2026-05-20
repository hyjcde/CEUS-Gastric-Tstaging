import { AgentAnalysisResponse, ConceptState, DEFAULT_STATE } from '@/types';

export interface ExplainableAnalysisResult {
  success: boolean;
  patient_id?: string;
  predicted_stage?: string;
  confidence?: string;
  sii?: number;
  bci?: number;
  cri?: number;
  composite_score?: number;
  total_danger_regions?: number;
  morphology?: {
    diameter_mm?: number;
    area_mm2?: number;
    circularity?: number;
    irregularity?: number;
  };
  error?: string;
}

function clamp0_100(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function stageToInvasionScore(stage?: string): number | null {
  if (!stage) return null;
  const normalized = stage.toUpperCase();
  if (normalized.includes('T4')) return 85;
  if (normalized.includes('T3')) return 65;
  if (normalized.includes('T2')) return 45;
  if (normalized.includes('T1')) return 25;
  return null;
}

function penetrationRiskToScore(risk?: string): number {
  const normalized = (risk ?? '').toLowerCase();
  if (normalized.includes('high')) return 1;
  if (normalized.includes('medium') || normalized.includes('moderate')) return 0.55;
  if (normalized.includes('low')) return 0.2;
  return 0;
}

type ConceptKey = keyof ConceptState;

function isClinicalPopulated(clinicalBaseline: ConceptState, key: ConceptKey): boolean {
  return clinicalBaseline[key] !== DEFAULT_STATE[key];
}

function canAutoFill(
  current: ConceptState,
  clinicalBaseline: ConceptState,
  key: ConceptKey,
  skipKeys?: Set<ConceptKey>,
): boolean {
  if (skipKeys?.has(key)) return false;
  if (current[key] !== clinicalBaseline[key]) return false;
  return !isClinicalPopulated(clinicalBaseline, key);
}

function fillIfDefault(
  out: ConceptState,
  current: ConceptState,
  clinicalBaseline: ConceptState,
  key: ConceptKey,
  value: number,
  skipKeys?: Set<ConceptKey>,
) {
  if (!canAutoFill(current, clinicalBaseline, key, skipKeys)) return;
  out[key] = value;
}

/**
 * 将 Agent 超声形态/分期/临床风险证据合并进 CBM 状态。
 * 临床病理已填充的字段不会被覆盖；用户已手动调整的字段也不会被覆盖。
 */
export function mergeAgentIntoConceptState(
  current: ConceptState,
  clinicalBaseline: ConceptState,
  agent: AgentAnalysisResponse,
  skipKeys?: Set<ConceptKey>,
): ConceptState {
  const out: ConceptState = { ...current };
  const evidence = agent.tool_evidence;

  const irregularity = Number(evidence.morphology?.boundary_irregularity);
  if (!Number.isNaN(irregularity)) {
    const scaled = clamp0_100(irregularity <= 1 ? irregularity * 100 : irregularity);
    fillIfDefault(out, current, clinicalBaseline, 'c1', clamp0_100(scaled * 0.65 + DEFAULT_STATE.c1 * 0.35), skipKeys);
  }

  const stage = String(evidence.classification?.top1_stage ?? '');
  const topProb = Number(evidence.classification?.top1_prob);
  const invasionScore = stageToInvasionScore(stage);
  if (invasionScore !== null && !Number.isNaN(topProb)) {
    const prob = topProb <= 1 ? topProb : topProb / 100;
    fillIfDefault(out, current, clinicalBaseline, 'c1', clamp0_100(invasionScore * prob + DEFAULT_STATE.c1 * (1 - prob * 0.5)), skipKeys);
    fillIfDefault(out, current, clinicalBaseline, 'c7', clamp0_100(DEFAULT_STATE.c7 + prob * invasionScore * 0.35), skipKeys);
  }

  const penetrationScore = penetrationRiskToScore(String(evidence.wall_evidence?.penetration_risk ?? ''));
  if (penetrationScore > 0) {
    fillIfDefault(out, current, clinicalBaseline, 'c5', clamp0_100(DEFAULT_STATE.c5 + penetrationScore * 30), skipKeys);
    fillIfDefault(out, current, clinicalBaseline, 'c6', clamp0_100(DEFAULT_STATE.c6 + penetrationScore * 20), skipKeys);
    if (
      canAutoFill(current, clinicalBaseline, 'vascularInvasion', skipKeys) &&
      penetrationScore >= 0.55
    ) {
      out.vascularInvasion = penetrationScore >= 0.9 ? 1 : 0;
    }
  }

  const clinicalRisk = Number(evidence.clinical?.clinical_risk_score);
  if (!Number.isNaN(clinicalRisk)) {
    const risk = clinicalRisk <= 1 ? clinicalRisk * 100 : clinicalRisk;
    fillIfDefault(out, current, clinicalBaseline, 'c2', clamp0_100(risk * 0.35 + DEFAULT_STATE.c2), skipKeys);
    fillIfDefault(out, current, clinicalBaseline, 'c4', clamp0_100(DEFAULT_STATE.c4 + risk * 0.25), skipKeys);
    if (canAutoFill(current, clinicalBaseline, 'differentiation', skipKeys)) {
      out.differentiation = risk > 70 ? 4 : risk > 45 ? 3 : clinicalBaseline.differentiation;
    }
  }

  const convexity = Number(evidence.morphology?.convexity);
  if (!Number.isNaN(convexity)) {
    const morphScore = clamp0_100((1 - Math.min(1, convexity <= 1 ? convexity : convexity / 100)) * 80);
    fillIfDefault(out, current, clinicalBaseline, 'c3', clamp0_100(morphScore * 0.5 + DEFAULT_STATE.c3), skipKeys);
  }

  return out;
}

/**
 * 将可解释边界分析（SII/BCI/CRI）合并进 CBM 状态，规则与 Agent 相同。
 */
export function mergeExplainableIntoConceptState(
  current: ConceptState,
  clinicalBaseline: ConceptState,
  explainable: ExplainableAnalysisResult,
  skipKeys?: Set<ConceptKey>,
): ConceptState {
  if (!explainable.success) return current;

  const out: ConceptState = { ...current };
  const sii = explainable.sii ?? 0;
  const bci = explainable.bci ?? 0;
  const cri = explainable.cri ?? 0;
  const composite = explainable.composite_score ?? 0;
  const irregularity = explainable.morphology?.irregularity;

  fillIfDefault(out, current, clinicalBaseline, 'c1', clamp0_100(sii * 55 + bci * 35 + DEFAULT_STATE.c1 * 0.1), skipKeys);
  fillIfDefault(out, current, clinicalBaseline, 'c3', clamp0_100(cri * 75 + DEFAULT_STATE.c3 * 0.25), skipKeys);
  fillIfDefault(out, current, clinicalBaseline, 'c7', clamp0_100(composite * 60 + DEFAULT_STATE.c7 * 0.4), skipKeys);

  if (typeof irregularity === 'number' && !Number.isNaN(irregularity)) {
    const scaled = clamp0_100(irregularity <= 1 ? irregularity * 100 : irregularity);
    fillIfDefault(out, current, clinicalBaseline, 'c5', clamp0_100(scaled * 0.4 + DEFAULT_STATE.c5), skipKeys);
  }

  const invasionScore = stageToInvasionScore(explainable.predicted_stage);
  if (invasionScore !== null) {
    fillIfDefault(out, current, clinicalBaseline, 'c1', clamp0_100((out.c1 + invasionScore) / 2), skipKeys);
    if (
      canAutoFill(current, clinicalBaseline, 'vascularInvasion', skipKeys) &&
      invasionScore >= 65
    ) {
      out.vascularInvasion = invasionScore >= 85 ? 1 : 0;
    }
  }

  const dangerRegions = explainable.total_danger_regions ?? 0;
  if (dangerRegions > 0) {
    fillIfDefault(out, current, clinicalBaseline, 'c6', clamp0_100(DEFAULT_STATE.c6 + Math.min(dangerRegions * 4, 25)), skipKeys);
  }

  return out;
}

export function countAgentFilledFields(
  before: ConceptState,
  after: ConceptState,
  clinicalBaseline: ConceptState,
): number {
  const keys: ConceptKey[] = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'differentiation', 'vascularInvasion', 'neuralInvasion'];
  return keys.filter((key) => {
    if (after[key] === before[key]) return false;
    if (isClinicalPopulated(clinicalBaseline, key)) return false;
    return true;
  }).length;
}
