export const GC_US_REPORT_TEMPLATE_ID = 'gc_us_t_report_template_v1' as const;
export const GC_US_REPORT_SCHEMA_VERSION = 'gc_us_report_signs_v1' as const;
export const GC_US_REPORT_SOURCE_DOC = '胃充盈超声报告模板.docx' as const;

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

export type GcUsStageBand = 'T1' | 'T2' | 'T3' | 'T4' | 'T4a' | 'T4b' | 'uncertain';

export type GcUsField<T> = {
  value: T | null;
  status: GcUsEvidenceStatus;
  source: GcUsEvidenceSource;
  confidence: number | null;
  raw_value: T | null;
  doctor_override: T | null;
  evidence_ref: string[];
  unit?: 'mm' | 'cm' | 'px' | null;
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
  action_type: 'field_edit' | 'template_field_edit' | 'stage_override' | 'reset' | 'revision_start' | 'finalize';
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

export type GcUsTemplateFieldId =
  | 'lesion_site'
  | 'maximum_diameter_cm'
  | 'maximum_thickness_cm'
  | 'gross_type'
  | 'wall_layer_summary'
  | 'layer_1_mucosa'
  | 'layer_2_submucosa'
  | 'layer_3_muscularis'
  | 'layer_4_subserosa'
  | 'layer_5_serosa'
  | 'perigastric_involvement'
  | 'lymph_nodes'
  | 'distant_metastasis'
  | 'ascites'
  | 'ct_stage'
  | 'cn_stage'
  | 'cm_stage'
  | 'impression'
  | 'recommendation';

export type GcUsTemplateFields = {
  lesion_site: GcUsField<string>;
  maximum_diameter_cm: GcUsField<number>;
  maximum_thickness_cm: GcUsField<number>;
  gross_type: GcUsField<string>;
  wall_layer_summary: GcUsField<string>;
  layer_1_mucosa: GcUsField<string>;
  layer_2_submucosa: GcUsField<string>;
  layer_3_muscularis: GcUsField<string>;
  layer_4_subserosa: GcUsField<string>;
  layer_5_serosa: GcUsField<string>;
  perigastric_involvement: GcUsField<string>;
  lymph_nodes: GcUsField<string>;
  distant_metastasis: GcUsField<string>;
  ascites: GcUsField<string>;
  ct_stage: GcUsField<string>;
  cn_stage: GcUsField<string>;
  cm_stage: GcUsField<string>;
  impression: GcUsField<string>;
  recommendation: GcUsField<string>;
};

export type GcUsReportImage = {
  id: string;
  label: string;
  url: string;
  kind: 'original' | 'overlay' | 'roi' | 'wall' | 'evidence' | 'other';
  caption?: string;
  selected?: boolean;
};

export type GcUsReportStatus = 'draft' | 'reviewed' | 'finalized';

export type GcUsReportValidationIssue = {
  code: string;
  severity: 'error' | 'warning';
  field_id: string | null;
  message: string;
};

export type GcUsReportValidationResult = {
  ok: boolean;
  issues: GcUsReportValidationIssue[];
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
  template_fields: GcUsTemplateFields;
  report_images: GcUsReportImage[];
  reference_stage: GcUsReferenceStage;
  report: {
    prose: string;
    source: 'template' | 'ai' | 'doctor';
    doctor_edited: boolean;
    status: GcUsReportStatus;
    report_id: string | null;
    revision: number;
    signed_by: string | null;
    signed_at: string | null;
  };
  conflicts: GcUsConflict[];
  doctor_actions: GcUsDoctorAction[];
};

export const GC_US_CORE_SIGN_DEFINITIONS = [
  { id: 'length', label: '肿瘤长径', group: 'size', kind: 'measurement' },
  { id: 'thickness', label: '肿瘤厚度', group: 'size', kind: 'measurement' },
  { id: 'layer_structure', label: '胃壁层次结构（累及最深）', group: 'wall', kind: 'select' },
  { id: 'morphology', label: '肿瘤形态（并入大体分型）', group: 'lesion', kind: 'select' },
  { id: 'boundary', label: '肿瘤边界（并入层次）', group: 'lesion', kind: 'select' },
  { id: 'growth_pattern', label: '生长方式（并入大体分型）', group: 'growth', kind: 'select' },
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
  T4a: '胃窦后壁见巨大浸润性低回声占位，大小约82×38 mm，呈溃疡浸润型生长，边界明显不规则。病灶累及胃壁全层，固有肌层结构破坏，浆膜连续性中断，并伴胃周脂肪间隙异常改变。未见明确邻近器官侵犯。',
  T4b: '胃窦后壁见巨大浸润性低回声占位，大小约82×38 mm，呈溃疡浸润型生长，边界明显不规则。病灶累及胃壁全层并突破浆膜，可见邻近器官受侵征象。',
};

/**
 * Common 5-layer gastric US anatomy (inside → outside).
 * Field IDs keep legacy names for saved-report compatibility; labels are SSOT.
 */
export const GC_US_WALL_LAYER_SPECS = [
  { id: 'layer_1_mucosa' as const, ordinal: 1, anatomyZh: '黏膜浅层', labelZh: '第一层（黏膜浅层）' },
  { id: 'layer_2_submucosa' as const, ordinal: 2, anatomyZh: '黏膜肌层', labelZh: '第二层（黏膜肌层）' },
  { id: 'layer_3_muscularis' as const, ordinal: 3, anatomyZh: '黏膜下层', labelZh: '第三层（黏膜下层）' },
  { id: 'layer_4_subserosa' as const, ordinal: 4, anatomyZh: '固有肌层', labelZh: '第四层（固有肌层）' },
  { id: 'layer_5_serosa' as const, ordinal: 5, anatomyZh: '浆膜', labelZh: '第五层（浆膜）' },
];

const DISRUPTED_LAYER_STATUSES = new Set(['模糊/变薄', '消失', '角征']);

export type DeepestWallLayerResult = {
  layerId: typeof GC_US_WALL_LAYER_SPECS[number]['id'] | null;
  anatomyZh: string | null;
  status: string | null;
  suggestedBand: Exclude<GcUsStageBand, 'uncertain' | 'T4'> | null;
  layerStructureText: string | null;
  boundaryText: string | null;
  serosaText: string | null;
};

export function deepestInvolvedWallLayer(fields: GcUsTemplateFields): DeepestWallLayerResult {
  let deepest: typeof GC_US_WALL_LAYER_SPECS[number] | null = null;
  let status: string | null = null;
  for (const spec of GC_US_WALL_LAYER_SPECS) {
    const value = normalizedText(fields[spec.id]?.value);
    if (!value || !DISRUPTED_LAYER_STATUSES.has(value)) continue;
    deepest = spec;
    status = value;
  }
  if (!deepest || !status) {
    return {
      layerId: null,
      anatomyZh: null,
      status: null,
      suggestedBand: null,
      layerStructureText: null,
      boundaryText: null,
      serosaText: null,
    };
  }
  const perigastric = normalizedText(fields.perigastric_involvement?.value);
  if (/邻近器官|器官侵犯|胰腺|肝|结肠|横膈/i.test(perigastric)) {
    return {
      layerId: deepest.id,
      anatomyZh: deepest.anatomyZh,
      status,
      suggestedBand: 'T4b',
      layerStructureText: '邻近器官侵犯（T4b）',
      boundaryText: '外侵样改变，边界消失倾向',
      serosaText: '浆膜连续性中断',
    };
  }
  if (deepest.ordinal <= 2) {
    return {
      layerId: deepest.id,
      anatomyZh: deepest.anatomyZh,
      status,
      suggestedBand: 'T1',
      layerStructureText: '黏膜/黏膜下层（T1）',
      boundaryText: status === '消失' ? '边界部分欠清' : '边界清晰、规则',
      serosaText: '浆膜连续光滑',
    };
  }
  if (deepest.ordinal === 3) {
    return {
      layerId: deepest.id,
      anatomyZh: deepest.anatomyZh,
      status,
      suggestedBand: 'T1',
      layerStructureText: '黏膜/黏膜下层（T1）',
      boundaryText: '边界部分欠清',
      serosaText: '浆膜连续光滑',
    };
  }
  if (deepest.ordinal === 4) {
    return {
      layerId: deepest.id,
      anatomyZh: deepest.anatomyZh,
      status,
      suggestedBand: 'T2',
      layerStructureText: '固有肌层（T2）',
      boundaryText: '边界部分欠清',
      serosaText: '浆膜连续光滑',
    };
  }
  if (status === '消失' || status === '角征') {
    return {
      layerId: deepest.id,
      anatomyZh: deepest.anatomyZh,
      status,
      suggestedBand: 'T4a',
      layerStructureText: '浆膜连续性中断（T4a）',
      boundaryText: '外侵样改变，边界消失倾向',
      serosaText: '浆膜连续性中断',
    };
  }
  return {
    layerId: deepest.id,
    anatomyZh: deepest.anatomyZh,
    status,
    suggestedBand: 'T3',
    layerStructureText: '浆膜下层（T3）',
    boundaryText: '边界不规则',
    serosaText: '浆膜面欠光整',
  };
}

const GROSS_TYPE_SIGN_MAP: Record<string, { morphology: string; growth: string }> = {
  表浅型: { morphology: '浅表隆起型', growth: '膨胀型' },
  隆起型: { morphology: '局限隆起型', growth: '膨胀型' },
  局限溃疡型: { morphology: '局部浸润型', growth: '局部浸润性' },
  浸润溃疡型: { morphology: '溃疡浸润型', growth: '明显浸润性' },
  弥漫浸润型: { morphology: '巨大浸润型', growth: '跨壁向外侵犯倾向' },
};

export function syncSignsFromTemplateFields(
  signs: GcUsSigns,
  fields: GcUsTemplateFields,
): GcUsSigns {
  const next = { ...signs, size: { ...signs.size } };
  const gross = normalizedText(fields.gross_type?.value);
  const mapped = gross ? GROSS_TYPE_SIGN_MAP[gross] : null;
  if (mapped) {
    next.morphology = createGcUsField(mapped.morphology, {
      ...signs.morphology,
      value: mapped.morphology,
      status: fields.gross_type.status === 'doctor_edited' ? 'doctor_edited' : signs.morphology.status,
      source: fields.gross_type.source === 'doctor' ? 'doctor' : signs.morphology.source,
      note: '由正式模板大体分型同步',
    });
    next.growth_pattern = createGcUsField(mapped.growth, {
      ...signs.growth_pattern,
      value: mapped.growth,
      status: fields.gross_type.status === 'doctor_edited' ? 'doctor_edited' : signs.growth_pattern.status,
      source: fields.gross_type.source === 'doctor' ? 'doctor' : signs.growth_pattern.source,
      note: '由正式模板大体分型同步',
    });
  }
  const deepest = deepestInvolvedWallLayer(fields);
  if (deepest.layerStructureText) {
    next.layer_structure = createGcUsField(deepest.layerStructureText, {
      ...signs.layer_structure,
      value: deepest.layerStructureText,
      status: 'doctor_edited',
      source: 'doctor',
      note: `由五层勾选同步：累及最深至${deepest.anatomyZh || '未分层'}（${deepest.status}）`,
    });
  }
  if (deepest.boundaryText) {
    next.boundary = createGcUsField(deepest.boundaryText, {
      ...signs.boundary,
      value: deepest.boundaryText,
      status: 'doctor_edited',
      source: 'doctor',
      note: '由正式模板层次勾选同步（边界并入层次）',
    });
  }
  if (deepest.serosaText) {
    next.serosa_change = createGcUsField(deepest.serosaText, {
      ...signs.serosa_change,
      value: deepest.serosaText,
      status: 'doctor_edited',
      source: 'doctor',
      note: '由第五层/胃周勾选同步',
    });
  }
  const peri = normalizedText(fields.perigastric_involvement?.value);
  if (peri) {
    next.perigastric_tissue = createGcUsField(peri, {
      ...signs.perigastric_tissue,
      value: peri,
      status: fields.perigastric_involvement.status === 'doctor_edited' ? 'doctor_edited' : signs.perigastric_tissue.status,
      source: fields.perigastric_involvement.source === 'doctor' ? 'doctor' : signs.perigastric_tissue.source,
    });
  }
  return next;
}

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

export const GC_US_TEMPLATE_FIELD_DEFINITIONS: Array<{
  id: GcUsTemplateFieldId;
  label: string;
  kind: 'number' | 'select' | 'textarea';
  group: 'basic' | 'wall' | 'spread' | 'stage' | 'text';
}> = [
  { id: 'lesion_site', label: '病灶部位', kind: 'select', group: 'basic' },
  { id: 'maximum_diameter_cm', label: '最大径', kind: 'number', group: 'basic' },
  { id: 'maximum_thickness_cm', label: '最大厚度', kind: 'number', group: 'basic' },
  { id: 'gross_type', label: '大体分型', kind: 'select', group: 'basic' },
  { id: 'wall_layer_summary', label: '胃壁层次总评', kind: 'select', group: 'wall' },
  { id: 'layer_1_mucosa', label: '第一层（黏膜浅层）', kind: 'select', group: 'wall' },
  { id: 'layer_2_submucosa', label: '第二层（黏膜肌层）', kind: 'select', group: 'wall' },
  { id: 'layer_3_muscularis', label: '第三层（黏膜下层）', kind: 'select', group: 'wall' },
  { id: 'layer_4_subserosa', label: '第四层（固有肌层）', kind: 'select', group: 'wall' },
  { id: 'layer_5_serosa', label: '第五层（浆膜）', kind: 'select', group: 'wall' },
  { id: 'perigastric_involvement', label: '侵及胃周组织', kind: 'textarea', group: 'spread' },
  { id: 'lymph_nodes', label: '淋巴结', kind: 'textarea', group: 'spread' },
  { id: 'distant_metastasis', label: '远处转移', kind: 'textarea', group: 'spread' },
  { id: 'ascites', label: '腹腔游离液性区', kind: 'select', group: 'spread' },
  { id: 'ct_stage', label: '超声 uT', kind: 'select', group: 'stage' },
  { id: 'cn_stage', label: '超声 N', kind: 'select', group: 'stage' },
  { id: 'cm_stage', label: '超声 M', kind: 'select', group: 'stage' },
  { id: 'impression', label: '超声印象', kind: 'textarea', group: 'text' },
  { id: 'recommendation', label: '检查建议', kind: 'textarea', group: 'text' },
];

export const GC_US_TEMPLATE_SELECT_OPTIONS: Partial<Record<GcUsTemplateFieldId, string[]>> = {
  lesion_site: [
    '贲门',
    '胃底',
    '胃体',
    '胃体（大弯）',
    '胃体（小弯）',
    '胃体（前壁）',
    '胃体（后壁）',
    '胃角',
    '胃窦',
    '胃窦（大弯）',
    '胃窦（小弯）',
    '胃窦（前壁）',
    '胃窦（后壁）',
    '幽门',
  ],
  gross_type: [
    '表浅型',
    '隆起型',
    '局限溃疡型',
    '浸润溃疡型',
    '弥漫浸润型',
  ],
  wall_layer_summary: [
    '层次结构清晰',
    '局部受累，结构尚可辨',
    '固有肌层受累',
    '浆膜下层受累',
    '浆膜连续性可疑破坏',
    '邻近器官侵犯倾向',
  ],
  layer_1_mucosa: ['存在', '模糊/变薄', '消失'],
  layer_2_submucosa: ['存在', '模糊/变薄', '消失'],
  layer_3_muscularis: ['存在', '模糊/变薄', '消失'],
  layer_4_subserosa: ['存在', '模糊/变薄', '消失'],
  layer_5_serosa: ['存在', '模糊/变薄', '消失', '角征'],
  ascites: ['无', '少量', '中量', '大量'],
  ct_stage: ['uT1', 'uT2', 'uT3', 'uT4a', 'uT4b', 'uT4', 'uTx'],
  cn_stage: ['N0', 'N1', 'N2', 'N3', 'Nx'],
  cm_stage: ['M0', 'M1', 'Mx'],
};

const GC_US_REQUIRED_TEMPLATE_FIELDS: Array<{ id: GcUsTemplateFieldId; label: string }> = [
  { id: 'lesion_site', label: '病灶部位' },
  { id: 'maximum_diameter_cm', label: '最大径' },
  { id: 'maximum_thickness_cm', label: '最大厚度' },
  { id: 'gross_type', label: '大体分型' },
  { id: 'wall_layer_summary', label: '胃壁层次总评' },
  { id: 'impression', label: '超声印象' },
];

const GC_US_REVIEW_TEMPLATE_FIELDS: Array<{ id: GcUsTemplateFieldId; label: string }> = [
  { id: 'layer_1_mucosa', label: '第一层（黏膜浅层）' },
  { id: 'layer_2_submucosa', label: '第二层（黏膜肌层）' },
  { id: 'layer_3_muscularis', label: '第三层（黏膜下层）' },
  { id: 'layer_4_subserosa', label: '第四层（固有肌层）' },
  { id: 'layer_5_serosa', label: '第五层（浆膜）' },
  { id: 'perigastric_involvement', label: '侵及胃周组织' },
  { id: 'lymph_nodes', label: '淋巴结' },
  { id: 'distant_metastasis', label: '远处转移' },
  { id: 'ascites', label: '腹腔游离液性区' },
  { id: 'ct_stage', label: '超声 uT' },
  { id: 'cn_stage', label: '超声 N' },
  { id: 'cm_stage', label: '超声 M' },
];

export function createEmptyGcUsTemplateFields(): GcUsTemplateFields {
  return {
    lesion_site: createGcUsField<string>(),
    maximum_diameter_cm: createGcUsField<number>(),
    maximum_thickness_cm: createGcUsField<number>(),
    gross_type: createGcUsField<string>(),
    wall_layer_summary: createGcUsField<string>(),
    layer_1_mucosa: createGcUsField<string>(),
    layer_2_submucosa: createGcUsField<string>(),
    layer_3_muscularis: createGcUsField<string>(),
    layer_4_subserosa: createGcUsField<string>(),
    layer_5_serosa: createGcUsField<string>(),
    perigastric_involvement: createGcUsField<string>(),
    lymph_nodes: createGcUsField<string>(),
    distant_metastasis: createGcUsField<string>(),
    ascites: createGcUsField<string>(),
    ct_stage: createGcUsField<string>(),
    cn_stage: createGcUsField<string>(),
    cm_stage: createGcUsField<string>(),
    impression: createGcUsField<string>(),
    recommendation: createGcUsField<string>(),
  };
}

function clinicalText(clinical: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = normalizedText(clinical[key]);
    if (value) return value;
  }
  return null;
}

function templateTextField(value: string | null, source: GcUsEvidenceSource = 'clinical'): GcUsField<string> {
  return createGcUsField(value, { source });
}

function templateNumberField(value: number | null, unit: 'cm' | null = 'cm'): GcUsField<number> {
  return createGcUsField(value, { source: value == null ? 'not_available' : 'clinical', unit });
}

export function deriveGcUsTemplateFields(input: {
  clinical?: Record<string, unknown>;
  signs?: GcUsSigns;
  referenceStage?: GcUsReferenceStage;
  reportProse?: string;
}): GcUsTemplateFields {
  const clinical = input.clinical || {};
  const signs = input.signs || createEmptyGcUsSigns();
  const referenceStage = input.referenceStage;
  const empty = createEmptyGcUsTemplateFields();
  const lengthMm = signs.size.length.value != null && signs.size.length.unit !== 'px'
    ? Number(signs.size.length.value)
    : clinicalMm(clinical, ['tumor_size_mm', 'length_mm'], ['length_cm'], 'length');
  const thicknessMm = signs.size.thickness.value != null && signs.size.thickness.unit !== 'px'
    ? Number(signs.size.thickness.value)
    : clinicalMm(clinical, ['tumor_thickness_mm', 'thickness_mm'], ['thickness_cm'], 'thickness');
  const stage = referenceStage?.requested_band || referenceStage?.band;
  const stageValue = stage && stage !== 'uncertain' ? `u${stage}` : null;

  return {
    ...empty,
    lesion_site: templateTextField(
      clinicalText(clinical, ['location', 'site', 'lesion_site']),
      'clinical',
    ),
    maximum_diameter_cm: templateNumberField(lengthMm == null ? null : lengthMm / 10),
    maximum_thickness_cm: templateNumberField(thicknessMm == null ? null : thicknessMm / 10),
    gross_type: templateTextField(
      normalizedText(signs.morphology.value) || clinicalText(clinical, ['morphology', 'morphology_pattern']),
      signs.morphology.source || 'clinical',
    ),
    wall_layer_summary: templateTextField(
      normalizedText(signs.layer_structure.value) || clinicalText(clinical, ['layer_structure', 'wall_layer_id']),
      signs.layer_structure.source || 'not_available',
    ),
    layer_5_serosa: templateTextField(
      normalizedText(signs.serosa_change.value) || clinicalText(clinical, ['serosa_status', 'serosa_change']),
      signs.serosa_change.source || 'not_available',
    ),
    perigastric_involvement: templateTextField(
      normalizedText(signs.perigastric_tissue.value) || clinicalText(clinical, ['perigastric_tissue', 'fat_status']),
      signs.perigastric_tissue.source || 'not_available',
    ),
    lymph_nodes: templateTextField(
      clinicalText(clinical, ['lymph_nodes', 'lymph_node_status', 'nodes', 'nodal_status']),
      'clinical',
    ),
    distant_metastasis: templateTextField(
      clinicalText(clinical, ['distant_metastasis', 'metastasis', 'm_stage', 'cm_stage']),
      'clinical',
    ),
    ascites: templateTextField(
      clinicalText(clinical, ['ascites', 'free_fluid', 'peritoneal_fluid']),
      'clinical',
    ),
    ct_stage: templateTextField(stageValue, referenceStage?.source || 'product_score'),
    cn_stage: templateTextField(
      clinicalText(clinical, ['cN', 'cn_stage', 'n_stage', 'clinical_n_stage']),
      'clinical',
    ),
    cm_stage: templateTextField(
      clinicalText(clinical, ['cM', 'cm_stage', 'm_stage', 'clinical_m_stage']),
      'clinical',
    ),
    impression: templateTextField(
      clinicalText(clinical, ['ultrasound_impression', 'impression']) || input.reportProse || null,
      input.reportProse ? 'template_reference' : 'clinical',
    ),
    recommendation: templateTextField(
      clinicalText(clinical, ['recommendation', 'ultrasound_recommendation'])
        || '建议结合胃镜活检及其他影像学资料，必要时进行多切面复核。',
      'template_reference',
    ),
  };
}

function classifyLayer(value: unknown): string | null {
  const raw = normalizedText(value);
  if (!raw) return null;
  if (/不可辨|unreadable|unclear/i.test(raw)) return '不可辨';
  if (/邻近器官|器官侵犯|T4b/i.test(raw)) return '邻近器官侵犯（T4b）';
  if (/浆膜.*(中断|破坏)|连续性.*(中断|破坏)|T4a|L5/i.test(raw)) return '浆膜连续性中断（T4a）';
  if (/中断|破坏|突破|disrupt/i.test(raw)) return '连续性可疑破坏';
  if (/紊乱|destroy/i.test(raw)) return '结构紊乱';
  if (/T3|浆膜下|subserosa/i.test(raw)) return '浆膜下层（T3）';
  if (/T2|固有肌|proper|L4/i.test(raw)) return '固有肌层（T2）';
  if (/T1|L1|L2|L3|黏膜下|黏膜\/黏膜|mucosa|submuc/i.test(raw)) return '黏膜/黏膜下层（T1）';
  if (/局部受累|partial|部分/i.test(raw)) return '局部受累，结构尚可辨';
  if (/完整|清晰|intact|clear/i.test(raw)) return '层次结构清晰';
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
  if (/T4a|uT4a/i.test(raw)) return { band: 'T4a', raw };
  if (/T4b|uT4b/i.test(raw)) return { band: 'T4b', raw };
  if (/T4(?![ab])|uT4(?![ab])/i.test(raw) && !/T4\s*\+/i.test(raw)) {
    // Bare T4 / uT4 remains an aggregate label; subtype unresolved.
    return { band: 'T4', raw, reason: 'T4_subtype_unresolved' };
  }
  const unique = [...new Set([...raw.toUpperCase().matchAll(/T([1-3])/g)].map((match) => `T${match[1]}`))];
  if (unique.length !== 1) return { band: 'uncertain', raw, reason: 'stage_range' };
  return { band: unique[0] as GcUsStageBand, raw };
}

function fieldText(field: GcUsField<unknown>, fallback = '____'): string {
  const value = normalizedText(field.value);
  return value || fallback;
}

function measurementText(field: GcUsField<number>, fallback = '____'): string {
  if (field.value == null || !Number.isFinite(Number(field.value))) return fallback;
  const value = Number(field.value);
  const numberText = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
  if (field.unit === 'px') return `${numberText}像素（非毫米）`;
  return `${numberText} mm`;
}

function normalizedBoundary(value: string): string {
  return value.replace(/^边界/, '').trim() || '____';
}

function normalizedLayer(value: string): string {
  return value.replace(/^胃壁层次|^层次结构/, '').trim() || '____';
}

function normalizedSerosa(value: string): string {
  return value.replace(/^浆膜面?/, '').trim() || '____';
}

function normalizedPerigastric(value: string): string {
  if (value.startsWith('胃周组织')) return value.slice('胃周组织'.length).trim() || '____';
  if (value.startsWith('胃周')) return value.slice('胃周'.length).trim() || '____';
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
  if (length.value == null && thickness.value == null) return '大小约____×____ mm，最大厚度____ mm';
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
  const morphologyPrefix = morphology && morphology !== '____' ? morphology : '';
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
  if (
    (stage === 'T4' || stage === 'T4a' || stage === 'T4b')
    && hasAny(serosa, [/尚光整/, /完整/, /连续光滑/])
    && hasAny(perigastric, [/清晰/, /未见明显/])
  ) {
    conflicts.push({
      code: 't4_without_outer_evidence',
      severity: 'medium',
      fields: ['serosa_change', 'perigastric_tissue'],
      message: '当前浆膜和胃周组织描述未提供明确 T4 外层证据，建议多切面核对。',
    });
  }
  if (stage === 'T4b' && !hasAny(layer, [/邻近器官|器官侵犯|T4b/]) && !hasAny(perigastric, [/邻近器官|器官侵犯|胰腺|肝|结肠|横膈/])) {
    conflicts.push({
      code: 't4b_without_adjacent_evidence',
      severity: 'medium',
      fields: ['layer_structure', 'perigastric_tissue'],
      message: '参考分期为 T4b，但层次/胃周描述未见明确邻近器官侵犯证据。',
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

function normalizeTemplateFields(
  value: unknown,
  fallback: GcUsTemplateFields,
): GcUsTemplateFields {
  const raw = value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  const next = { ...fallback } as GcUsTemplateFields;
  for (const definition of GC_US_TEMPLATE_FIELD_DEFINITIONS) {
    const rawValue = raw[definition.id];
    if (rawValue == null) continue;
    const field = normalizeField<unknown>(rawValue);
    if (
      field.value != null
      || field.status === 'doctor_edited'
      || field.doctor_override != null
      || (rawValue && typeof rawValue === 'object')
    ) {
      (next as unknown as Record<string, GcUsField<unknown>>)[definition.id] = field;
    }
  }
  return next;
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
  const reportInput = (input.report || {}) as Partial<GcUsReportState['report']>;
  const report = {
    prose: reportInput.prose || '',
    source: reportInput.source || 'template',
    doctor_edited: Boolean(reportInput.doctor_edited),
    status: reportInput.status || 'draft',
    report_id: reportInput.report_id || null,
    revision: Number.isFinite(Number(reportInput.revision)) ? Number(reportInput.revision) : 0,
    signed_by: reportInput.signed_by || null,
    signed_at: reportInput.signed_at || null,
  } satisfies GcUsReportState['report'];
  const derivedTemplateFields = deriveGcUsTemplateFields({
    clinical: input.clinical || {},
    signs,
    referenceStage,
    reportProse: report.prose,
  });
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
    template_fields: normalizeTemplateFields(input.template_fields, derivedTemplateFields),
    report_images: Array.isArray(input.report_images)
      ? input.report_images.filter((item): item is GcUsReportImage => (
        Boolean(item)
        && typeof item === 'object'
        && typeof (item as GcUsReportImage).id === 'string'
        && typeof (item as GcUsReportImage).url === 'string'
      ))
      : [],
    reference_stage: referenceStage,
    report,
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
    ? '胃癌可能，超声评估cTx期，浸润深度倾向尚不确定。无经确认的壁层、浆膜或邻近器官证据时不得输出确定 cT。'
    : stage === 'T4'
      ? '胃癌可能，超声评估cT4期（亚型未定；需区分浆膜受侵 T4a 与邻近器官侵犯 T4b）。'
      : `胃癌可能，超声评估c${stage}期。`;
  const advice = conflicts.length
    ? '建议针对冲突征象进行多切面核对，必要时补扫病灶外缘及浆膜区。'
    : '建议结合胃镜活检明确病理性质。当前工作台评估的是 cT，不等于完整 TNM（N=淋巴结，M=远处转移）。';
  const prose = [
    '【超声所见】',
    buildGcUsFindingSentence(state),
    '',
    '【超声印象】',
    '1. 综合超声影像征象及AI辅助分析，考虑：',
    stageLine,
    '2. cT 阶梯提示：T1 黏膜/黏膜下层；T2 固有肌层；T3 浆膜下组织；T4a 浆膜；T4b 邻近器官。正式报告勾选五层：L1 黏膜浅层，L2 黏膜肌层，L3 黏膜下层，L4 固有肌层，L5 浆膜。',
    ...(conflicts.length
      ? [`3. 当前存在需要医生复核的征象冲突：${conflicts.map((item) => item.message).join('；')}`]
      : []),
    '',
    '【建议】',
    `1. ${advice}`,
    '',
    '备注：几何与规则辅助，非病理金标准；最终判断权在医生。频谱、涂鸦、胃腔框代理均不能独立决定 cT。形态/生长方式并入大体分型；边界并入层次勾选。',
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

function templateValue(
  fields: GcUsTemplateFields,
  id: keyof GcUsTemplateFields,
  fallback = '____',
): string {
  const value = fields[id]?.value;
  if (value == null || String(value).trim() === '') return fallback;
  return String(value).trim();
}

function templateNumber(
  fields: GcUsTemplateFields,
  id: 'maximum_diameter_cm' | 'maximum_thickness_cm',
): string {
  const value = fields[id].value;
  if (value == null || !Number.isFinite(Number(value))) return '____';
  return Number(value).toFixed(1).replace(/\.0$/, '');
}

function templateImpressionText(
  fields: GcUsTemplateFields,
  stageText: string,
): string {
  const fallback = stageText
    ? `综合超声影像征象，倾向${stageText}，供医生复核签发。`
    : '综合超声影像征象，浸润深度尚不确定，供医生复核签发。';
  return templateValue(fields, 'impression', fallback);
}

export function buildGcUsTemplateImpression(stateInput: GcUsReportState): string {
  const state = createGcUsReportState(stateInput);
  const stageText = [
    templateValue(state.template_fields, 'ct_stage'),
    templateValue(state.template_fields, 'cn_stage'),
    templateValue(state.template_fields, 'cm_stage'),
  ].filter((value) => value && value !== '____').join(' ');
  return templateImpressionText(state.template_fields, stageText);
}

export function buildGcUsTemplateReportText(stateInput: GcUsReportState): string {
  const state = createGcUsReportState(stateInput);
  const fields = state.template_fields;
  const site = templateValue(fields, 'lesion_site');
  const uT = templateValue(fields, 'ct_stage');
  const n = templateValue(fields, 'cn_stage');
  const m = templateValue(fields, 'cm_stage');
  const impression = templateImpressionText(
    fields,
    [uT, n, m].filter((value) => value && value !== '____').join(' '),
  );

  return [
    '胃癌超声报告',
    '',
    '超声描述：',
    `病灶位于［${site}］；`,
    `最大径 ${templateNumber(fields, 'maximum_diameter_cm')} cm，最厚径 ${templateNumber(fields, 'maximum_thickness_cm')} cm；`,
    `大体分型（${templateValue(fields, 'gross_type')}）`,
    '胃壁层次结构（由内往外）［',
    `第一层（黏膜浅层）（${templateValue(fields, 'layer_1_mucosa')}）、第二层（黏膜肌层）（${templateValue(fields, 'layer_2_submucosa')}）、第三层（黏膜下层）（${templateValue(fields, 'layer_3_muscularis')}）、第四层（固有肌层）（${templateValue(fields, 'layer_4_subserosa')}）、第五层（浆膜）（${templateValue(fields, 'layer_5_serosa')}）］；`,
    `侵及胃周组织 ${templateValue(fields, 'perigastric_involvement')}；`,
    `淋巴结（${templateValue(fields, 'lymph_nodes', '待补充')}）；`,
    `远处转移（${templateValue(fields, 'distant_metastasis', '待补充')}）；`,
    `腹腔游离液性区（${templateValue(fields, 'ascites')}）。`,
    '',
    '超声提示：',
    `${site === '____' ? '________' : site}胃壁 ${impression === '____' ? '________' : impression}`,
    `考虑胃癌（${uT === '____' ? 'uT ____' : uT} ${n === '____' ? 'N ____' : n} ${m === '____' ? 'M ____' : m}）`,
    '',
    '注：',
    '形态、生长方式并入大体分型；边界并入层次结构，细化并勾选累及最深层次。',
    '五层解剖（由内往外）：第一层黏膜浅层，第二层黏膜肌层，第三层黏膜下层，第四层固有肌层，第五层浆膜。',
    '',
    `核心影像征象：${buildGcUsFindingSentence(state)}`,
    '',
    '检查建议：',
    templateValue(fields, 'recommendation', '建议结合胃镜活检及其他影像学资料。'),
    '',
    '说明：本报告按《胃充盈超声报告模板.docx》版式生成，影像辅助结果需由医生复核后签发。',
  ].join('\n');
}

export function buildGcUsTemplateReport(stateInput: GcUsReportState): GcUsReportState {
  const state = createGcUsReportState(stateInput);
  return {
    ...state,
    report: {
      ...state.report,
      prose: buildGcUsTemplateReportText(state),
    },
  };
}

export function validateGcUsReportForFinalize(
  stateInput: GcUsReportState,
): GcUsReportValidationResult {
  const state = createGcUsReportState(stateInput);
  const issues: GcUsReportValidationIssue[] = [];
  const seen = new Set<string>();
  const addIssue = (issue: GcUsReportValidationIssue) => {
    if (seen.has(issue.code)) return;
    seen.add(issue.code);
    issues.push(issue);
  };

  if (!state.report.signed_by?.trim()) {
    addIssue({
      code: 'missing_signed_by',
      severity: 'error',
      field_id: null,
      message: '请填写签发医生。',
    });
  }

  for (const definition of GC_US_REQUIRED_TEMPLATE_FIELDS) {
    const field = state.template_fields[definition.id];
    const value = field?.value;
    const missing = value == null
      || (typeof value === 'string' && value.trim() === '')
      || field?.status === 'unevaluated';
    if (!missing) continue;
    addIssue({
      code: `missing_${definition.id}`,
      severity: 'error',
      field_id: definition.id,
      message: `请补充${definition.label}。`,
    });
  }

  for (const definition of GC_US_REVIEW_TEMPLATE_FIELDS) {
    const field = state.template_fields[definition.id];
    const missing = field?.value == null
      || (typeof field.value === 'string' && field.value.trim() === '')
      || field.status === 'unevaluated';
    if (!missing) continue;
    addIssue({
      code: `unassessed_${definition.id}`,
      severity: 'warning',
      field_id: definition.id,
      message: `${definition.label}尚未明确评估，签发前请确认是否为未评估。`,
    });
  }

  const conflicts = [...state.conflicts, ...state.reference_stage.conflicts];
  for (const conflict of conflicts) {
    const severity = conflict.severity === 'high' ? 'error' : 'warning';
    addIssue({
      code: `conflict_${conflict.code}`,
      severity,
      field_id: conflict.fields[0] || null,
      message: conflict.message || `存在${conflict.code}征象冲突，请复核。`,
    });
  }

  for (const definition of GC_US_TEMPLATE_FIELD_DEFINITIONS) {
    const field = state.template_fields[definition.id];
    if (field?.status !== 'conflict') continue;
    addIssue({
      code: `field_conflict_${definition.id}`,
      severity: 'error',
      field_id: definition.id,
      message: `${definition.label}存在证据冲突，请先复核。`,
    });
  }

  return {
    ok: issues.every((issue) => issue.severity !== 'error'),
    issues,
  };
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
