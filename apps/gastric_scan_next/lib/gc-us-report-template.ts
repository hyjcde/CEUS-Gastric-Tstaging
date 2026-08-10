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
  kind: 'original' | 'overlay' | 'roi' | 'wall' | 'evidence' | 'keyframe' | 'curvature' | 'analysis' | 'other';
  caption?: string;
  selected?: boolean;
  frame_index?: number | null;
  frame_time?: number | null;
  source_frame_id?: string | null;
  source_video_url?: string | null;
  image_width?: number | null;
  image_height?: number | null;
};

export type GcUsReportStatus = 'draft' | 'reviewed' | 'finalized';
export type GcUsExportMethod = 'pdf' | 'print';

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
    export_method?: GcUsExportMethod | null;
  };
  conflicts: GcUsConflict[];
  doctor_actions: GcUsDoctorAction[];
};

export const GC_US_CORE_SIGN_DEFINITIONS = [
  { id: 'length', label: '肿瘤长径', labelEn: 'Tumor length', group: 'size', kind: 'measurement' },
  { id: 'thickness', label: '肿瘤厚度', labelEn: 'Tumor thickness', group: 'size', kind: 'measurement' },
  { id: 'layer_structure', label: '胃壁层次结构（累及最深）', labelEn: 'Wall layers (deepest involved)', group: 'wall', kind: 'select' },
  { id: 'morphology', label: '肿瘤形态（并入大体分型）', labelEn: 'Morphology (into gross type)', group: 'lesion', kind: 'select' },
  { id: 'boundary', label: '肿瘤边界（并入层次）', labelEn: 'Boundary (into layers)', group: 'lesion', kind: 'select' },
  { id: 'growth_pattern', label: '生长方式（并入大体分型）', labelEn: 'Growth pattern (into gross type)', group: 'growth', kind: 'select' },
  { id: 'serosa_change', label: '浆膜改变', labelEn: 'Serosal change', group: 'serosa', kind: 'select' },
] as const;

export const GC_US_SIGN_DEFINITIONS = [
  ...GC_US_CORE_SIGN_DEFINITIONS,
  { id: 'perigastric_tissue', label: '胃周组织', labelEn: 'Perigastric tissue', group: 'serosa', kind: 'select' },
] as const;

export function gcUsLabel(item: { label: string; labelEn?: string }, zh = true): string {
  return zh ? item.label : (item.labelEn || item.label);
}

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
  { id: 'layer_1_mucosa' as const, ordinal: 1, anatomyZh: '黏膜浅层', anatomyEn: 'Superficial mucosa', labelZh: '第一层（黏膜浅层）', labelEn: 'Layer 1 (superficial mucosa)' },
  { id: 'layer_2_submucosa' as const, ordinal: 2, anatomyZh: '黏膜肌层', anatomyEn: 'Muscularis mucosae', labelZh: '第二层（黏膜肌层）', labelEn: 'Layer 2 (muscularis mucosae)' },
  { id: 'layer_3_muscularis' as const, ordinal: 3, anatomyZh: '黏膜下层', anatomyEn: 'Submucosa', labelZh: '第三层（黏膜下层）', labelEn: 'Layer 3 (submucosa)' },
  { id: 'layer_4_subserosa' as const, ordinal: 4, anatomyZh: '固有肌层', anatomyEn: 'Muscularis propria', labelZh: '第四层（固有肌层）', labelEn: 'Layer 4 (muscularis propria)' },
  { id: 'layer_5_serosa' as const, ordinal: 5, anatomyZh: '浆膜', anatomyEn: 'Serosa', labelZh: '第五层（浆膜）', labelEn: 'Layer 5 (serosa)' },
];

export function gcUsWallLayerLabel(spec: typeof GC_US_WALL_LAYER_SPECS[number], zh = true): string {
  return zh ? spec.labelZh : spec.labelEn;
}

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

export function growthPatternFromGrossType(value: unknown): string {
  return GROSS_TYPE_SIGN_MAP[normalizedText(value)]?.growth || '';
}

/** When five-layer ticks change, rebuild wall_layer_summary so preview stays consistent. */
export function syncWallLayerSummaryFromTicks(fields: GcUsTemplateFields): GcUsTemplateFields {
  const deepest = deepestInvolvedWallLayer(fields);
  if (!deepest.layerStructureText) return fields;
  return {
    ...fields,
    wall_layer_summary: createGcUsField(deepest.layerStructureText, {
      ...fields.wall_layer_summary,
      value: deepest.layerStructureText,
      status: 'doctor_edited',
      source: 'doctor',
      note: `由五层勾选同步：累及最深至${deepest.anatomyZh || '未分层'}（${deepest.status}）`,
    }),
  };
}

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
  labelEn: string;
  kind: 'number' | 'select' | 'textarea';
  group: 'basic' | 'wall' | 'spread' | 'stage' | 'text';
}> = [
  { id: 'lesion_site', label: '病灶部位', labelEn: 'Lesion site', kind: 'select', group: 'basic' },
  { id: 'maximum_diameter_cm', label: '最大径', labelEn: 'Max diameter', kind: 'number', group: 'basic' },
  { id: 'maximum_thickness_cm', label: '最大厚度', labelEn: 'Max thickness', kind: 'number', group: 'basic' },
  { id: 'gross_type', label: '大体分型', labelEn: 'Gross type', kind: 'select', group: 'basic' },
  { id: 'wall_layer_summary', label: '胃壁层次总评', labelEn: 'Wall-layer summary', kind: 'select', group: 'wall' },
  { id: 'layer_1_mucosa', label: '第一层（黏膜浅层）', labelEn: 'Layer 1 (superficial mucosa)', kind: 'select', group: 'wall' },
  { id: 'layer_2_submucosa', label: '第二层（黏膜肌层）', labelEn: 'Layer 2 (muscularis mucosae)', kind: 'select', group: 'wall' },
  { id: 'layer_3_muscularis', label: '第三层（黏膜下层）', labelEn: 'Layer 3 (submucosa)', kind: 'select', group: 'wall' },
  { id: 'layer_4_subserosa', label: '第四层（固有肌层）', labelEn: 'Layer 4 (muscularis propria)', kind: 'select', group: 'wall' },
  { id: 'layer_5_serosa', label: '第五层（浆膜）', labelEn: 'Layer 5 (serosa)', kind: 'select', group: 'wall' },
  { id: 'perigastric_involvement', label: '侵及胃周组织', labelEn: 'Perigastric involvement', kind: 'textarea', group: 'spread' },
  { id: 'lymph_nodes', label: '淋巴结', labelEn: 'Lymph nodes', kind: 'textarea', group: 'spread' },
  { id: 'distant_metastasis', label: '远处转移', labelEn: 'Distant metastasis', kind: 'textarea', group: 'spread' },
  { id: 'ascites', label: '腹腔游离液性区', labelEn: 'Ascites / free fluid', kind: 'select', group: 'spread' },
  { id: 'ct_stage', label: '超声 uT', labelEn: 'Ultrasound uT', kind: 'select', group: 'stage' },
  { id: 'cn_stage', label: '超声 N', labelEn: 'Ultrasound N', kind: 'select', group: 'stage' },
  { id: 'cm_stage', label: '超声 M', labelEn: 'Ultrasound M', kind: 'select', group: 'stage' },
  { id: 'impression', label: '超声印象', labelEn: 'Ultrasound impression', kind: 'textarea', group: 'text' },
  { id: 'recommendation', label: '检查建议', labelEn: 'Recommendations', kind: 'textarea', group: 'text' },
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
  ct_stage: ['uT1', 'uT2', 'uT3', 'uT4a', 'uT4b', 'uT4'],
  cn_stage: ['N0', 'N1', 'N2', 'N3'],
  cm_stage: ['M0', 'M1'],
};

/** Display labels for stored Chinese option tokens (values stay Chinese for SSOT). */
export const GC_US_OPTION_LABEL_EN: Record<string, string> = {
  贲门: 'Cardia',
  胃底: 'Fundus',
  胃体: 'Body',
  '胃体（大弯）': 'Body (greater curvature)',
  '胃体（小弯）': 'Body (lesser curvature)',
  '胃体（前壁）': 'Body (anterior wall)',
  '胃体（后壁）': 'Body (posterior wall)',
  胃角: 'Angle',
  胃窦: 'Antrum',
  '胃窦（大弯）': 'Antrum (greater curvature)',
  '胃窦（小弯）': 'Antrum (lesser curvature)',
  '胃窦（前壁）': 'Antrum (anterior wall)',
  '胃窦（后壁）': 'Antrum (posterior wall)',
  幽门: 'Pylorus',
  大弯: 'Greater curvature',
  小弯: 'Lesser curvature',
  前壁: 'Anterior wall',
  后壁: 'Posterior wall',
  表浅型: 'Superficial',
  隆起型: 'Protruding',
  局限溃疡型: 'Localized ulcerative',
  浸润溃疡型: 'Infiltrative ulcerative',
  弥漫浸润型: 'Diffuse infiltrative',
  '层次结构清晰': 'Layers clear',
  '局部受累，结构尚可辨': 'Focal involvement, structure still recognizable',
  '固有肌层受累': 'Muscularis propria involved',
  '浆膜下层受累': 'Subserosa involved',
  '浆膜连续性可疑破坏': 'Suspected serosal discontinuity',
  '邻近器官侵犯倾向': 'Tendency of adjacent-organ invasion',
  存在: 'Present',
  '模糊/变薄': 'Blurred / thinned',
  消失: 'Absent',
  角征: 'Angular sign',
  无: 'None',
  少量: 'Small',
  中量: 'Moderate',
  大量: 'Large',
  浅表隆起型: 'Superficial elevated',
  局限隆起型: 'Localized elevated',
  局部浸润型: 'Locally infiltrative',
  溃疡浸润型: 'Ulcerative infiltrative',
  巨大浸润型: 'Bulky infiltrative',
  膨胀型: 'Expansile',
  局部浸润性: 'Locally infiltrative',
  明显浸润性: 'Frankly infiltrative',
  跨壁向外侵犯倾向: 'Transmural outward invasion tendency',
  '边界清晰、规则': 'Clear and regular',
  边界清晰: 'Clear',
  边界部分欠清: 'Partially ill-defined',
  边界不规则: 'Irregular',
  // Stripped forms used by Chinese finding-sentence grammar helpers.
  '清晰、规则': 'Clear and regular',
  部分欠清: 'Partially ill-defined',
  不规则: 'Irregular',
  '外侵样改变，边界消失倾向': 'Invasive appearance with margin fading',
  '外侵样改变，消失倾向': 'Invasive appearance with margin fading',
  '浆膜连续光滑': 'Serosa continuous and smooth',
  '浆膜面欠光整': 'Serosal surface irregular',
  '浆膜连续性中断': 'Serosal discontinuity',
  '浆膜连续': 'Serosa continuous',
  连续光滑: 'Continuous and smooth',
  连续性中断: 'Discontinuity',
  面欠光整: 'Surface irregular',
  '黏膜/黏膜下层（T1）': 'mucosa / submucosa (T1)',
  '固有肌层（T2）': 'muscularis propria (T2)',
  '浆膜下层（T3）': 'subserosa (T3)',
  '浆膜连续性中断（T4a）': 'serosal discontinuity (T4a)',
  '邻近器官侵犯（T4b）': 'adjacent-organ invasion (T4b)',
  '胃壁层次结构相对完整': 'wall layers relatively preserved',
  '固有肌层受累/结构破坏': 'muscularis propria involved / disrupted',
  '当前帧层次显示有限，需多切面复核': 'Limited layer visibility on this frame; multi-plane review needed',
  '请先勾画胃腔以定向胃壁后再评估层次': 'Draw the lumen first to orient the wall, then assess layers',
  '当前帧浆膜连续性需多切面核对': 'Serosal continuity on this frame needs multi-plane review',
  '当前帧胃周组织需多切面核对': 'Perigastric tissues on this frame need multi-plane review',
  '当前帧未能确认浆膜连续性': 'Serosal continuity not confirmed on this frame',
  '当前帧未能确认胃周组织': 'Perigastric tissues not confirmed on this frame',
  '当前帧几何/界面代理，需医生结合多切面核对': 'Current-frame geometry/UI proxy; physician multi-plane review required',
  '胃周组织未见明显异常改变': 'No clear perigastric abnormality',
  '胃周脂肪间隙清晰': 'Perigastric fat plane clear',
  '胃周脂肪间隙欠清': 'Perigastric fat plane ill-defined',
  '胃周脂肪间隙异常改变': 'Abnormal perigastric fat change',
  '脂肪间隙清晰': 'Fat plane clear',
  '脂肪间隙欠清': 'Fat plane ill-defined',
  '脂肪间隙异常改变': 'Abnormal fat change',
  '未见明显异常改变': 'No clear abnormality',
  '未见明确胃周脂肪或邻近器官侵犯征象': 'No definite invasion of the perigastric fat or adjacent organs',
  '建议结合胃镜活检及其他影像学资料，必要时进行多切面复核。':
    'Correlate with endoscopic biopsy and other imaging; multi-plane review when needed.',
  '建议结合胃镜活检及其他影像学资料。':
    'Correlate with endoscopic biopsy and other imaging studies.',
  '建议结合胃镜活检明确病理性质。当前工作台评估的是 cT，不等于完整 TNM（N=淋巴结，M=远处转移）。':
    'Correlate with endoscopic biopsy for pathology. This workbench assesses cT only, not complete TNM (N = lymph nodes, M = distant metastasis).',
  '综合超声影像征象，浸润深度尚不确定，供医生复核签发。':
    'Based on ultrasound imaging signs, invasion depth remains uncertain; physician review and sign-off are required.',
  低回声: 'hypoechoic',
  低回声占位性病变: 'hypoechoic mass',
  未评估: 'Not assessed',
  未提供: 'Not provided',
  待补充: 'To be completed',
  待复核: 'Pending review',
  显示欠清: 'limited visibility',
  连续性欠清: 'continuity unclear',
  层次显示欠清: 'limited layer visibility',
  浆膜连续性欠清: 'serosal continuity unclear',
  胃周组织显示欠清: 'perigastric tissue unclear',
  壁层层次: 'Wall layers',
  浆膜: 'Serosa',
  胃: 'stomach',
};

export type GcUsReportLocale = 'zh' | 'en';

export function resolveGcUsReportLocale(zh = true): GcUsReportLocale {
  return zh ? 'zh' : 'en';
}

export function gcUsOptionLabel(value: string, zh = true): string {
  if (!value) return value;
  if (zh) return value;
  if (GC_US_OPTION_LABEL_EN[value]) return GC_US_OPTION_LABEL_EN[value];
  // Soft fallback for compound site strings (e.g. 胃体（大弯）).
  // Prefer longer tokens; if any CJK remains, keep the original to avoid mixed garbage.
  let next = value;
  const tokens = Object.entries(GC_US_OPTION_LABEL_EN).sort((a, b) => b[0].length - a[0].length);
  for (const [zhToken, enToken] of tokens) {
    if (next.includes(zhToken)) next = next.split(zhToken).join(enToken);
  }
  if (next !== value && !containsCjk(next)) return next;
  return value;
}

function containsCjk(value: string): boolean {
  return /[\u4e00-\u9fff]/.test(value);
}

function localizedProseValue(value: string, locale: GcUsReportLocale, fallback = '____'): string {
  const raw = normalizedText(value);
  if (!raw) return fallback;
  if (locale === 'zh') return raw;
  const mapped = gcUsOptionLabel(raw, false);
  if (!containsCjk(mapped)) return mapped;
  return fallback;
}

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

function layerOrdinalFromText(value: unknown): number | null {
  const raw = normalizedText(value);
  const code = raw.match(/\bL([1-5])\b/i);
  if (code) return Number(code[1]);
  if (/T4a|T4b|T3|浆膜外|浆膜|subserosa/i.test(raw)) return 5;
  if (/T2|固有肌|proper/i.test(raw)) return 4;
  if (/T1|黏膜|submuc/i.test(raw)) return 3;
  return null;
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
  const clinicalLengthMm = clinicalMm(
    clinical,
    ['tumor_size_mm', 'length_mm', 'tumorSizeMm'],
    ['length_cm', 'tumor_size_cm'],
    'length',
  );
  const clinicalThicknessMm = clinicalMm(
    clinical,
    ['tumor_thickness_mm', 'thickness_mm', 'tumorThicknessMm'],
    ['thickness_cm', 'tumor_thickness_cm'],
    'thickness',
  );
  const lengthMm = clinicalLengthMm
    ?? (signs.size.length.value != null && signs.size.length.unit !== 'px'
      ? Number(signs.size.length.value)
      : null);
  const thicknessMm = clinicalThicknessMm
    ?? (signs.size.thickness.value != null && signs.size.thickness.unit !== 'px'
      ? Number(signs.size.thickness.value)
      : null);
  const stage = referenceStage?.requested_band || referenceStage?.band;
  const stageValue = stage && stage !== 'uncertain' ? `u${stage}` : null;
  const layerValue = normalizedText(signs.layer_structure.value);
  const deepestOrdinal = layerOrdinalFromText(layerValue);
  const unassessedField = (value = '未评估'): GcUsField<string> => createGcUsField(value, {
    source: 'not_available',
    status: 'pending',
    note: '当前病例未提供明确证据，需医生确认',
  });
  const layerField = (ordinal: number): GcUsField<string> => {
    if (!deepestOrdinal) return unassessedField();
    return createGcUsField(ordinal === deepestOrdinal ? '模糊/变薄' : '存在', {
      source: signs.layer_structure.source,
      status: 'suggested',
      confidence: signs.layer_structure.confidence,
      evidence_ref: [...signs.layer_structure.evidence_ref, `layer:L${ordinal}`],
      note: '由当前胃壁层界分析映射，需医生复核',
    });
  };

  return {
    ...empty,
    lesion_site: templateTextField(
      clinicalText(clinical, ['location', 'site', 'lesion_site']) || '胃体',
      'clinical',
    ),
    maximum_diameter_cm: templateNumberField(lengthMm == null ? null : lengthMm / 10),
    maximum_thickness_cm: templateNumberField(thicknessMm == null ? null : thicknessMm / 10),
    gross_type: templateTextField(
      normalizedText(signs.morphology.value)
        || clinicalText(clinical, ['morphology', 'morphology_pattern'])
        || '未评估',
      signs.morphology.source || 'clinical',
    ),
    wall_layer_summary: templateTextField(
      normalizedText(signs.layer_structure.value)
        || clinicalText(clinical, ['layer_structure', 'wall_layer_id'])
        || '未评估',
      signs.layer_structure.source || 'not_available',
    ),
    layer_1_mucosa: layerField(1),
    layer_2_submucosa: layerField(2),
    layer_3_muscularis: layerField(3),
    layer_4_subserosa: layerField(4),
    layer_5_serosa: deepestOrdinal
      ? layerField(5)
      : templateTextField(
          normalizedText(signs.serosa_change.value)
            || clinicalText(clinical, ['serosa_status', 'serosa_change'])
            || '未评估',
          signs.serosa_change.source || 'not_available',
        ),
    perigastric_involvement: templateTextField(
      normalizedText(signs.perigastric_tissue.value)
        || clinicalText(clinical, ['perigastric_tissue', 'fat_status'])
        || '未评估',
      signs.perigastric_tissue.source || 'not_available',
    ),
    lymph_nodes: templateTextField(
      clinicalText(clinical, ['lymph_nodes', 'lymph_node_status', 'nodes', 'nodal_status']) || '未提供',
      'clinical',
    ),
    distant_metastasis: templateTextField(
      clinicalText(clinical, ['distant_metastasis', 'metastasis', 'm_stage', 'cm_stage']) || '未提供',
      'clinical',
    ),
    ascites: templateTextField(
      clinicalText(clinical, ['ascites', 'free_fluid', 'peritoneal_fluid']) || '未评估',
      'clinical',
    ),
    ct_stage: templateTextField(stageValue || 'uT1', referenceStage?.source || 'product_score'),
    cn_stage: templateTextField(
      clinicalText(clinical, ['cN', 'cn_stage', 'n_stage', 'clinical_n_stage']) || 'N0',
      'clinical',
    ),
    cm_stage: templateTextField(
      clinicalText(clinical, ['cM', 'cm_stage', 'm_stage', 'clinical_m_stage']) || 'M0',
      'clinical',
    ),
    impression: templateTextField(
      clinicalText(clinical, ['ultrasound_impression', 'impression'])
        || '综合超声影像征象，浸润深度尚不确定，供医生复核签发。',
      clinicalText(clinical, ['ultrasound_impression', 'impression'])
        ? 'clinical'
        : 'template_reference',
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
  if (/浆膜外/i.test(raw)) return '浆膜外（L5, 几何代理）';
  if (/浆膜.*(中断|破坏)|连续性.*(中断|破坏)|T4a/i.test(raw)) return '浆膜连续性中断（L5, T4a）';
  if (/中断|破坏|突破|disrupt/i.test(raw)) return '连续性可疑破坏';
  if (/紊乱|destroy/i.test(raw)) return '结构紊乱';
  if (/T3|浆膜下|subserosa|L5/i.test(raw)) return '浆膜/浆膜下层（L5, T3-T4a）';
  if (/T2|固有肌|proper|L4/i.test(raw)) return '固有肌层（L4, T2）';
  if (/L3|黏膜下|submuc/i.test(raw)) return '黏膜下层（L3, T1）';
  if (/L2|黏膜肌/i.test(raw)) return '黏膜肌层（L2, T1）';
  if (/T1|L1|黏膜|mucosa/i.test(raw)) return '黏膜浅层（L1, T1）';
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

function morphologyFromGeometry(value: unknown): string | null {
  const irregularity = positiveNumber(value);
  if (irregularity == null) return null;
  if (irregularity <= 3.15) return '局限隆起型';
  if (irregularity <= 3.58) return '局部浸润型';
  return '溃疡浸润型';
}

function growthFromGeometry(value: unknown): string | null {
  const irregularity = positiveNumber(value);
  if (irregularity == null) return null;
  if (irregularity <= 3.15) return '膨胀型';
  if (irregularity <= 3.58) return '局部浸润性';
  return '明显浸润性';
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
    /** Evidence source for ContactGeom / LayerBridge (pixel | live_contour | model). */
    source?: GcUsEvidenceSource | null;
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

  // Calibrated clinical-table measurements always outrank contour-derived values.
  // Pixel geometry has no device calibration and must never replace the clinical
  // maximum thickness in the formal report.
  const lengthMm = clinicalMm(
    clinical,
    ['tumor_size_mm', 'length_mm', 'tumorSizeMm'],
    ['length_cm', 'tumor_size_cm'],
    'length',
  ) ?? positiveNumber(input.lesion?.lengthMm);
  const thicknessMm = clinicalMm(
    clinical,
    ['tumor_thickness_mm', 'thickness_mm', 'tumorThicknessMm'],
    ['thickness_cm', 'tumor_thickness_cm'],
    'thickness',
  ) ?? positiveNumber(input.lesion?.thicknessMm);
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
  const layerSource = layer.source
    || (layer.label || layer.tHint ? 'live_contour' : 'not_available');
  signs.layer_structure = createGcUsField(layerValue, {
    source: layerSource,
    status: layerValue ? 'suggested' : 'pending',
    confidence: layer.confidence ?? null,
    evidence_ref: [...refs, 'layer_result'],
    note: layerValue
      ? (pixel.wall_proxy
        ? '由当前帧壁层分析映射（几何/回声代理），不作病理层次结论，需医生复核'
        : '由当前胃壁层界分析映射，需医生复核')
      : '',
  });
  const morphology = classifyMorphology(
    firstValue(lesion.morphology, clinical.morphology, clinical.morphology_pattern, pixel.morphology),
  ) || morphologyFromGeometry(pixel.irregularity);
  signs.morphology = createGcUsField(
    morphology,
    {
      source: lesion.morphology || clinical.morphology ? 'clinical' : 'pixel',
      status: morphology ? 'suggested' : 'pending',
      evidence_ref: [...refs, 'lesion.morphology', 'pixel.irregularity', 'pen_ratio'],
      note: morphology && !lesion.morphology && !clinical.morphology
        ? '由当前分割轮廓与接触穿透代理，需医生复核'
        : '',
    },
  );
  signs.boundary = createGcUsField(
    classifyBoundary(firstValue(lesion.boundary, clinical.boundary, pixel.boundary, pixel.irregularity)),
    {
      source: lesion.boundary || clinical.boundary ? 'clinical' : 'pixel',
      status: 'suggested',
      evidence_ref: [...refs, 'lesion.boundary', 'pen_ratio'],
      note: !lesion.boundary && !clinical.boundary
        ? '由当前分割轮廓与接触穿透代理，需医生复核'
        : '',
    },
  );
  const growth = classifyGrowth(
    firstValue(lesion.growthPattern, clinical.us_growth_pattern, clinical.growth_pattern_us, pixel.growth),
  ) || growthFromGeometry(pixel.irregularity) || classifyGrowth(layer.tHint);
  signs.growth_pattern = createGcUsField(
    growth,
    {
      source: clinical.us_growth_pattern || clinical.growth_pattern_us
        ? 'clinical'
        : (pixel.growth || growthFromGeometry(pixel.irregularity))
          ? 'pixel'
          : 'live_contour',
      status: growth ? 'suggested' : 'pending',
      evidence_ref: [...refs, 'growth', 'pixel.irregularity', 'pen_ratio'],
      note: growth && !lesion.growthPattern && !clinical.us_growth_pattern && !clinical.growth_pattern_us
        ? '由当前分割轮廓与接触穿透代理，需医生复核'
        : '',
    },
  );
  signs.serosa_change = createGcUsField(
    classifySerosa(firstValue(lesion.serosaChange, clinical.serosa_status, clinical.serosa_change, pixel.serosa, layer.tHint)),
    {
      source: clinical.serosa_status || clinical.serosa_change ? 'doctor' : 'pixel',
      status: 'suggested',
      evidence_ref: [...refs, 'serosa', 'pen_ratio'],
      note: !clinical.serosa_status && !clinical.serosa_change
        ? '浆膜代理提示，需多切面复核'
        : '',
    },
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

function buildSizePhrase(state: GcUsReportState, locale: GcUsReportLocale = 'zh'): string {
  const length = state.signs.size.length;
  const thickness = state.signs.size.thickness;
  const hasMillimeterPair = length.value != null && thickness.value != null
    && length.unit !== 'px' && thickness.unit !== 'px';
  if (locale === 'en') {
    if (hasMillimeterPair) {
      const l = measurementText(length).replace(/ mm$/, '');
      const t = measurementText(thickness).replace(/ mm$/, '');
      return `size approximately ${l}×${t} mm, maximum thickness ${t} mm`;
    }
    if (length.value == null && thickness.value == null) {
      return 'size approximately ____×____ mm, maximum thickness ____ mm';
    }
    return `size approximately ${measurementText(length)}×${measurementText(thickness)}, maximum thickness ${measurementText(thickness)}`;
  }
  if (hasMillimeterPair) {
    const l = measurementText(length).replace(/ mm$/, '');
    const t = measurementText(thickness).replace(/ mm$/, '');
    return `大小约${l}×${t} mm，最大厚度${t} mm`;
  }
  if (length.value == null && thickness.value == null) return '大小约____×____ mm，最大厚度____ mm';
  return `大小约${measurementText(length)}×${measurementText(thickness)}，最大厚度${measurementText(thickness)}`;
}

export function buildGcUsFindingSentence(
  state: GcUsReportState,
  locale: GcUsReportLocale = 'zh',
): string {
  const siteRaw = normalizedText(state.clinical.location || state.clinical.site);
  const grossType = GROSS_TYPE_SIGN_MAP[normalizedText(state.template_fields.gross_type.value)];
  const morphologyRaw = fieldText(state.signs.morphology, '') || grossType?.morphology || '';
  const echoRaw = fieldText(state.signs.lesion_echo, '低回声');
  const boundaryRaw = normalizedBoundary(fieldText(state.signs.boundary));
  const growthRaw = fieldText(state.signs.growth_pattern, '') || grossType?.growth || '局部浸润性';
  const layerRaw = normalizedLayer(fieldText(state.signs.layer_structure));
  const serosaRaw = normalizedSerosa(fieldText(state.signs.serosa_change));
  const perigastricRaw = normalizedPerigastric(fieldText(state.signs.perigastric_tissue));

  if (locale === 'en') {
    // Localize from full stored tokens (Chinese SSOT). Do not use ZH grammar strippers first,
    // or exact EN maps miss (e.g. 边界部分欠清 → 部分欠清).
    const site = siteRaw ? localizedProseValue(siteRaw, 'en', 'the gastric wall') : 'the gastric wall';
    const morphology = morphologyRaw && morphologyRaw !== '____'
      ? `${localizedProseValue(morphologyRaw, 'en', 'locally infiltrative')} `
      : '';
    const echo = localizedProseValue(echoRaw, 'en', 'hypoechoic');
    const lesionNoun = /mass|lesion|占位|肿块|病变/i.test(echoRaw) || /mass|lesion/i.test(echo)
      ? (/mass|lesion/i.test(echo) ? echo : `${echo} mass`)
      : `${echo} mass`;
    const growth = localizedProseValue(growthRaw, 'en', 'locally infiltrative');
    const boundaryFull = fieldText(state.signs.boundary);
    const boundary = localizedProseValue(
      boundaryFull !== '____' ? boundaryFull : boundaryRaw,
      'en',
      'ill-defined',
    );
    const layer = localizedProseValue(
      fieldText(state.signs.layer_structure) !== '____'
        ? fieldText(state.signs.layer_structure)
        : layerRaw,
      'en',
      'limited layer visibility on this frame; multi-plane review needed',
    );
    const serosa = localizedProseValue(
      fieldText(state.signs.serosa_change) !== '____'
        ? fieldText(state.signs.serosa_change)
        : serosaRaw,
      'en',
      'serosal continuity on this frame needs multi-plane review',
    );
    const perigastric = localizedProseValue(
      fieldText(state.signs.perigastric_tissue) !== '____'
        ? fieldText(state.signs.perigastric_tissue)
        : perigastricRaw,
      'en',
      'perigastric tissues on this frame need multi-plane review',
    );
    return `A ${morphology}${lesionNoun} is seen in ${site}. The ${buildSizePhrase(state, 'en')}. The lesion shows ${growth} growth with a ${boundary} margin. Wall-layer architecture: ${layer}. Serosal appearance: ${serosa}. Perigastric tissue: ${perigastric}.`;
  }

  const location = siteRaw ? `${siteRaw}见` : '胃壁见';
  const lesionNoun = /占位|肿块|病变/.test(echoRaw) ? echoRaw : `${echoRaw}占位性病变`;
  const morphologyPrefix = morphologyRaw && morphologyRaw !== '____' ? morphologyRaw : '';
  const growthZh = growthRaw === '____' ? '局部浸润性' : growthRaw;
  const boundaryZh = boundaryRaw === '____' ? '部分欠清' : boundaryRaw;
  const layerZh = layerRaw === '____' ? '当前帧层次显示有限，需多切面复核' : layerRaw;
  const serosaZh = serosaRaw === '____' ? '当前帧浆膜连续性需多切面核对' : serosaRaw;
  const perigastricZh = perigastricRaw === '____' ? '当前帧胃周组织需多切面核对' : perigastricRaw;
  return `${location}${morphologyPrefix}${lesionNoun}，${buildSizePhrase(state, 'zh')}。病灶呈${growthZh}生长方式，边界${boundaryZh}。胃壁层次表现为${layerZh}，浆膜表现${serosaZh}，胃周组织${perigastricZh}。`;
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
  input: Omit<Partial<GcUsReportState>, 'signs'> & { signs?: Partial<GcUsSigns> } = {},
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
    export_method: reportInput.export_method || null,
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
        && Boolean(String((item as GcUsReportImage).url).trim())
        && (
          /^data:image\//i.test(String((item as GcUsReportImage).url))
          || /^blob:/i.test(String((item as GcUsReportImage).url))
          || /^https?:\/\//i.test(String((item as GcUsReportImage).url))
          || /^\/(?:api|_next|images|public)\//i.test(String((item as GcUsReportImage).url))
        )
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
  locale: GcUsReportLocale = 'zh',
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
  const stageLine = locale === 'en'
    ? (stage === 'uncertain'
      ? 'Gastric cancer is possible; ultrasound-assessed cTx. Invasion depth remains uncertain. Do not output a definite cT without confirmed wall-layer, serosal, or adjacent-organ evidence.'
      : stage === 'T4'
        ? 'Gastric cancer is possible; ultrasound-assessed cT4 (subtype unresolved; distinguish serosal invasion T4a from adjacent-organ invasion T4b).'
        : `Gastric cancer is possible; ultrasound-assessed c${stage}.`)
    : (stage === 'uncertain'
      ? '胃癌可能，超声评估cTx期，浸润深度倾向尚不确定。无经确认的壁层、浆膜或邻近器官证据时不得输出确定 cT。'
      : stage === 'T4'
        ? '胃癌可能，超声评估cT4期（亚型未定；需区分浆膜受侵 T4a 与邻近器官侵犯 T4b）。'
        : `胃癌可能，超声评估c${stage}期。`);
  const advice = locale === 'en'
    ? (conflicts.length
      ? 'Reassess conflicting signs on multiple planes; if needed, rescan the lesion outer edge and serosal region.'
      : 'Correlate with endoscopic biopsy for pathology. This workbench assesses cT only, not complete TNM (N = lymph nodes, M = distant metastasis).')
    : (conflicts.length
      ? '建议针对冲突征象进行多切面核对，必要时补扫病灶外缘及浆膜区。'
      : '建议结合胃镜活检明确病理性质。当前工作台评估的是 cT，不等于完整 TNM（N=淋巴结，M=远处转移）。');
  const prose = locale === 'en'
    ? [
      '[Ultrasound findings]',
      buildGcUsFindingSentence(state, 'en'),
      '',
      '[Ultrasound impression]',
      '1. Based on the ultrasound imaging features and AI-assisted analysis, consider:',
      stageLine,
      '2. cT ladder: T1 mucosa/submucosa; T2 muscularis propria; T3 subserosa; T4a serosa; T4b adjacent organs. Formal report ticks five layers: L1 superficial mucosa, L2 muscularis mucosae, L3 submucosa, L4 muscularis propria, L5 serosa.',
      ...(conflicts.length
        ? [`3. Sign conflicts requiring physician review: ${conflicts.map((item) => item.message).join('; ')}`]
        : []),
      '',
      '[Recommendations]',
      `1. ${advice}`,
      '',
      'Note: Geometry and rule assists are not pathology gold standards; the physician has final authority. Spectral cues, scribbles, and lumen-box proxies cannot alone decide cT. Morphology/growth fold into gross type; boundary folds into layer ticks.',
    ].join('\n')
    : [
      '【超声所见】',
      buildGcUsFindingSentence(state, 'zh'),
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
  locale: GcUsReportLocale = 'zh',
): string {
  const stored = templateValue(fields, 'impression', '');
  if (locale === 'en') {
    // Prefer structured English impression (bilingual template style) when stored text is Chinese.
    if (stored && stored !== '____' && !containsCjk(stored)) return stored;
    const site = localizedProseValue(templateValue(fields, 'lesion_site', ''), 'en', 'gastric');
    if (stageText) {
      return `Infiltrative wall thickening at ${site}; gastric cancer is suspected. Based on the ultrasound imaging features and AI-assisted analysis, the physician reviewed and confirmed: ultrasound-assessed ${stageText}.`;
    }
    return `Wall abnormality at ${site}; gastric cancer is suspected. Invasion depth remains uncertain and requires physician review before sign-off.`;
  }
  const fallback = stageText
    ? `综合超声影像征象，倾向${stageText}，供医生复核签发。`
    : '综合超声影像征象，浸润深度尚不确定，供医生复核签发。';
  return stored && stored !== '____' ? stored : fallback;
}

export function buildGcUsTemplateImpression(
  stateInput: GcUsReportState,
  locale: GcUsReportLocale = 'zh',
): string {
  const state = createGcUsReportState(stateInput);
  const stageText = [
    templateValue(state.template_fields, 'ct_stage'),
    templateValue(state.template_fields, 'cn_stage'),
    templateValue(state.template_fields, 'cm_stage'),
  ].filter((value) => value && value !== '____').join(' ');
  return templateImpressionText(state.template_fields, stageText, locale);
}

function localizedFreeTextField(
  value: string,
  locale: GcUsReportLocale,
  fallbackZh: string,
  fallbackEn: string,
): string {
  const raw = normalizedText(value);
  if (!raw || raw === '____') return locale === 'en' ? fallbackEn : fallbackZh;
  if (locale === 'zh') return raw;
  if (!containsCjk(raw)) return raw;
  const mapped = gcUsOptionLabel(raw, false);
  if (mapped !== raw && !containsCjk(mapped)) return mapped;
  return fallbackEn;
}

/** Localize stored Chinese free-text fields for English report / preview surfaces. */
export function localizeGcUsFreeText(
  value: string,
  locale: GcUsReportLocale,
  fallbackZh: string,
  fallbackEn: string,
): string {
  return localizedFreeTextField(value, locale, fallbackZh, fallbackEn);
}

export function buildGcUsTemplateReportText(
  stateInput: GcUsReportState,
  locale: GcUsReportLocale = 'zh',
): string {
  const state = createGcUsReportState(stateInput);
  const fields = state.template_fields;
  const siteRaw = templateValue(fields, 'lesion_site');
  const uT = templateValue(fields, 'ct_stage');
  const n = templateValue(fields, 'cn_stage');
  const m = templateValue(fields, 'cm_stage');
  const stageText = [uT, n, m].filter((value) => value && value !== '____').join(' ');
  const impression = templateImpressionText(fields, stageText, locale);
  const diameter = templateNumber(fields, 'maximum_diameter_cm');
  const thickness = templateNumber(fields, 'maximum_thickness_cm');
  const growthRaw = fieldText(state.signs.growth_pattern);

  if (locale === 'en') {
    const site = localizedProseValue(siteRaw, 'en');
    const gross = localizedProseValue(templateValue(fields, 'gross_type'), 'en');
    const growth = localizedProseValue(growthRaw, 'en');
    const layer1 = localizedProseValue(templateValue(fields, 'layer_1_mucosa'), 'en');
    const layer2 = localizedProseValue(templateValue(fields, 'layer_2_submucosa'), 'en');
    const layer3 = localizedProseValue(templateValue(fields, 'layer_3_muscularis'), 'en');
    const layer4 = localizedProseValue(templateValue(fields, 'layer_4_subserosa'), 'en');
    const layer5 = localizedProseValue(templateValue(fields, 'layer_5_serosa'), 'en');
    const perigastric = localizedFreeTextField(
      templateValue(fields, 'perigastric_involvement', ''),
      'en',
      '____',
      'No definite invasion of the perigastric fat or adjacent organs is identified.',
    );
    const lymph = localizedFreeTextField(
      templateValue(fields, 'lymph_nodes', ''),
      'en',
      '待补充',
      'A complete lymph-node assessment is not included and should be supplemented with additional imaging.',
    );
    const distant = localizedFreeTextField(
      templateValue(fields, 'distant_metastasis', ''),
      'en',
      '待补充',
      'A complete assessment of distant metastasis is not included and should be supplemented by staging examinations.',
    );
    const ascites = localizedProseValue(templateValue(fields, 'ascites'), 'en');
    const recommendation = localizedFreeTextField(
      templateValue(fields, 'recommendation', ''),
      'en',
      '建议结合胃镜活检及其他影像学资料。',
      'Correlate with endoscopic biopsy and other imaging studies. Final physician review and sign-off are required.',
    );
    return [
      'Gastric Cancer Ultrasound Report',
      '',
      'Ultrasound description:',
      `The lesion is located in [${site}].`,
      `The maximum diameter is approximately ${diameter} cm, and the maximum thickness is approximately ${thickness} cm.`,
      `Gross type: ${gross}.`,
      `Growth pattern: ${growth}.`,
      'Gastric wall layers (inner to outer):',
      `Layer 1 (superficial mucosa) (${layer1}), Layer 2 (muscularis mucosae) (${layer2}), Layer 3 (submucosa) (${layer3}), Layer 4 (muscularis propria) (${layer4}), Layer 5 (serosa) (${layer5}).`,
      `Perigastric involvement: ${perigastric}.`,
      `Lymph nodes: ${lymph}.`,
      `Distant metastasis: ${distant}.`,
      `Free intraperitoneal fluid: ${ascites}.`,
      '',
      'Ultrasound impression:',
      `${site === '____' ? '________' : site} gastric wall: ${impression === '____' ? '________' : impression}`,
      `Consider gastric cancer (${uT === '____' ? 'uT ____' : uT} ${n === '____' ? 'N ____' : n} ${m === '____' ? 'M ____' : m}).`,
      '',
      'Notes:',
      'Morphology and growth are folded into gross type; boundary is folded into wall-layer structure. Select the deepest involved layer.',
      'Breakthrough analysis focuses on the lesion-lumen contact band; overlap wash is localization only and not standalone evidence of breakthrough.',
      'Five-layer anatomy (inner to outer): Layer 1 superficial mucosa, Layer 2 muscularis mucosae, Layer 3 submucosa, Layer 4 muscularis propria, Layer 5 serosa.',
      '',
      `Core imaging signs: ${buildGcUsFindingSentence(state, 'en')}`,
      '',
      'Recommendations:',
      recommendation,
      '',
      'Note: Generated from the gastric filling ultrasound report template layout (bilingual example, 2026-08-10). Key images must come from the current-case segmentation/key-frame/analysis outputs. Imaging assists require physician review before sign-off.',
    ].join('\n');
  }

  return [
    '胃癌超声报告',
    '',
    '超声描述：',
    `病灶位于［${siteRaw}］；`,
    `最大径 ${diameter} cm，最厚径 ${thickness} cm；`,
    `大体分型（${templateValue(fields, 'gross_type')}）`,
    `生长方式（${growthRaw}）`,
    '胃壁层次结构（由内往外）［',
    `第一层（黏膜浅层）（${templateValue(fields, 'layer_1_mucosa')}）、第二层（黏膜肌层）（${templateValue(fields, 'layer_2_submucosa')}）、第三层（黏膜下层）（${templateValue(fields, 'layer_3_muscularis')}）、第四层（固有肌层）（${templateValue(fields, 'layer_4_subserosa')}）、第五层（浆膜）（${templateValue(fields, 'layer_5_serosa')}）］；`,
    `侵及胃周组织 ${templateValue(fields, 'perigastric_involvement')}；`,
    `淋巴结（${templateValue(fields, 'lymph_nodes', '待补充')}）；`,
    `远处转移（${templateValue(fields, 'distant_metastasis', '待补充')}）；`,
    `腹腔游离液性区（${templateValue(fields, 'ascites')}）。`,
    '',
    '超声提示：',
    `${siteRaw === '____' ? '________' : siteRaw}胃壁 ${impression === '____' ? '________' : impression}`,
    `考虑胃癌（${uT === '____' ? 'uT ____' : uT} ${n === '____' ? 'N ____' : n} ${m === '____' ? 'M ____' : m}）`,
    '',
    '注：',
    '形态、生长方式并入大体分型；边界并入层次结构，细化并勾选累及最深层次。',
    '突破胃壁分析的关键区为病灶与胃腔壁的接触带；重叠填色仅作定位辅助，不能单独作为突破依据。',
    '五层解剖（由内往外）：第一层黏膜浅层，第二层黏膜肌层，第三层黏膜下层，第四层固有肌层，第五层浆膜。',
    '',
    `核心影像征象：${buildGcUsFindingSentence(state, 'zh')}`,
    '',
    '检查建议：',
    templateValue(fields, 'recommendation', '建议结合胃镜活检及其他影像学资料。'),
    '',
    '说明：本报告按《胃充盈超声报告模板.docx》版式生成，关键图像应来自当前病例分割、关键帧和分析结果，影像辅助结果需由医生复核后签发。',
  ].join('\n');
}

export function buildGcUsTemplateReport(
  stateInput: GcUsReportState,
  locale: GcUsReportLocale = 'zh',
): GcUsReportState {
  const state = createGcUsReportState(stateInput);
  return {
    ...state,
    report: {
      ...state.report,
      prose: buildGcUsTemplateReportText(state, locale),
    },
  };
}

/** Rebuild doctor-facing template prose for the active UI language from structured fields. */
export function localizeGcUsTemplateReport(
  stateInput: GcUsReportState,
  locale: GcUsReportLocale,
): GcUsReportState {
  return buildGcUsTemplateReport(stateInput, locale);
}

function isUnassessedValue(value: unknown): boolean {
  const raw = normalizedText(value).toLowerCase();
  return raw === '未评估'
    || raw === '未提供'
    || raw === 'utx'
    || raw === 'nx'
    || raw === 'mx';
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
  if (!state.report.export_method) {
    addIssue({
      code: 'missing_export_method',
      severity: 'error',
      field_id: null,
      message: '请选择一种导出方式。',
    });
  }
  if (!state.report_images.some((image) => image.selected !== false)) {
    addIssue({
      code: 'missing_report_reference_image',
      severity: 'error',
      field_id: null,
      message: '请至少选择一张参考报告图像。',
    });
  }

  for (const definition of GC_US_REQUIRED_TEMPLATE_FIELDS) {
    const field = state.template_fields[definition.id];
    const value = field?.value;
    const missing = value == null
      || (typeof value === 'string' && value.trim() === '')
      || isUnassessedValue(value)
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
      || isUnassessedValue(field.value)
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
