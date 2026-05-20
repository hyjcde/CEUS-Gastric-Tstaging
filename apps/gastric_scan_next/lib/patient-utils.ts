import { ConceptState, DEFAULT_STATE, Patient, ConceptFeatures } from '@/types';
import {
  enrichConceptFeaturesFromClinical,
  parseConceptNumericValue,
  parseInvasionFlag,
} from '@/lib/concept-extract';

function parseDifferentiation(value?: string): number {
  if (!value) return DEFAULT_STATE.differentiation;

  const cleaned = value.toString().trim().toLowerCase();

  if (cleaned.includes('1') || cleaned.includes('well') || cleaned.includes('高分化')) return 1;
  if (cleaned.includes('2') || cleaned.includes('mod') || cleaned.includes('中分化')) return 2;
  if (cleaned.includes('3') || cleaned.includes('mod-poor') || cleaned.includes('中-低')) return 3;
  if (cleaned.includes('4') || cleaned.includes('poor') || cleaned.includes('低分化')) return 4;

  return 5;
}

function parseLauren(value?: string): number {
  if (!value) return DEFAULT_STATE.lauren;

  const cleaned = value.toString().trim().toLowerCase();

  if (cleaned.includes('0') || cleaned.includes('diffuse') || cleaned.includes('弥漫')) return 0;
  if (cleaned.includes('1') || cleaned.includes('intestinal') || cleaned.includes('肠型')) return 1;
  if (cleaned.includes('4') || cleaned.includes('mixed') || cleaned.includes('混合')) return 4;

  return 1;
}

function applyFeature(
  state: ConceptState,
  key: keyof ConceptState,
  parsed: number | null,
) {
  if (parsed === null || Number.isNaN(parsed)) return;
  switch (key) {
    case 'c1': state.c1 = parsed; break;
    case 'c2': state.c2 = parsed; break;
    case 'c3': state.c3 = parsed; break;
    case 'c4': state.c4 = parsed; break;
    case 'c5': state.c5 = parsed; break;
    case 'c6': state.c6 = parsed; break;
    case 'c7': state.c7 = parsed; break;
    case 'differentiation': state.differentiation = parsed; break;
    case 'lauren': state.lauren = parsed; break;
    case 'vascularInvasion': state.vascularInvasion = parsed; break;
    case 'neuralInvasion': state.neuralInvasion = parsed; break;
    default: break;
  }
}

function buildStateFromFeatures(features: ConceptFeatures): ConceptState {
  const state: ConceptState = { ...DEFAULT_STATE };

  applyFeature(state, 'c1', parseConceptNumericValue(features.ki67, 'ihc'));
  applyFeature(state, 'c2', parseConceptNumericValue(features.cps, 'cps'));
  applyFeature(state, 'c3', parseConceptNumericValue(features.pd1, 'ihc'));
  applyFeature(state, 'c4', parseConceptNumericValue(features.foxp3, 'ihc'));
  applyFeature(state, 'c5', parseConceptNumericValue(features.cd3, 'ihc'));
  applyFeature(state, 'c6', parseConceptNumericValue(features.cd4, 'ihc'));
  applyFeature(state, 'c7', parseConceptNumericValue(features.cd8, 'ihc'));

  if (features.differentiation) {
    state.differentiation = parseDifferentiation(features.differentiation);
  }
  if (features.lauren) {
    state.lauren = parseLauren(features.lauren);
  }

  applyFeature(state, 'vascularInvasion', parseInvasionFlag(features.vascular));
  applyFeature(state, 'neuralInvasion', parseInvasionFlag(features.neural));

  return state;
}

/**
 * 从患者临床数据构建 CBM ConceptState。
 * 优先使用 concept_features + 病理报告补全；缺失项保留 DEFAULT_STATE 而非 0。
 */
export function getConceptStateFromPatient(patient: Patient | null): ConceptState {
  if (!patient?.clinical) {
    return { ...DEFAULT_STATE };
  }

  const clinicalRecord = patient.clinical as unknown as Record<string, unknown>;
  const featuresFromClinical = patient.clinical.concept_features;
  const enriched = enrichConceptFeaturesFromClinical({
    ...clinicalRecord,
    concept_features: featuresFromClinical,
    differentiation: patient.clinical.differentiation,
    lauren: patient.clinical.lauren,
  });

  if (!enriched) {
    return {
      ...DEFAULT_STATE,
      differentiation: parseDifferentiation(patient.clinical.differentiation),
      lauren: parseLauren(patient.clinical.lauren),
    };
  }

  return buildStateFromFeatures(enriched);
}

export function countPopulatedConceptFields(state: ConceptState): number {
  const keys: (keyof ConceptState)[] = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7'];
  return keys.filter((key) => state[key] !== DEFAULT_STATE[key]).length;
}
