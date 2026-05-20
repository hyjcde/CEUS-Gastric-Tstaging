import { ConceptFeatures } from '@/types';

/** 从病理/IHC 文本提取 concept_features（与 convert_excel_to_json.py 逻辑对齐） */
export function extractConceptFeaturesFromPathology(pathologyText?: string): ConceptFeatures {
  if (!pathologyText?.trim()) return {};

  const text = pathologyText;
  const features: ConceptFeatures = {};

  const ki67Match = text.match(/Ki67[约约\s]*(\d+(?:\.\d+)?)[%％]?/i);
  if (ki67Match) {
    features.ki67 = `Ki67约${ki67Match[1]}%`;
  }

  const cpsMatch = text.match(/CPS[约约\s<≤]*(\d+(?:\.\d+)?)/i);
  if (cpsMatch) {
    features.cps = text.includes('<') || text.includes('≤')
      ? `CPS<${cpsMatch[1]}`
      : `CPS${cpsMatch[1]}`;
  }

  if (/PD-?1/i.test(text)) {
    features.pd1 = /个别|散在/i.test(text) ? 'PD-1个别阳性' : /阴性/i.test(text) ? 'PD-1阴性' : 'PD-1阳性';
  }
  if (/FoxP3|FOXP3/i.test(text)) {
    features.foxp3 = /个别|散在/i.test(text) ? 'FoxP3个别阳性' : /阴性/i.test(text) ? 'FoxP3阴性' : 'FoxP3阳性';
  }
  if (/CD3/i.test(text)) {
    features.cd3 = /部分|少量/i.test(text) ? 'CD3淋巴细胞部分阳性' : /阴性/i.test(text) ? 'CD3阴性' : 'CD3阳性';
  }
  if (/CD4/i.test(text)) {
    features.cd4 = /部分|少量/i.test(text) ? 'CD4淋巴细胞部分阳性' : /阴性/i.test(text) ? 'CD4阴性' : 'CD4阳性';
  }
  if (/CD8/i.test(text)) {
    features.cd8 = /部分|少量/i.test(text) ? 'CD8淋巴细胞部分阳性' : /阴性/i.test(text) ? 'CD8阴性' : 'CD8阳性';
  }
  if (/脉管/i.test(text)) {
    features.vascular = /未见[^。\n]{0,12}脉管|无[^。\n]{0,8}脉管|脉管[^。\n]{0,8}未见/i.test(text)
      ? '未见脉管侵犯'
      : '脉管内瘤栓';
  }
  if (/神经/i.test(text)) {
    features.neural = /未见[^。\n]{0,12}神经|无[^。\n]{0,8}神经|神经[^。\n]{0,8}未见/i.test(text)
      ? '未见神经侵犯'
      : '神经侵犯';
  }

  return features;
}

export function mergeConceptFeatures(
  primary?: ConceptFeatures,
  fallback?: ConceptFeatures,
): ConceptFeatures {
  return {
    ki67: primary?.ki67 || fallback?.ki67,
    cps: primary?.cps || fallback?.cps,
    pd1: primary?.pd1 || fallback?.pd1,
    foxp3: primary?.foxp3 || fallback?.foxp3,
    cd3: primary?.cd3 || fallback?.cd3,
    cd4: primary?.cd4 || fallback?.cd4,
    cd8: primary?.cd8 || fallback?.cd8,
    vascular: primary?.vascular || fallback?.vascular,
    neural: primary?.neural || fallback?.neural,
    differentiation: primary?.differentiation || fallback?.differentiation,
    lauren: primary?.lauren || fallback?.lauren,
  };
}

/** 解析百分比或 CPS 数值；定性描述映射为 CBM 0-100  surrogate */
export function parseConceptNumericValue(value?: string, kind?: 'ihc' | 'cps'): number | null {
  if (!value?.trim()) return null;

  const cleaned = value.trim();
  const lower = cleaned.toLowerCase();

  if (/阴性|negative|未见|none/i.test(lower)) return kind === 'cps' ? 0 : 5;
  if (/个别|散在|少量|部分|partial|focal/i.test(lower)) return 25;
  if (/阳性|positive|\+/.test(lower) && !/\d/.test(lower)) return 55;

  const ltMatch = cleaned.match(/[<≤]\s*(\d+(?:\.\d+)?)/);
  if (ltMatch) {
    const n = parseFloat(ltMatch[1]);
    return Number.isFinite(n) ? Math.max(0, n - 1) : null;
  }

  const numMatch = cleaned.match(/(\d+(?:\.\d+)?)/);
  if (numMatch) {
    const n = parseFloat(numMatch[1]);
    if (!Number.isFinite(n)) return null;
    return Math.max(0, Math.min(100, n));
  }

  return null;
}

export function parseInvasionFlag(value?: string): number | null {
  if (!value?.trim()) return null;
  const lower = value.toLowerCase();
  if (/未见|无|no|negative|阴性/.test(lower)) return 0;
  if (/侵犯|瘤栓|阳性|yes|\+|有|invad/i.test(lower)) return 1;
  return null;
}

export function enrichConceptFeaturesFromClinical(clinical: Record<string, unknown> | undefined): ConceptFeatures | undefined {
  if (!clinical) return undefined;

  const pathology = clinical.pathology as Record<string, unknown> | undefined;
  const pathologyText = typeof pathology?.type === 'string'
    ? pathology.type
    : typeof clinical.pathology_report === 'string'
      ? clinical.pathology_report
      : '';

  const fromRecord = (clinical.concept_features as ConceptFeatures | undefined) ?? {};
  const fromPathology = extractConceptFeaturesFromPathology(pathologyText);
  const merged = pathologyText.trim()
    ? mergeConceptFeatures(fromPathology, fromRecord)
    : mergeConceptFeatures(fromRecord, fromPathology);

  if (pathology?.differentiation && !merged.differentiation) {
    merged.differentiation = String(pathology.differentiation);
  }
  if (pathology?.lauren && !merged.lauren) {
    merged.lauren = String(pathology.lauren);
  }
  if (clinical.differentiation && !merged.differentiation) {
    merged.differentiation = String(clinical.differentiation);
  }
  if (clinical.lauren && !merged.lauren) {
    merged.lauren = String(clinical.lauren);
  }

  return Object.values(merged).some(Boolean) ? merged : undefined;
}
