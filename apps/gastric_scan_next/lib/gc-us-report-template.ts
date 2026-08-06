export const GC_US_REPORT_TEMPLATE_ID = 'gc_us_t_report_template_v1' as const;
export const GC_US_REPORT_SCHEMA_VERSION = 'gc_us_report_signs_v1' as const;
export const GC_US_REPORT_SOURCE_DOC = 'GC_US_T报告模板_20260803.docx' as const;

export type GcUsEvidenceStatus =
  | 'pending'
  | 'suggested'
  | 'confirmed'
  | 'doctor_edited'
  | 'unevaluated'
  | 'conflict'
  | 'reference_only';

export type GcUsEvidenceSource =
  | 'not_available'
  | 'clinical'
  | 'live_contour'
  | 'pixel'
  | 'model'
  | 'doctor'
  | 'template_reference'
  | 'product_score'
  | 'track_window';

export type GcUsStageBand = 'T1' | 'T2' | 'T3' | 'T4' | 'uncertain';

export type GcUsField<T> = {
  value: T | null;
  status: GcUsEvidenceStatus;
  source: GcUsEvidenceSource;
  confidence: number | null;
  raw_value: T | null;
  doctor_override: T | null;
  evidence_ref: string[];
  unit?: 'mm' | 'px' | null;
  note?: string;
  provenance?: GcUsEvidenceProvenance[];
};

export type GcUsEvidenceProvenance = {
  evidence_id: string;
  source_type: 'doctor_input' | 'image_observed' | 'video_observed' | 'model_inference' | 'derived_rule';
  source_refs: string[];
  frame_id_or_time: string | number | null;
  model_version: string | null;
  rule_version: string;
  actor_id: string | null;
  created_at: string;
};

export type GcUsDoctorAction = {
  action_id: string;
  action_type: 'field_edit' | 'stage_override' | 'reset';
  field_id: string | null;
  suggestion_id: string | null;
  before_value: unknown;
  after_value: unknown;
  reason: string | null;
  evidence_ids: string[];
  source_refs: string[];
  frame_id_or_time: string | number | null;
  actor_id: string | null;
  software_version: string;
  model_version: string | null;
  rule_version: string;
  created_at: string;
};

export type GcUsSigns = {
  size: {
    length: GcUsField<number>;
    thickness: GcUsField<number>;
  };
  layer_structure: GcUsField<string>;
  morphology: GcUsField<string>;
  boundary: GcUsField<string>;
  growth_pattern: GcUsField<string>;
  serosa_change: GcUsField<string>;
  perigastric_tissue: GcUsField<string>;
  lesion_echo: GcUsField<string>;
};

export type GcUsConflict = {
  code: string;
  severity: 'low' | 'medium' | 'high';
  fields: string[];
  message: string;
};

export type GcUsReferenceStage = {
  band: GcUsStageBand;
  requested_band?: GcUsStageBand;
  raw: string | null;
  source: GcUsEvidenceSource;
  conflicts: GcUsConflict[];
};

export type GcUsReportState = {
  schema_version: typeof GC_US_REPORT_SCHEMA_VERSION;
  template_id: typeof GC_US_REPORT_TEMPLATE_ID;
  source_doc: typeof GC_US_REPORT_SOURCE_DOC;
  case_id: string | null;
  frame_id: string | null;
  frame_time: number | null;
  clinical: Record<string, unknown>;
  signs: GcUsSigns;
  reference_stage: GcUsReferenceStage;
  report: {
    prose: string;
    source: 'template' | 'ai' | 'doctor';
    doctor_edited: boolean;
  };
  conflicts: GcUsConflict[];
  doctor_actions: GcUsDoctorAction[];
};

export const GC_US_CORE_SIGN_DEFINITIONS = [
  { id: 'length', label: '肿瘤长径', group: 'size', kind: 'measurement' },
  { id: 'thickness', label: '肿瘤厚度', group: 'size', kind: 'measurement' },
  { id: 'layer_structure', label: '胃壁层次结构', group: 'wall', kind: 'select' },
  { id: 'morphology', label: '肿瘤形态', group: 'lesion', kind: 'select' },
  { id: 'boundary', label: '肿瘤边界', group: 'lesion', kind: 'select' },
  { id: 'growth_pattern', label: '生长方式', group: 'growth', kind: 'select' },
  { id: 'serosa_change', label: '浆膜改变', group: 'serosa', kind: 'select' },
] as const;

export const GC_US_SIGN_DEFINITIONS = [
  ...GC_US_CORE_SIGN_DEFINITIONS,
  { id: 'perigastric_tissue', label: '胃周组织', group: 'serosa', kind: 'select' },
] as const;

export const GC_US_STAGE_EXAMPLES: Record<Exclude<GcUsStageBand, 'uncertain'>, string> = {
  T1: '胃窦后壁见低回声占位性病变，大小约18×7 mm，呈浅表隆起型，边界清晰，局限累及黏膜及黏膜下层，肌层结构完整，浆膜连续光滑。',
  T2: '胃窦后壁见低回声占位性病变，大小约35×16 mm，呈局部浸润性生长，边界部分欠清。病灶累及胃壁固有肌层，浆膜连续完整，未见明确胃周脂肪浸润及邻近器官侵犯征象。',
  T3: '胃窦后壁见浸润性低回声占位性病变，大小约58×26 mm，呈溃疡浸润型生长，边界不规则。病灶累及胃壁全层，突破固有肌层并侵犯浆膜下层，浆膜面局部毛糙但连续性尚存，未见明确胃外器官侵犯征象。',
  T4: '胃窦后壁见巨大浸润性低回声占位，大小约82×38 mm，呈溃疡浸润型生长，边界明显不规则。病灶累及胃壁全层，固有肌层结构破坏，浆膜连续性中断，并伴胃周脂肪间隙异常改变。未见明确邻近器官侵犯。',
};

function isBlank(value: unknown): boolean {
  return value == null || (typeof value === 'string' && value.trim() === '');
}

function normalizedText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'object' && !Array.isArray(value)) {
    const objectValue = value as Record<string, unknown>;
    return normalizedText(objectValue.label ?? objectValue.status ?? objectValue.value);
  }
  return String(value).trim();
}

function firstValue(...values: unknown[]): unknown {
  return values.find((value) => !isBlank(value)) ?? null;
}

function positiveNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function nestedTumorSize(clinical: Record<string, unknown>): Record<string, unknown> {
  const value = clinical.tumorSize;
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function clinicalMm(
  clinical: Record<string, unknown>,
  mmKeys: string[],
  cmKeys: string[],
  nestedKey: 'length' | 'thickness',
): number | null {
  for (const key of mmKeys) {
    const value = positiveNumber(clinical[key]);
    if (value != null) return value;
  }
  for (const key of cmKeys) {
    const value = positiveNumber(clinical[key]);
    if (value != null) return value * 10;
  }
  const nested = positiveNumber(nestedTumorSize(clinical)[nestedKey]);
  return nested == null ? null : nested * 10;
}

export function createGcUsField<T>(
  value: T | null = null,
  options: Partial<GcUsField<T>> = {},
): GcUsField<T> {
  const hasValue = !isBlank(value);
  return {
    value: hasValue ? value : null,
    status: options.status || (hasValue ? 'suggested' : 'unevaluated'),
    source: options.source || (hasValue ? 'model' : 'not_available'),
    confidence: options.confidence ?? null,
    raw_value: options.raw_value ?? (hasValue ? value : null),
    doctor_override: options.doctor_override ?? null,
    evidence_ref: options.evidence_ref || [],
    unit: options.unit ?? null,
    note: options.note || '',
    provenance: options.provenance || [],
  };
}

export function createEmptyGcUsSigns(): GcUsSigns {
  return {
    size: {
      length: createGcUsField<number>(),
      thickness: createGcUsField<number>(),
    },
    layer_structure: createGcUsField<string>(),
    morphology: createGcUsField<string>(),
    boundary: createGcUsField<string>(),
    growth_pattern: createGcUsField<string>(),
    serosa_change: createGcUsField<string>(),
    perigastric_tissue: createGcUsField<string>(),
    lesion_echo: createGcUsField<string>(),
  };
}

function classifyLayer(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/不可辨|unreadable|unclear/i.test(raw)) return '不可辨';
  if (/中断|破坏|突破|邻近器官|disrupt/i.test(raw)) return '连续性可疑破坏';
  if (/紊乱|destroy/i.test(raw)) return '结构紊乱';
  if (/固有肌|partial|部分/i.test(raw)) return '局部受累，结构尚可辨';
  if (/完整|清晰|intact|clear/i.test(raw)) return '层次结构清晰';
  if (/T4|L5|浆膜|serosa/i.test(raw)) return '连续性可疑破坏';
  if (/T3|肌层|muscle/i.test(raw)) return '结构紊乱';
  if (/T2|proper|L4/i.test(raw)) return '局部受累，结构尚可辨';
  if (/T1|L1|L2|L3|黏膜|黏膜下|mucosa|submuc/i.test(raw)) return '层次结构清晰';
  return raw;
}

function classifyBoundary(value: unknown): string | null {
  if (typeof value === 'number' || (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value)))) {
    const irregularity = Number(value);
    if (irregularity >= 3.58) return '边界不规则';
    if (irregularity > 3.15) return '边界部分欠清';
    return '边界清晰、规则';
  }
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/外侵|边界消失/.test(raw)) return '外侵样改变，边界消失倾向';
  if (/不规则/.test(raw)) return '边界不规则';
  if (/模糊|欠清|partial_blur|blurred/i.test(raw)) return '边界部分欠清';
  if (/清晰|规则|clear/i.test(raw)) return '边界清晰、规则';
  return raw;
}

function classifyGrowth(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/T4|T3/i.test(raw)) return '明显浸润性';
  if (/T2/i.test(raw)) return '局部浸润性';
  if (/T1/i.test(raw)) return '膨胀型';
  if (/跨壁|外侵|transmur|extra/i.test(raw)) return '跨壁向外侵犯倾向';
  if (/明显浸润|溃疡|infiltr/i.test(raw)) return '明显浸润性';
  if (/局部浸润|local/i.test(raw)) return '局部浸润性';
  if (/膨胀|隆起|expans/i.test(raw)) return '膨胀型';
  return raw.replace(/生长方式?$/, '').replace(/生长$/, '');
}

function classifySerosa(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/中断|破坏|break|interrupt/i.test(raw)) return '浆膜连续性中断';
  if (/可疑|欠光整|毛糙|ill|suspicious/i.test(raw)) return '浆膜面欠光整';
  if (/完整|连续|光整|intact/i.test(raw)) return '浆膜连续光滑';
  if (/T4/i.test(raw)) return '浆膜连续性可疑破坏';
  if (/T3/i.test(raw)) return '浆膜面欠光整';
  if (/T1|T2/i.test(raw)) return '浆膜连续光滑';
  return raw;
}

function classifyPerigastric(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/模糊|异常|浸润|abnormal|unclear/i.test(raw)) return '胃周脂肪间隙异常改变';
  if (/欠清|suspicious/i.test(raw)) return '胃周脂肪间隙欠清';
  if (/清晰|未见|clear/i.test(raw)) return '胃周组织未见明显异常改变';
  return raw;
}

function classifyMorphology(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/巨大浸润/.test(raw)) return '巨大浸润型';
  if (/溃疡.*浸润|浸润.*溃疡/.test(raw)) return '溃疡浸润型';
  if (/浅表隆起/.test(raw)) return '浅表隆起型';
  if (/局限隆起/.test(raw)) return '局限隆起型';
  if (/局部浸润/.test(raw)) return '局部浸润型';
  return raw;
}

function classifyEcho(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/低回声|hypoechoic/i.test(raw)) return '低回声';
  if (/高回声|hyperechoic/i.test(raw)) return '高回声';
  if (/等回声|isoechoic/i.test(raw)) return '等回声';
  return null;
}

export type GcUsDeriveInput = {
  caseId?: string | null;
  frameId?: string | null;
  frameTime?: number | null;
  clinical?: Record<string, unknown>;
  lesion?: {
    lengthMm?: number | null;
    thicknessMm?: number | null;
    lengthPx?: number | null;
    thicknessPx?: number | null;
    echo?: string | null;
    morphology?: string | null;
    boundary?: string | number | null;
    growthPattern?: string | null;
    serosaChange?: string | null;
    perigastricTissue?: string | null;
  };
  layer?: {
    label?: string | null;
    tHint?: string | null;
    inContact?: boolean | null;
    confidence?: number | null;
  };
  pixel?: Record<string, unknown>;
  evidenceRef?: string[];
};

export function deriveGcUsSigns(input: GcUsDeriveInput): GcUsSigns {
  const clinical = input.clinical || {};
  const lesion = input.lesion || {};
  const layer = input.layer || {};
  const pixel = input.pixel || {};
  const refs = input.evidenceRef || [];
  const signs = createEmptyGcUsSigns();

  const lengthMm = positiveNumber(input.lesion?.lengthMm)
    ?? clinicalMm(clinical, ['tumor_size_mm', 'length_mm', 'tumorSizeMm'], ['length_cm', 'tumor_size_cm'], 'length');
  const thicknessMm = positiveNumber(input.lesion?.thicknessMm)
    ?? clinicalMm(clinical, ['tumor_thickness_mm', 'thickness_mm', 'tumorThicknessMm'], ['thickness_cm', 'tumor_thickness_cm'], 'thickness');
  const lengthPx = positiveNumber(input.lesion?.lengthPx);
  const thicknessPx = positiveNumber(input.lesion?.thicknessPx);

  signs.size.length = createGcUsField(Number(lengthMm ?? lengthPx) || null, {
    unit: lengthMm != null ? 'mm' : lengthPx != null ? 'px' : null,
    source: lengthMm != null ? 'clinical' : lengthPx != null ? 'live_contour' : 'not_available',
    evidence_ref: [...refs, lengthMm != null ? 'clinical.tumor_size' : 'lesion.lengthPx'],
    note: lengthMm == null && lengthPx != null ? '像素值，不等同于毫米' : '',
  });
  signs.size.thickness = createGcUsField(Number(thicknessMm ?? thicknessPx) || null, {
    unit: thicknessMm != null ? 'mm' : thicknessPx != null ? 'px' : null,
    source: thicknessMm != null ? 'clinical' : thicknessPx != null ? 'live_contour' : 'not_available',
    evidence_ref: [...refs, thicknessMm != null ? 'clinical.tumor_thickness' : 'lesion.thicknessPx'],
    note: thicknessMm == null && thicknessPx != null ? '像素值，不等同于毫米' : '',
  });

  const layerValue = classifyLayer(firstValue(layer.label, layer.tHint, clinical.layer_structure, clinical.wall_layer_id));
  signs.layer_structure = createGcUsField(layerValue, {
    source: layer.label || layer.tHint ? 'model' : 'not_available',
    confidence: layer.confidence ?? null,
    evidence_ref: [...refs, 'layer_result'],
  });
  signs.morphology = createGcUsField(
    classifyMorphology(firstValue(lesion.morphology, clinical.morphology, clinical.morphology_pattern, pixel.morphology)),
    { source: lesion.morphology || clinical.morphology ? 'clinical' : 'pixel', evidence_ref: [...refs, 'lesion.morphology'] },
  );
  signs.boundary = createGcUsField(
    classifyBoundary(firstValue(lesion.boundary, clinical.boundary, pixel.boundary, pixel.irregularity)),
    { source: lesion.boundary || clinical.boundary ? 'clinical' : 'pixel', evidence_ref: [...refs, 'lesion.boundary'] },
  );
  signs.growth_pattern = createGcUsField(
    classifyGrowth(firstValue(lesion.growthPattern, clinical.us_growth_pattern, clinical.growth_pattern_us, pixel.growth, layer.tHint)),
    { source: clinical.us_growth_pattern || clinical.growth_pattern_us ? 'clinical' : 'model', evidence_ref: [...refs, 'growth'] },
  );
  signs.serosa_change = createGcUsField(
    classifySerosa(firstValue(lesion.serosaChange, clinical.serosa_status, clinical.serosa_change, pixel.serosa, layer.tHint)),
    { source: clinical.serosa_status || clinical.serosa_change ? 'doctor' : 'pixel', evidence_ref: [...refs, 'serosa'] },
  );
  signs.perigastric_tissue = createGcUsField(
    classifyPerigastric(firstValue(lesion.perigastricTissue, clinical.perigastric_tissue, clinical.fat_status, pixel.peritumoral_fat)),
    { source: clinical.perigastric_tissue || clinical.fat_status ? 'doctor' : 'pixel', evidence_ref: [...refs, 'peritumoral_fat'] },
  );
  signs.lesion_echo = createGcUsField(
    classifyEcho(firstValue(lesion.echo, clinical.echo, pixel.echo)),
    { source: lesion.echo || clinical.echo || pixel.echo ? 'pixel' : 'not_available', evidence_ref: [...refs, 'echo'] },
  );
  return signs;
}

export function normalizeGcUsStage(value: unknown): {
  band: GcUsStageBand;
  raw: string | null;
  reason?: string;
} {
  const raw = normalizedText(value);
  if (!raw) return { band: 'uncertain', raw: null };
  if (/T4\s*\+/i.test(raw)) return { band: 'uncertain', raw, reason: 'T4+' };
  const unique = [...new Set([...raw.toUpperCase().matchAll(/T([1-4])/g)].map((match) => `T${match[1]}`))];
  if (unique.length !== 1) return { band: 'uncertain', raw, reason: 'stage_range' };
  return { band: unique[0] as GcUsStageBand, raw };
}

function fieldText(field: GcUsField<unknown>, fallback = '未评估'): string {
  const value = normalizedText(field.value);
  return value || fallback;
}

function measurementText(field: GcUsField<number>, fallback = '未评估'): string {
  if (field.value == null || !Number.isFinite(Number(field.value))) return fallback;
  const value = Number(field.value);
  const numberText = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
  if (field.unit === 'px') return `${numberText}像素（非毫米）`;
  return `${numberText} mm`;
}

function normalizedBoundary(value: string): string {
  return value.replace(/^边界/, '').trim() || '未评估';
}

function normalizedLayer(value: string): string {
  return value.replace(/^胃壁层次|^层次结构/, '').trim() || '未评估';
}

function normalizedSerosa(value: string): string {
  return value.replace(/^浆膜面?/, '').trim() || '未评估';
}

function normalizedPerigastric(value: string): string {
  if (value.startsWith('胃周组织')) return value.slice('胃周组织'.length).trim() || '未评估';
  if (value.startsWith('胃周')) return value.slice('胃周'.length).trim() || '未评估';
  return value;
}

function buildSizePhrase(state: GcUsReportState): string {
  const length = state.signs.size.length;
  const thickness = state.signs.size.thickness;
  const hasMillimeterPair = length.value != null && thickness.value != null
    && length.unit !== 'px' && thickness.unit !== 'px';
  if (hasMillimeterPair) {
    const l = measurementText(length).replace(/ mm$/, '');
    const t = measurementText(thickness).replace(/ mm$/, '');
    return `大小约${l}×${t} mm，最大厚度${t} mm`;
  }
  if (length.value == null && thickness.value == null) return '大小及最大厚度未评估';
  return `大小约${measurementText(length)}×${measurementText(thickness)}，最大厚度${measurementText(thickness)}`;
}

export function buildGcUsFindingSentence(state: GcUsReportState): string {
  const site = normalizedText(state.clinical.location || state.clinical.site);
  const location = site ? `${site}见` : '胃壁见';
  const morphology = fieldText(state.signs.morphology, '');
  const echo = fieldText(state.signs.lesion_echo, '低回声');
  const lesionNoun = /占位|肿块|病变/.test(echo) ? echo : `${echo}占位性病变`;
  const boundary = normalizedBoundary(fieldText(state.signs.boundary));
  const growth = fieldText(state.signs.growth_pattern);
  const layer = normalizedLayer(fieldText(state.signs.layer_structure));
  const serosa = normalizedSerosa(fieldText(state.signs.serosa_change));
  const perigastric = normalizedPerigastric(fieldText(state.signs.perigastric_tissue));
  const morphologyPrefix = morphology && morphology !== '未评估' ? morphology : '';
  return `${location}${morphologyPrefix}${lesionNoun}，${buildSizePhrase(state)}。病灶呈${growth}生长方式，边界${boundary}。胃壁层次表现为${layer}，浆膜表现${serosa}，胃周组织${perigastric}。`;
}

function hasAny(value: string, patterns: RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(value));
}

export function detectGcUsConflicts(signs: GcUsSigns, stage: GcUsStageBand): GcUsConflict[] {
  const conflicts: GcUsConflict[] = [];
  const layer = fieldText(signs.layer_structure, '');
  const serosa = fieldText(signs.serosa_change, '');
  const boundary = fieldText(signs.boundary, '');
  const perigastric = fieldText(signs.perigastric_tissue, '');

  if ((stage === 'T1' || stage === 'T2') && hasAny(layer, [/破坏/, /中断/, /突破/, /邻近器官/])) {
    conflicts.push({
      code: 'deep_layer_vs_low_stage',
      severity: 'high',
      fields: ['layer_structure'],
      message: `${layer}与${stage}参考阶段冲突，需核对层次和多切面证据。`,
    });
  }
  if ((stage === 'T1' || stage === 'T2') && hasAny(serosa, [/中断/, /破坏/, /突破/])) {
    conflicts.push({
      code: 'serosa_break_vs_low_stage',
      severity: 'high',
      fields: ['serosa_change'],
      message: `${serosa}与${stage}参考阶段冲突，不能直接输出确定性低分期。`,
    });
  }
  if ((stage === 'T1' || stage === 'T2') && hasAny(boundary, [/外侵/, /边界消失/])) {
    conflicts.push({
      code: 'invasive_boundary_vs_low_stage',
      severity: 'medium',
      fields: ['boundary'],
      message: `${boundary}提示外侵倾向，与${stage}参考阶段存在冲突。`,
    });
  }
  if (stage === 'T4' && hasAny(serosa, [/尚光整/, /完整/, /连续光滑/]) && hasAny(perigastric, [/清晰/, /未见明显/])) {
    conflicts.push({
      code: 't4_without_outer_evidence',
      severity: 'medium',
      fields: ['serosa_change', 'perigastric_tissue'],
      message: '当前浆膜和胃周组织描述未提供明确 T4 外层证据，建议多切面核对。',
    });
  }
  if (stage !== 'uncertain' && (signs.layer_structure.status === 'unevaluated' || !layer)) {
    conflicts.push({
      code: 'unreadable_layer',
      severity: 'low',
      fields: ['layer_structure'],
      message: '胃壁层次不可评估，当前阶段只能作为软倾向参考。',
    });
  }
  return conflicts;
}

function normalizeField<T>(value: unknown): GcUsField<T> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const source = value as Partial<GcUsField<T>> & { value?: T | null };
    return createGcUsField(source.value ?? null, source);
  }
  return createGcUsField((value ?? null) as T | null);
}

export function createGcUsReportState(
  input: Partial<GcUsReportState> & { signs?: Partial<GcUsSigns> } = {},
): GcUsReportState {
  const empty = createEmptyGcUsSigns();
  const rawSigns = (input.signs || {}) as Partial<GcUsSigns>;
  const rawSize = (rawSigns.size || {}) as Partial<GcUsSigns['size']>;
  const signs: GcUsSigns = {
    size: {
      length: normalizeField<number>(rawSize.length),
      thickness: normalizeField<number>(rawSize.thickness),
    },
    layer_structure: normalizeField<string>(rawSigns.layer_structure),
    morphology: normalizeField<string>(rawSigns.morphology),
    boundary: normalizeField<string>(rawSigns.boundary),
    growth_pattern: normalizeField<string>(rawSigns.growth_pattern),
    serosa_change: normalizeField<string>(rawSigns.serosa_change),
    perigastric_tissue: normalizeField<string>(rawSigns.perigastric_tissue),
    lesion_echo: normalizeField<string>(rawSigns.lesion_echo),
  };
  const rawReference = (input.reference_stage || {}) as Partial<GcUsReferenceStage>;
  const normalizedReference = normalizeGcUsStage(
    rawReference.requested_band || rawReference.band || rawReference.raw,
  );
  const normalizedBand = normalizeGcUsStage(rawReference.band);
  const referenceStage: GcUsReferenceStage = {
    band: rawReference.band ? normalizedBand.band : normalizedReference.band,
    requested_band: rawReference.requested_band
      ? normalizeGcUsStage(rawReference.requested_band).band
      : normalizedReference.band,
    raw: rawReference.raw ?? normalizedReference.raw,
    source: rawReference.source || 'product_score',
    conflicts: rawReference.conflicts || [],
  };
  return {
    schema_version: GC_US_REPORT_SCHEMA_VERSION,
    template_id: GC_US_REPORT_TEMPLATE_ID,
    source_doc: GC_US_REPORT_SOURCE_DOC,
    case_id: input.case_id || null,
    frame_id: input.frame_id || null,
    frame_time: input.frame_time ?? null,
    clinical: input.clinical || {},
    signs: {
      ...empty,
      ...signs,
      size: { ...empty.size, ...signs.size },
    },
    reference_stage: referenceStage,
    report: input.report || { prose: '', source: 'template', doctor_edited: false },
    conflicts: input.conflicts || referenceStage.conflicts || [],
    doctor_actions: input.doctor_actions || [],
  };
}

export function buildGcUsReport(
  stateInput: GcUsReportState,
  stageOverride?: GcUsStageBand,
): {
  prose: string;
  structured: GcUsReportState;
  stage: GcUsStageBand;
  conflicts: GcUsConflict[];
} {
  const state = createGcUsReportState(stateInput);
  const requested = stageOverride || state.reference_stage.requested_band || state.reference_stage.band || 'uncertain';
  const conflicts = detectGcUsConflicts(state.signs, requested);
  const stage = conflicts.length ? 'uncertain' : requested;
  const stageLine = stage === 'uncertain'
    ? '胃癌可能，超声评估cTx期，浸润深度倾向尚不确定。'
    : `胃癌可能，超声评估c${stage}期。`;
  const advice = conflicts.length
    ? '建议针对冲突征象进行多切面核对，必要时补扫病灶外缘及浆膜区。'
    : '建议结合胃镜活检明确病理性质。';
  const prose = [
    '【超声所见】',
    buildGcUsFindingSentence(state),
    '',
    '【超声印象】',
    '1. 综合超声影像征象及AI辅助分析，考虑：',
    stageLine,
    ...(conflicts.length
      ? [`2. 当前存在需要医生复核的征象冲突：${conflicts.map((item) => item.message).join('；')}`]
      : []),
    '',
    '【建议】',
    `1. ${advice}`,
    '',
    '备注：几何与规则辅助，非病理金标准；最终判断权在医生。',
  ].join('\n');
  const structured: GcUsReportState = {
    ...state,
    reference_stage: {
      ...state.reference_stage,
      band: stage,
      requested_band: requested,
      conflicts,
    },
    conflicts,
    report: {
      ...state.report,
      prose,
    },
  };
  return { prose, structured, stage, conflicts };
}

export function applyGcUsDoctorOverride<T>(
  field: GcUsField<T>,
  value: T | null,
): GcUsField<T> {
  return {
    ...field,
    value,
    status: 'doctor_edited',
    source: 'doctor',
    raw_value: field.raw_value ?? field.value,
    doctor_override: value,
  };
}
