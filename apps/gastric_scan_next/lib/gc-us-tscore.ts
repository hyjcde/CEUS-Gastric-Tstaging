/**
 * GC-US T-score v1 — ACR-style discrete points (from tscore_discrete_draft_v1)
 * plus wall-layer imaging points for doctor-facing narrative.
 *
 * size/morph bins: pipeline/experiments/reports/tscore_discrete_draft_v1/
 * Wall extras are soft imaging points (not train-calibrated); labeled separately.
 */

export type GcUsCtStage = 'cT1' | 'cT2' | 'cT3' | 'cT4a' | 'cT4b' | 'cTx';
export type GcUsTscoreStatus = 'supported' | 'uncertain' | 'not_assessable' | 'conflicting';

export type GcUsTscoreInput = {
  lengthCm?: number | null;
  thicknessCm?: number | null;
  /** boundary irregularity (morphology); higher = more irregular */
  irregularity?: number | null;
  /** short-axis / long-axis ratio of lesion bbox */
  shortAxisRatio?: number | null;
  ceaPositive?: boolean | null;
  /** ContactGeom layer label e.g. L3 / 浆膜 */
  layerLabel?: string | null;
  tHint?: string | null;
  inContact?: boolean | null;
  /** wall occupation ratio 0–1 */
  occupationRatio?: number | null;
  serosaDisrupted?: boolean | null;
  /** Explicit doctor/video structural evidence; proxy geometry is not enough. */
  structuralEvidence?: 'explicit' | 'proxy' | 'missing' | null;
};

export type GcUsScoreItem = {
  id: string;
  label: string;
  points: number;
  max: number;
  detail: string;
  group: 'size' | 'morph' | 'clinical' | 'wall';
};

export type GcUsTscoreResult = {
  scheme: 'gc_us_v1';
  total: number;
  maxTotal: number;
  items: GcUsScoreItem[];
  ctStage: GcUsCtStage;
  status: GcUsTscoreStatus;
  uncertaintyReasons: string[];
  mappingNote: string;
};

function binLength(cm: number): { points: number; detail: string } {
  if (cm <= 3.0) return { points: 0, detail: `长径 ${cm.toFixed(1)} cm ≤3.0` };
  if (cm <= 4.4) return { points: 1, detail: `长径 ${cm.toFixed(1)} cm ≤4.4` };
  if (cm <= 6.3) return { points: 2, detail: `长径 ${cm.toFixed(1)} cm ≤6.3` };
  return { points: 3, detail: `长径 ${cm.toFixed(1)} cm >6.3` };
}

function binThickness(cm: number): { points: number; detail: string } {
  if (cm <= 1.0) return { points: 0, detail: `厚度 ${cm.toFixed(1)} cm ≤1.0` };
  if (cm <= 1.3) return { points: 1, detail: `厚度 ${cm.toFixed(1)} cm ≤1.3` };
  if (cm <= 1.7) return { points: 2, detail: `厚度 ${cm.toFixed(1)} cm ≤1.7` };
  return { points: 3, detail: `厚度 ${cm.toFixed(1)} cm >1.7` };
}

function binIrregularity(v: number): { points: number; detail: string } {
  if (v <= 3.152) return { points: 0, detail: `不规则度 ${v.toFixed(2)} ≤3.15` };
  if (v <= 3.581) return { points: 1, detail: `不规则度 ${v.toFixed(2)} ≤3.58` };
  return { points: 2, detail: `不规则度 ${v.toFixed(2)} >3.58` };
}

function binShortAxis(r: number): { points: number; detail: string } {
  if (r <= 0.1023) return { points: 0, detail: `短轴比 ${r.toFixed(3)} ≤0.102` };
  if (r <= 0.1586) return { points: 1, detail: `短轴比 ${r.toFixed(3)} ≤0.159` };
  return { points: 2, detail: `短轴比 ${r.toFixed(3)} >0.159` };
}

function layerPoints(label?: string | null, tHint?: string | null): { points: number; detail: string } {
  const raw = `${label || ''} ${tHint || ''}`.toUpperCase();
  if (/L5|浆膜|SEROSA|T4|T3–T4|T3-T4/.test(raw)) {
    return { points: 4, detail: `达层 ${label || tHint || 'L5/浆膜'}` };
  }
  if (/L4|固有肌|PROPER/.test(raw)) return { points: 3, detail: `达层 ${label || 'L4'}` };
  if (/L3|肌层|MUSCLE/.test(raw)) return { points: 2, detail: `达层 ${label || 'L3'}` };
  if (/L2|粘膜下|SUBMUC/.test(raw)) return { points: 1, detail: `达层 ${label || 'L2'}` };
  if (/L1|粘膜|MUCOSA|不可分期|N\/A|无接触/.test(raw)) {
    return { points: 0, detail: `达层 ${label || '浅层/不可分期'}` };
  }
  return { points: 0, detail: '达层未判定' };
}

function mapTotalToCt(total: number): { ctStage: GcUsCtStage; mappingNote: string } {
  // Extended scale (size + morph + wall soft, ~0–20). Example: 16 → cT3.
  if (total <= 4) return { ctStage: 'cT1', mappingNote: '总分≤4 → cT1（偏粘膜/粘膜下）' };
  if (total <= 9) return { ctStage: 'cT2', mappingNote: '总分≤9 → cT2（偏固有肌层）' };
  if (total <= 16) return { ctStage: 'cT3', mappingNote: '总分≤16 → cT3（偏浆膜下/浆膜外）' };
  if (total <= 19) return { ctStage: 'cT4a', mappingNote: '总分≤19 → cT4a（浆膜受累倾向）' };
  return { ctStage: 'cT4b', mappingNote: '总分>19 → cT4b（深侵犯/邻近倾向）' };
}

export function computeGcUsTscore(input: GcUsTscoreInput): GcUsTscoreResult {
  const items: GcUsScoreItem[] = [];

  if (input.lengthCm != null && Number.isFinite(input.lengthCm) && input.lengthCm > 0) {
    const b = binLength(Number(input.lengthCm));
    items.push({ id: 'length', label: '肿瘤长径', points: b.points, max: 3, detail: b.detail, group: 'size' });
  }
  if (input.thicknessCm != null && Number.isFinite(input.thicknessCm) && input.thicknessCm > 0) {
    const b = binThickness(Number(input.thicknessCm));
    items.push({ id: 'thickness', label: '肿瘤厚度', points: b.points, max: 3, detail: b.detail, group: 'size' });
  }
  if (input.irregularity != null && Number.isFinite(input.irregularity)) {
    const b = binIrregularity(Number(input.irregularity));
    items.push({ id: 'irregularity', label: '边界不规则', points: b.points, max: 2, detail: b.detail, group: 'morph' });
  }
  // Avoid double-counting with thickness when both axes already entered (draft note).
  const hasSizeAxes =
    input.lengthCm != null &&
    Number.isFinite(input.lengthCm) &&
    input.lengthCm > 0 &&
    input.thicknessCm != null &&
    Number.isFinite(input.thicknessCm) &&
    input.thicknessCm > 0;
  if (
    !hasSizeAxes &&
    input.shortAxisRatio != null &&
    Number.isFinite(input.shortAxisRatio) &&
    input.shortAxisRatio > 0
  ) {
    const b = binShortAxis(Number(input.shortAxisRatio));
    items.push({ id: 'short_axis', label: '短轴比', points: b.points, max: 2, detail: b.detail, group: 'morph' });
  }
  if (input.ceaPositive != null) {
    items.push({
      id: 'cea',
      label: 'CEA',
      points: input.ceaPositive ? 1 : 0,
      max: 1,
      detail: input.ceaPositive ? 'CEA 阳性' : 'CEA 阴性/未测',
      group: 'clinical',
    });
  }

  const layerSignal = `${input.layerLabel || ''} ${input.tHint || ''}`;
  const hasLayerSignal = /L[1-5]|粘膜|黏膜|肌层|浆膜|SEROSA|MUCOSA|MUSCLE|PROPER|SUBMUC/i.test(layerSignal);
  if (hasLayerSignal) {
    const lay = layerPoints(input.layerLabel, input.tHint);
    items.push({ id: 'layer', label: '超声达层', points: lay.points, max: 4, detail: lay.detail, group: 'wall' });
  }

  if (input.inContact === false) {
    items.push({
      id: 'contact',
      label: '接触门控',
      points: 0,
      max: 1,
      detail: '无可靠接触，达层证据降权',
      group: 'wall',
    });
  } else if (input.inContact === true) {
    items.push({
      id: 'contact',
      label: '接触门控',
      points: 1,
      max: 1,
      detail: '病灶与胃壁接触成立',
      group: 'wall',
    });
  }

  const occ = input.occupationRatio;
  if (occ != null && Number.isFinite(occ)) {
    const pts = occ < 0.35 ? 0 : occ < 0.7 ? 1 : 2;
    items.push({
      id: 'occupation',
      label: '占壁厚',
      points: pts,
      max: 2,
      detail: `占壁厚 ${(occ * 100).toFixed(0)}%`,
      group: 'wall',
    });
  }

  if (input.serosaDisrupted) {
    items.push({
      id: 'serosa',
      label: '浆膜面',
      points: 2,
      max: 2,
      detail: '浆膜面欠光整/中断倾向',
      group: 'wall',
    });
  }

  const total = items.reduce((s, it) => s + it.points, 0);
  const maxTotal = items.reduce((s, it) => s + it.max, 0) || 20;
  const structuralEvidence = input.structuralEvidence || 'missing';
  const hasExplicitStructuralEvidence =
    structuralEvidence === 'explicit' &&
    input.inContact !== false &&
    (hasLayerSignal || input.serosaDisrupted === true);
  const uncertaintyReasons: string[] = [];
  if (!items.length) uncertaintyReasons.push('no_scoring_evidence');
  if (structuralEvidence !== 'explicit') uncertaintyReasons.push('wall_layer_not_explicitly_confirmed');
  if (input.inContact === false) uncertaintyReasons.push('lesion_wall_contact_not_reliable');
  if (!hasLayerSignal && input.serosaDisrupted !== true) uncertaintyReasons.push('layer_or_serosa_not_assessable');
  const status: GcUsTscoreStatus = hasExplicitStructuralEvidence
    ? 'supported'
    : items.length
      ? 'uncertain'
      : 'not_assessable';
  const { ctStage, mappingNote } = hasExplicitStructuralEvidence
    ? mapTotalToCt(total)
    : {
        ctStage: 'cTx' as const,
        mappingNote: '缺少经确认的胃壁层次/浆膜证据，仅展示软评分，不输出确定 cT 分期',
      };

  return {
    scheme: 'gc_us_v1',
    total,
    maxTotal,
    items,
    ctStage,
    status,
    uncertaintyReasons,
    mappingNote,
  };
}

export type ImagingNarrativeInput = {
  location?: string | null;
  lengthMm?: number | null;
  thicknessMm?: number | null;
  irregularity?: number | null;
  inContact?: boolean | null;
  layerLabel?: string | null;
  tHint?: string | null;
  occupationRatio?: number | null;
  serosaDisrupted?: boolean | null;
  tscore?: GcUsTscoreResult | null;
  zh?: boolean;
};

/** Doctor-style US finding paragraph + AI score line (example style). */
export function buildImagingNarrative(input: ImagingNarrativeInput): string {
  const zh = input.zh !== false;
  const loc = (input.location || '').trim() || (zh ? '胃壁' : 'gastric wall');
  const len = input.lengthMm != null && input.lengthMm > 0 ? Math.round(input.lengthMm) : null;
  const th = input.thicknessMm != null && input.thicknessMm > 0 ? Math.round(input.thicknessMm) : null;
  const size =
    len && th
      ? zh
        ? `大小约${len}×${th} mm`
        : `measuring about ${len}×${th} mm`
      : len
        ? zh
          ? `长径约${len} mm`
          : `length about ${len} mm`
        : zh
          ? '大小待测'
          : 'size pending';

  const irreg = input.irregularity ?? 0;
  const border =
    irreg > 3.58
      ? zh
        ? '边界欠清，呈浸润性生长'
        : 'ill-defined margins with infiltrative growth'
      : irreg > 3.15
        ? zh
          ? '边界欠光整'
          : 'somewhat irregular margins'
        : zh
          ? '边界尚清'
          : 'relatively clear margins';

  const wallCont =
    input.inContact === false
      ? zh
        ? '与胃壁接触关系不确定'
        : 'wall contact uncertain'
      : zh
        ? '胃壁结构连续性破坏'
        : 'disruption of wall stratification';

  const serosa =
    input.serosaDisrupted || /L5|浆膜|T4|T3–T4|T3-T4/i.test(`${input.layerLabel || ''} ${input.tHint || ''}`)
      ? zh
        ? '浆膜面欠光整'
        : 'serosal surface irregular'
      : zh
        ? '浆膜面尚光整'
        : 'serosa relatively smooth';

  const occ = input.occupationRatio;
  const fat =
    occ != null && occ >= 0.7
      ? zh
        ? '局部活动度下降，胃周脂肪间隙模糊'
        : 'reduced motility with blurred perigastric fat'
      : occ != null && occ >= 0.35
        ? zh
          ? '局部活动度下降，胃周脂肪间隙欠清'
          : 'reduced motility with indistinct perigastric fat'
        : zh
          ? '胃周脂肪间隙尚清'
          : 'perigastric fat relatively clear';

  const score = input.tscore;
  const scoreLine = score && score.status === 'supported' && score.ctStage !== 'cTx'
    ? zh
      ? `AI综合分析提示胃癌可能，GC-US T-score为${score.total}分，考虑${score.ctStage}期。`
      : `AI analysis suggests gastric cancer; GC-US T-score ${score.total}, favoring ${score.ctStage}.`
    : zh
      ? 'AI综合分析提示需结合临床进一步评估。'
      : 'AI analysis warrants further clinical correlation.';

  if (!zh) {
    return `An irregular hypoechoic mass is seen at the ${loc}, ${size}, ${border}, ${wallCont}, ${serosa}, ${fat}. ${scoreLine}`;
  }

  return `${loc}见不规则低回声肿块，${size}，${border}，${wallCont}，${serosa}，${fat}。${scoreLine}`;
}

/** Estimate length/thickness (mm) from lesion polygon; FOV heuristic ~50 mm across width. */
export function estimateAxesMm(
  poly: number[][],
  frame: { width: number; height: number },
): { lengthMm: number; thicknessMm: number } | null {
  if (!poly || poly.length < 3 || !frame?.width) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of poly) {
    minX = Math.min(minX, p[0]);
    maxX = Math.max(maxX, p[0]);
    minY = Math.min(minY, p[1]);
    maxY = Math.max(maxY, p[1]);
  }
  const w = maxX - minX;
  const h = maxY - minY;
  if (!Number.isFinite(w) || !Number.isFinite(h) || Math.max(w, h) <= 1) return null;
  const mmPerPx = 50 / Math.max(frame.width, 1);
  const lengthMm = Math.round(Math.max(w, h) * mmPerPx);
  const thicknessMm = Math.round(Math.min(w, h) * mmPerPx);
  if (lengthMm <= 0 || thicknessMm <= 0) return null;
  return { lengthMm, thicknessMm };
}

export function bboxShortAxisRatio(poly: number[][]): number | null {
  if (!poly || poly.length < 3) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of poly) {
    minX = Math.min(minX, p[0]);
    minY = Math.min(minY, p[1]);
    maxX = Math.max(maxX, p[0]);
    maxY = Math.max(maxY, p[1]);
  }
  const w = maxX - minX;
  const h = maxY - minY;
  const long = Math.max(w, h);
  const short = Math.min(w, h);
  if (long <= 1e-6) return null;
  return short / long;
}

/** Rough irregularity proxy: perimeter^2 / (4π area) — circle ≈ 1. */
export function polygonIrregularity(poly: number[][]): number | null {
  if (!poly || poly.length < 3) return null;
  let area = 0;
  let peri = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    area += a[0] * b[1] - b[0] * a[1];
    peri += Math.hypot(b[0] - a[0], b[1] - a[1]);
  }
  area = Math.abs(area) / 2;
  if (area < 1e-3 || peri < 1e-3) return null;
  return (peri * peri) / (4 * Math.PI * area);
}
