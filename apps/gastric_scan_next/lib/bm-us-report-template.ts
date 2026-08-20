export const BM_US_REPORT_TEMPLATE_ID = 'bm_us_diff_report_template_v1' as const;
export const BM_US_REPORT_SCHEMA_VERSION = 'bm_us_diff_report_v1' as const;
export const BM_US_REPORT_SOURCE_DOC = '胃良恶性病变鉴别超声报告模板.docx' as const;
export const BM_US_REPORT_SOURCE_DOC_EN = 'Gastric benign-malignant ultrasound report template.docx' as const;

export type BmUsReportLocale = 'zh' | 'en';

export type BmUsLesionSite =
  | '贲门'
  | '胃底'
  | '胃体（大弯）'
  | '胃体（小弯）'
  | '胃体（前壁）'
  | '胃体（后壁）'
  | '胃角'
  | '胃窦'
  | '幽门';

export type BmUsWallLayer = '存在' | '模糊' | '消失' | '其他';
export type BmUsSurface = '光整' | '不光整' | '覆盖强回声斑' | '其他';
export type BmUsPeristalsis = '活跃' | '正常' | '减弱' | '消失';
export type BmUsRetention = '有' | '无';
export type BmUsCdfi = '无' | '少量' | '中等量' | '丰富';
export type BmUsAscites = '无' | '少量' | '中等量' | '大量';
export type BmUsNature = 'benign' | 'malignant';

export type BmUsReportFields = {
  lesion_site: BmUsLesionSite | '';
  maximum_diameter_cm: number | null;
  maximum_thickness_cm: number | null;
  ulcer_present: boolean | null;
  ulcer_base_width_cm: number | null;
  ulcer_mouth_width_cm: number | null;
  ulcer_depth_cm: number | null;
  wall_layers: BmUsWallLayer | '';
  wall_layers_other: string;
  surface: BmUsSurface | '';
  surface_other: string;
  peristalsis: BmUsPeristalsis | '';
  stenosis_present: boolean | null;
  stenosis_site: string;
  stenosis_min_diameter_cm: number | null;
  retention: BmUsRetention | '';
  cdfi: BmUsCdfi | '';
  lymph_nodes_present: boolean | null;
  lymph_node_site: string;
  lymph_node_count: string;
  lymph_node_long_cm: number | null;
  lymph_node_short_cm: number | null;
  lymph_node_hilum: string;
  lymph_node_flow: string;
  ascites: BmUsAscites | '';
  impression_site: string;
  impression_wall: string;
  impression_consider: string;
  nature: BmUsNature | '';
};

export type BmUsReportState = {
  schema_version: typeof BM_US_REPORT_SCHEMA_VERSION;
  template_id: typeof BM_US_REPORT_TEMPLATE_ID;
  source_doc: typeof BM_US_REPORT_SOURCE_DOC;
  case_id: string | null;
  fields: BmUsReportFields;
  report: {
    prose: string;
    prose_ready: boolean;
    source: 'template' | 'doctor';
    status: 'draft' | 'finalized';
  };
};

export const BM_US_LESION_SITES: BmUsLesionSite[] = [
  '贲门',
  '胃底',
  '胃体（大弯）',
  '胃体（小弯）',
  '胃体（前壁）',
  '胃体（后壁）',
  '胃角',
  '胃窦',
  '幽门',
];

export const BM_US_WALL_LAYER_OPTIONS: BmUsWallLayer[] = ['存在', '模糊', '消失', '其他'];
export const BM_US_SURFACE_OPTIONS: BmUsSurface[] = ['光整', '不光整', '覆盖强回声斑', '其他'];
export const BM_US_PERISTALSIS_OPTIONS: BmUsPeristalsis[] = ['活跃', '正常', '减弱', '消失'];
export const BM_US_RETENTION_OPTIONS: BmUsRetention[] = ['有', '无'];
export const BM_US_CDFI_OPTIONS: BmUsCdfi[] = ['无', '少量', '中等量', '丰富'];
export const BM_US_ASCITES_OPTIONS: BmUsAscites[] = ['无', '少量', '中等量', '大量'];

const BM_OPTION_EN: Record<string, string> = {
  贲门: 'cardia',
  胃底: 'fundus',
  '胃体（大弯）': 'gastric body (greater curvature)',
  '胃体（小弯）': 'gastric body (lesser curvature)',
  '胃体（前壁）': 'gastric body (anterior wall)',
  '胃体（后壁）': 'gastric body (posterior wall)',
  胃角: 'angular incisure',
  胃窦: 'antrum',
  幽门: 'pylorus',
  存在: 'preserved',
  模糊: 'blurred',
  消失: 'absent',
  其他: 'other',
  光整: 'smooth',
  不光整: 'irregular',
  覆盖强回声斑: 'covered by hyperechoic plaques',
  活跃: 'active',
  正常: 'normal',
  减弱: 'reduced',
  无: 'none',
  有: 'present',
  少量: 'small amount',
  中等量: 'moderate amount',
  丰富: 'abundant',
  大量: 'large amount',
};

export function bmUsOptionLabel(value: string | null | undefined, zh = true): string {
  const raw = String(value || '').trim();
  if (!raw) return zh ? '____' : '____';
  if (zh) return raw;
  return BM_OPTION_EN[raw] || raw;
}

export function emptyBmUsReportFields(): BmUsReportFields {
  return {
    lesion_site: '',
    maximum_diameter_cm: null,
    maximum_thickness_cm: null,
    ulcer_present: null,
    ulcer_base_width_cm: null,
    ulcer_mouth_width_cm: null,
    ulcer_depth_cm: null,
    wall_layers: '',
    wall_layers_other: '',
    surface: '',
    surface_other: '',
    peristalsis: '',
    stenosis_present: null,
    stenosis_site: '',
    stenosis_min_diameter_cm: null,
    retention: '',
    cdfi: '',
    lymph_nodes_present: null,
    lymph_node_site: '',
    lymph_node_count: '',
    lymph_node_long_cm: null,
    lymph_node_short_cm: null,
    lymph_node_hilum: '',
    lymph_node_flow: '',
    ascites: '',
    impression_site: '',
    impression_wall: '',
    impression_consider: '',
    nature: '',
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function positiveNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function normalizeSite(value: unknown): BmUsLesionSite | '' {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const hit = BM_US_LESION_SITES.find((site) => raw.includes(site.replace(/[（）]/g, '')) || raw.includes(site));
  if (hit) return hit;
  if (raw.includes('贲门')) return '贲门';
  if (raw.includes('胃底')) return '胃底';
  if (raw.includes('胃角')) return '胃角';
  if (raw.includes('幽门')) return '幽门';
  if (raw.includes('胃窦')) return '胃窦';
  if (raw.includes('胃体')) {
    if (raw.includes('大弯')) return '胃体（大弯）';
    if (raw.includes('小弯')) return '胃体（小弯）';
    if (raw.includes('前壁')) return '胃体（前壁）';
    if (raw.includes('后壁')) return '胃体（后壁）';
    return '胃体（大弯）';
  }
  return '';
}

export function seedBmUsReportFields(
  clinical: Record<string, unknown> = {},
  extras?: Partial<BmUsReportFields>,
): BmUsReportFields {
  const measurements = asRecord(clinical.measurements) || asRecord(clinical.measurement) || {};
  const tumorSize = asRecord(clinical.tumorSize) || {};
  const lengthCm = positiveNumber(clinical.length_cm)
    ?? positiveNumber(measurements.length_cm)
    ?? (positiveNumber(clinical.tumor_size_mm) != null ? Number(clinical.tumor_size_mm) / 10 : null)
    ?? (positiveNumber(tumorSize.length) != null ? Number(tumorSize.length) : null);
  const thicknessCm = positiveNumber(clinical.thickness_cm)
    ?? positiveNumber(measurements.thickness_cm)
    ?? (positiveNumber(clinical.tumor_thickness_mm) != null ? Number(clinical.tumor_thickness_mm) / 10 : null)
    ?? (positiveNumber(tumorSize.thickness) != null ? Number(tumorSize.thickness) : null);
  const site = normalizeSite(clinical.location || clinical.site || clinical.tumor_location);
  const fields = emptyBmUsReportFields();
  fields.lesion_site = site;
  fields.maximum_diameter_cm = lengthCm;
  fields.maximum_thickness_cm = thicknessCm;
  fields.impression_site = site;
  return { ...fields, ...extras };
}

export function createBmUsReportState(input?: {
  case_id?: string | null;
  clinical?: Record<string, unknown>;
  fields?: Partial<BmUsReportFields>;
}): BmUsReportState {
  const seeded = seedBmUsReportFields(input?.clinical || {}, input?.fields);
  return {
    schema_version: BM_US_REPORT_SCHEMA_VERSION,
    template_id: BM_US_REPORT_TEMPLATE_ID,
    source_doc: BM_US_REPORT_SOURCE_DOC,
    case_id: input?.case_id || null,
    fields: seeded,
    report: {
      prose: '',
      prose_ready: false,
      source: 'template',
      status: 'draft',
    },
  };
}

function blank(value: string | number | null | undefined, fallback = '____'): string {
  if (value == null || value === '') return fallback;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : fallback;
  }
  const text = String(value).trim();
  return text || fallback;
}

function natureConsider(fields: BmUsReportFields, locale: BmUsReportLocale): string {
  if (fields.impression_consider.trim()) return fields.impression_consider.trim();
  if (fields.nature === 'benign') return locale === 'en' ? 'benign gastric-wall lesion' : '良性病变';
  if (fields.nature === 'malignant') return locale === 'en' ? 'malignant gastric-wall lesion' : '恶性病变';
  return '____';
}

export function buildBmUsTemplateReportText(
  state: BmUsReportState,
  locale: BmUsReportLocale = 'zh',
): string {
  const f = state.fields;
  const site = blank(f.lesion_site);
  const diameter = blank(f.maximum_diameter_cm);
  const thickness = blank(f.maximum_thickness_cm);
  const wall = f.wall_layers === '其他' && f.wall_layers_other.trim()
    ? f.wall_layers_other.trim()
    : blank(f.wall_layers);
  const surface = f.surface === '其他' && f.surface_other.trim()
    ? f.surface_other.trim()
    : blank(f.surface);
  const consider = natureConsider(f, locale);
  const impressionSite = blank(f.impression_site || f.lesion_site);
  const impressionWall = blank(f.impression_wall || wall);

  const ulcerZh = f.ulcer_present === true
    ? `有（底部宽径${blank(f.ulcer_base_width_cm)}cm、口部宽径${blank(f.ulcer_mouth_width_cm)}cm、最深径${blank(f.ulcer_depth_cm)}cm）`
    : f.ulcer_present === false
      ? '无'
      : '____';
  const stenosisZh = f.stenosis_present === true
    ? `有（部位${blank(f.stenosis_site)}、最窄径${blank(f.stenosis_min_diameter_cm)}cm）`
    : f.stenosis_present === false
      ? '无'
      : '____';
  const nodesZh = f.lymph_nodes_present === true
    ? `有（位置${blank(f.lymph_node_site)}、数量${blank(f.lymph_node_count)}、长径${blank(f.lymph_node_long_cm)} cm、短径${blank(f.lymph_node_short_cm)} cm、淋巴门${blank(f.lymph_node_hilum)}、血流信号${blank(f.lymph_node_flow)}）`
    : f.lymph_nodes_present === false
      ? '无'
      : '____';

  if (locale === 'en') {
    const ulcerEn = f.ulcer_present === true
      ? `present (base width ${blank(f.ulcer_base_width_cm)} cm, mouth width ${blank(f.ulcer_mouth_width_cm)} cm, depth ${blank(f.ulcer_depth_cm)} cm)`
      : f.ulcer_present === false
        ? 'absent'
        : '____';
    const stenosisEn = f.stenosis_present === true
      ? `present (site ${blank(f.stenosis_site)}, narrowest caliber ${blank(f.stenosis_min_diameter_cm)} cm)`
      : f.stenosis_present === false
        ? 'absent'
        : '____';
    const nodesEn = f.lymph_nodes_present === true
      ? `present (site ${blank(f.lymph_node_site)}, number ${blank(f.lymph_node_count)}, long-axis ${blank(f.lymph_node_long_cm)} cm, short-axis ${blank(f.lymph_node_short_cm)} cm, hilum ${blank(f.lymph_node_hilum)}, flow ${blank(f.lymph_node_flow)})`
      : f.lymph_nodes_present === false
        ? 'absent'
        : '____';
    return [
      'Gastric Benign–Malignant Ultrasound Report',
      '',
      'Ultrasound description:',
      `The lesion is located in [${bmUsOptionLabel(site === '____' ? '' : site, false) || '____'}];`,
      `Gastric-wall thickening (maximum diameter ${diameter} cm, maximum thickness ${thickness} cm);`,
      `Ulcer [${ulcerEn}];`,
      `Gastric-wall layer structure (${bmUsOptionLabel(wall === '____' ? '' : wall, false)});`,
      `Lesion surface (${bmUsOptionLabel(surface === '____' ? '' : surface, false)});`,
      `Gastric peristalsis (${bmUsOptionLabel(f.peristalsis, false)});`,
      `Luminal stenosis [${stenosisEn}]`,
      `Gastric retention (${bmUsOptionLabel(f.retention, false)});`,
      `CDFI (${bmUsOptionLabel(f.cdfi, false)});`,
      `Lymph nodes [${nodesEn}];`,
      `Ascites (${bmUsOptionLabel(f.ascites, false)}).`,
      '',
      'Ultrasound impression:',
      `${impressionSite === '____' ? '________' : bmUsOptionLabel(impressionSite, false)} gastric wall ${impressionWall === '____' ? '________' : bmUsOptionLabel(impressionWall, false)}`,
      `Consider ${consider}.`,
      '',
      `Note: Generated from ${BM_US_REPORT_SOURCE_DOC_EN}. Imaging assists require physician review before sign-off.`,
    ].join('\n');
  }

  return [
    '胃良恶性病变鉴别超声报告',
    '',
    '超声描述：',
    `病灶位于［${site}］；`,
    `胃壁增厚（最大径${diameter}cm，最厚径${thickness}cm）；`,
    `溃疡［${ulcerZh}］；`,
    `胃壁层次结构（${wall}）；`,
    `病灶表面 （${surface}）；`,
    `胃蠕动（${blank(f.peristalsis)}）；`,
    `胃腔狭窄［${stenosisZh}］`,
    `胃潴留（${blank(f.retention)}）；`,
    `CDFI（${blank(f.cdfi)}）；`,
    `淋巴结［${nodesZh}］；`,
    `腹水（${blank(f.ascites)}）。`,
    '',
    '超声提示：',
    `${impressionSite === '____' ? '________' : impressionSite}（部位）胃壁${impressionWall === '____' ? '________' : impressionWall}`,
    `考虑${consider}`,
    '',
    `说明：本报告按《${BM_US_REPORT_SOURCE_DOC}》版式生成，影像辅助结果需由医生复核后签发。`,
  ].join('\n');
}

export function commitBmUsTemplateReport(
  state: BmUsReportState,
  locale: BmUsReportLocale = 'zh',
): BmUsReportState {
  return {
    ...state,
    report: {
      prose: buildBmUsTemplateReportText(state, locale),
      prose_ready: true,
      source: 'doctor',
      status: 'finalized',
    },
  };
}

export function mergeBmUsReportFields(
  current: BmUsReportState,
  patch: Partial<BmUsReportFields>,
): BmUsReportState {
  return {
    ...current,
    fields: {
      ...current.fields,
      ...patch,
    },
    report: {
      ...current.report,
      prose_ready: false,
      status: current.report.status === 'finalized' ? 'draft' : current.report.status,
    },
  };
}
