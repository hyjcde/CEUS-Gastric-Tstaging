/**
 * Doctor prompt for test-time wall reasoning.
 * The stroke is an expected anatomical trajectory, not a continuity answer.
 */

export type WallAnatomyTarget = 1 | 2 | 3;
export type WallVisibility = 'clear' | 'blurry' | 'unseen';
export type InterruptVerdict = 'continuous' | 'suspected' | 'interrupted' | 'cannot_judge';
export type SerosaAnchorMode = 'bilateral' | 'unilateral' | 'unanalyzable';
export type DoctorDepthScreen = 'shallow_clear' | 'outer_clear' | 'boundary_unclear';
export type DoctorPromptConfidence = 'high' | 'mid' | 'low';

export const WALL_ANATOMY_TARGETS: Array<{
  id: WallAnatomyTarget;
  pair: 't1_t2' | 't2_t3' | 't3_t4';
  zh: string;
  en: string;
  shortZh: string;
  shortEn: string;
  askZh: string;
  askEn: string;
  lineZh: string;
  lineEn: string;
}> = [
  {
    id: 1,
    pair: 't3_t4',
    zh: '浆膜外缘',
    en: 'Serosal outer edge',
    shortZh: '浆膜',
    shortEn: 'Serosa',
    askZh: '浆膜最外缘是否连续',
    askEn: 'Is the outermost serosa still continuous?',
    lineZh: '浆膜预期走行线',
    lineEn: 'expected serosal trajectory',
  },
  {
    id: 2,
    pair: 't2_t3',
    zh: '固有肌外缘',
    en: 'Muscularis propria outer edge',
    shortZh: '固有肌',
    shortEn: 'MP',
    askZh: '固有肌外缘是否突破',
    askEn: 'Is the MP outer edge breached?',
    lineZh: '固有肌预期走行线',
    lineEn: 'expected MP trajectory',
  },
  {
    id: 3,
    pair: 't1_t2',
    zh: '浅层 / 肌层界面',
    en: 'Shallow / MP interface',
    shortZh: '浅层',
    shortEn: 'Shallow',
    askZh: '浅层与固有肌界面是否被进入',
    askEn: 'Has the lesion entered muscularis propria?',
    lineZh: '浅层界面预期走行线',
    lineEn: 'expected shallow-interface trajectory',
  },
];

export const WALL_VISIBILITY_OPTIONS: Array<{
  id: WallVisibility;
  zh: string;
  en: string;
}> = [
  { id: 'clear', zh: '清楚', en: 'Clear' },
  { id: 'blurry', zh: '模糊', en: 'Blurry' },
  { id: 'unseen', zh: '看不清', en: 'Not seen' },
];

export const SEROSA_ANCHOR_OPTIONS: Array<{
  id: SerosaAnchorMode;
  zh: string;
  en: string;
}> = [
  { id: 'bilateral', zh: '双侧锚定', en: 'Both flanks' },
  { id: 'unilateral', zh: '单侧延伸', en: 'One flank' },
  { id: 'unanalyzable', zh: '本帧看不清', en: 'This frame unclear' },
];

export const INTERRUPT_VERDICT_ORDER: InterruptVerdict[] = [
  'continuous',
  'suspected',
  'interrupted',
  'cannot_judge',
];

export const DOCTOR_DEPTH_SCREEN_OPTIONS: Array<{
  id: DoctorDepthScreen;
  zh: string;
  en: string;
  hintZh: string;
  hintEn: string;
}> = [
  {
    id: 'shallow_clear',
    zh: '明确浅层征象',
    en: 'Clear shallow signs',
    hintZh: '不是 T1。只说浅层结构还比较清楚。不输入核心模型。',
    hintEn: 'Not a T1 call. Only says shallow structure still looks clear. Not a core-model input.',
  },
  {
    id: 'outer_clear',
    zh: '明确外层突破征象',
    en: 'Clear outer-breach signs',
    hintZh: '不是 T4。只说外缘看起来像突破。不输入核心模型。',
    hintEn: 'Not a T4 call. Only says the outer edge looks breached. Not a core-model input.',
  },
  {
    id: 'boundary_unclear',
    zh: '深度边界不清，需要 AI 精细分析',
    en: 'Depth unclear, need AI',
    hintZh: '相邻分期困难。请框选病灶并确认最深浸润区。自动锚点失败时再画两侧短线。',
    hintEn: 'Adjacent-stage case. Box the lesion and confirm the deepest-invasion region. Paint short flanks only if auto-anchors fail.',
  },
];

export const DOCTOR_PROMPT_CONFIDENCE_OPTIONS: Array<{
  id: DoctorPromptConfidence;
  zh: string;
  en: string;
}> = [
  { id: 'high', zh: '信心高', en: 'High' },
  { id: 'mid', zh: '信心中', en: 'Medium' },
  { id: 'low', zh: '信心低', en: 'Low' },
];

export type WallVisibleLayerCount = 1 | 2 | 3;
export type WallSpanSide = 'left' | 'right' | 'supplement';
export type WallSpanSource = 'doctor' | 'ai_propose';

export type WallPaintSegment = {
  points: number[][];
  visibleLayers: WallVisibleLayerCount;
  side?: WallSpanSide | null;
  brushRadius?: number | null;
  frameIndex?: number | null;
  paintedAtMs?: number | null;
  source?: WallSpanSource | null;
};

export const WALL_VISIBLE_LAYER_OPTIONS: Array<{
  id: WallVisibleLayerCount;
  zh: string;
  en: string;
  hintZh: string;
  hintEn: string;
}> = [
  { id: 1, zh: '一层', en: '1 layer', hintZh: '本段只见浆膜或最外层', hintEn: 'Only serosa or the outermost layer is visible here' },
  { id: 2, zh: '两层', en: '2 layers', hintZh: '本段还看得见两层', hintEn: 'Two layers are still visible on this span' },
  { id: 3, zh: '三层', en: '3 layers', hintZh: '本段仍是完整亮-暗-亮', hintEn: 'Full bright-dark-bright remains on this span' },
];

export const MAX_ANALYSIS_FOCUS = 1;
const MAX_WALL_PAINT_SEGMENTS = 6;
const FOCUS_HIT_PX = 14;

export function parseVisibleLayerCount(value: unknown): WallVisibleLayerCount | null {
  if (value === 1 || value === 2 || value === 3) return value;
  if (value === '1' || value === '2' || value === '3') return Number(value) as WallVisibleLayerCount;
  return null;
}

export function parseWallSpanSide(value: unknown): WallSpanSide | null {
  if (value === 'left' || value === 'right' || value === 'supplement') return value;
  return null;
}

export function parseWallSpanSource(value: unknown): WallSpanSource | null {
  if (value === 'doctor' || value === 'ai_propose') return value;
  return null;
}

function finiteCoord(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function cloneWallPaintSegment(segment: WallPaintSegment): WallPaintSegment {
  return {
    points: segment.points.map((point) => point.slice()),
    visibleLayers: segment.visibleLayers,
    side: segment.side || null,
    brushRadius: Number.isFinite(Number(segment.brushRadius)) ? Number(segment.brushRadius) : null,
    frameIndex: Number.isFinite(Number(segment.frameIndex)) ? Number(segment.frameIndex) : null,
    paintedAtMs: Number.isFinite(Number(segment.paintedAtMs)) ? Number(segment.paintedAtMs) : null,
    source: parseWallSpanSource(segment.source),
  };
}

function spanCentroid(points: number[][]): number[] | null {
  const usable = points.filter((point) => point.length >= 2);
  if (!usable.length) return null;
  const sum = usable.reduce((acc, point) => [acc[0] + Number(point[0]), acc[1] + Number(point[1])], [0, 0]);
  return [sum[0] / usable.length, sum[1] / usable.length];
}

export function assignSpanSides(
  segments: WallPaintSegment[],
  attract?: number[] | null,
): WallPaintSegment[] {
  const cloned = segments.map(cloneWallPaintSegment);
  if (cloned.length < 1) return cloned;
  const ranked = cloned
    .map((segment, index) => ({ index, centroid: spanCentroid(segment.points) }))
    .filter((item) => item.centroid);
  ranked.sort((a, b) => (a.centroid![0] - b.centroid![0]));
  if (ranked.length === 1 && attract && attract.length >= 2) {
    cloned[ranked[0].index].side = ranked[0].centroid![0] <= Number(attract[0]) ? 'left' : 'right';
    return cloned;
  }
  ranked.forEach((item, rank) => {
    if (rank === 0) cloned[item.index].side = 'left';
    else if (rank === ranked.length - 1) cloned[item.index].side = 'right';
    else cloned[item.index].side = 'supplement';
  });
  return cloned;
}

export function normalizeWallPaintSegments(raw: unknown): WallPaintSegment[] {
  if (!Array.isArray(raw)) return [];
  const next: WallPaintSegment[] = [];
  for (const item of raw) {
    if (Array.isArray(item) && item.length >= 2 && Array.isArray(item[0])) {
      const points = (item as number[][]).filter((point) => point.length >= 2).map((point) => [Number(point[0]), Number(point[1])]);
      if (points.length >= 2) next.push({ points, visibleLayers: 3 });
      continue;
    }
    if (!item || typeof item !== 'object') continue;
    const rec = item as {
      points?: unknown;
      visibleLayers?: unknown;
      side?: unknown;
      brushRadius?: unknown;
      frameIndex?: unknown;
      paintedAtMs?: unknown;
      source?: unknown;
    };
    if (!Array.isArray(rec.points)) continue;
    const points = rec.points
      .filter((point): point is number[] => Array.isArray(point) && point.length >= 2)
      .map((point) => [Number(point[0]), Number(point[1])]);
    if (points.length < 2) continue;
    next.push({
      points,
      visibleLayers: parseVisibleLayerCount(rec.visibleLayers) || 3,
      side: parseWallSpanSide(rec.side),
      brushRadius: finiteCoord(rec.brushRadius),
      frameIndex: finiteCoord(rec.frameIndex),
      paintedAtMs: finiteCoord(rec.paintedAtMs),
      source: parseWallSpanSource(rec.source),
    });
  }
  return next.slice(0, MAX_WALL_PAINT_SEGMENTS);
}

export function appendWallPaintSegment(
  existing: WallPaintSegment[],
  next: WallPaintSegment,
  max = MAX_WALL_PAINT_SEGMENTS,
): WallPaintSegment[] {
  if (next.points.length < 2) return existing.map(cloneWallPaintSegment);
  return [...existing.map(cloneWallPaintSegment), cloneWallPaintSegment(next)].slice(-max);
}

export function spanLayerBadge(visibleLayers: WallVisibleLayerCount | number | null | undefined, zh: boolean): string {
  if (visibleLayers === 1) return zh ? '一层' : '1L';
  if (visibleLayers === 2) return zh ? '两层' : '2L';
  return zh ? '三层' : '3L';
}

export function spanLayerSummary(
  segments: Array<{ visibleLayers?: WallVisibleLayerCount | number | null }> | null | undefined,
  zh: boolean,
): string {
  const layers = (segments || []).map((segment) => spanLayerBadge(segment.visibleLayers || 3, zh));
  if (layers.length < 2) return layers[0] || '';
  return zh ? `左${layers[0]} / 右${layers[1]}` : `${layers[0]} / ${layers[1]}`;
}

export function setLastSpanVisibleLayers(
  existing: WallPaintSegment[],
  visibleLayers: WallVisibleLayerCount,
): WallPaintSegment[] {
  return setSpanVisibleLayers(existing, existing.length - 1, visibleLayers);
}

export function setSpanVisibleLayers(
  existing: WallPaintSegment[],
  index: number,
  visibleLayers: WallVisibleLayerCount,
): WallPaintSegment[] {
  if (!existing.length) return [];
  const target = Number.isFinite(index) && index >= 0 && index < existing.length
    ? index
    : existing.length - 1;
  return existing.map((segment, i) => (
    i === target
      ? { ...cloneWallPaintSegment(segment), visibleLayers }
      : cloneWallPaintSegment(segment)
  ));
}

export function popLastWallPaintSegment(existing: WallPaintSegment[]): WallPaintSegment[] {
  if (existing.length <= 1) return [];
  return existing.slice(0, -1).map(cloneWallPaintSegment);
}

export function hitTestWallPaintSegment(
  segments: WallPaintSegment[],
  point: number[],
  hitPx = 14,
): number {
  const x = Number(point[0]);
  const y = Number(point[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return -1;
  let best = -1;
  let bestDist = hitPx;
  segments.forEach((segment, index) => {
    const pts = segment.points || [];
    for (let i = 1; i < pts.length; i += 1) {
      const a = pts[i - 1];
      const b = pts[i];
      if (!a || a.length < 2 || !b || b.length < 2) continue;
      const vx = Number(b[0]) - Number(a[0]);
      const vy = Number(b[1]) - Number(a[1]);
      const len2 = vx * vx + vy * vy;
      const t = len2 < 1e-10
        ? 0
        : Math.max(0, Math.min(1, ((x - Number(a[0])) * vx + (y - Number(a[1])) * vy) / len2));
      const hx = Number(a[0]) + vx * t;
      const hy = Number(a[1]) + vy * t;
      const dist = Math.hypot(x - hx, y - hy);
      if (dist < bestDist) {
        bestDist = dist;
        best = index;
      }
    }
  });
  return best;
}

export function wallPaintSegmentsFromLegacy(wall: number[][] | null | undefined): WallPaintSegment[] {
  if (!wall || wall.length < 2) return [];
  return [{ points: wall.map((point) => point.slice()), visibleLayers: 3 }];
}

export function anatomyTargetMeta(target: WallAnatomyTarget | null | undefined) {
  return WALL_ANATOMY_TARGETS.find((item) => item.id === target) || WALL_ANATOMY_TARGETS[0];
}

export function parseWallVisibility(value: unknown): WallVisibility | null {
  if (value === 'clear' || value === 'blurry' || value === 'unseen') return value;
  return null;
}

export function parseSerosaAnchorMode(value: unknown): SerosaAnchorMode | null {
  if (value === 'bilateral' || value === 'unilateral' || value === 'unanalyzable') return value;
  return null;
}

export function parseDoctorDepthScreen(value: unknown): DoctorDepthScreen | null {
  if (value === 'shallow_clear' || value === 'outer_clear' || value === 'boundary_unclear') return value;
  return null;
}

export function parseDoctorPromptConfidence(value: unknown): DoctorPromptConfidence | null {
  if (value === 'high' || value === 'mid' || value === 'low') return value;
  return null;
}

export function depthScreenConflictsAi(
  screen: DoctorDepthScreen | null | undefined,
  aiTop1: string | null | undefined,
): boolean {
  const token = String(aiTop1 || '').toUpperCase().replace('T4+', 'T4');
  if (screen === 'shallow_clear') return token === 'T3' || token === 'T4';
  if (screen === 'outer_clear') return token === 'T1';
  return false;
}

export function suggestedAnatomyFromScreen(
  screen: DoctorDepthScreen | null | undefined,
): WallAnatomyTarget {
  if (screen === 'shallow_clear') return 3;
  return 1;
}

export function parseInterruptVerdict(value: unknown): InterruptVerdict | null {
  if (
    value === 'continuous'
    || value === 'suspected'
    || value === 'interrupted'
    || value === 'cannot_judge'
  ) return value;
  return null;
}

export function visibilityLabel(value: WallVisibility | null | undefined, zh: boolean): string {
  const hit = WALL_VISIBILITY_OPTIONS.find((item) => item.id === value);
  if (!hit) return zh ? '未标' : 'unset';
  return zh ? hit.zh : hit.en;
}

export function anchorModeLabel(value: SerosaAnchorMode | null | undefined, zh: boolean): string {
  const hit = SEROSA_ANCHOR_OPTIONS.find((item) => item.id === value);
  if (!hit) return zh ? '未标' : 'unset';
  return zh ? hit.zh : hit.en;
}

export function verdictLabel(value: InterruptVerdict | null | undefined, zh: boolean): string {
  if (value === 'suspected') return zh ? '疑似中断' : 'suspected';
  if (value === 'interrupted') return zh ? '中断' : 'interrupted';
  if (value === 'cannot_judge') return zh ? '无法判断' : 'cannot judge';
  return zh ? '连续' : 'continuous';
}

export function interruptVerdictFromRaw(input: {
  interrupted?: boolean;
  suspected?: boolean;
  visibility?: WallVisibility | null;
  anchorMode?: SerosaAnchorMode | null;
}): InterruptVerdict {
  if (input.visibility === 'unseen' || input.anchorMode === 'unanalyzable') {
    return 'cannot_judge';
  }
  if (input.interrupted) {
    return input.visibility === 'blurry' ? 'suspected' : 'interrupted';
  }
  if (input.suspected || input.visibility === 'blurry') return 'suspected';
  return 'continuous';
}

export function cycleInterruptVerdict(
  current: InterruptVerdict | null | undefined,
): InterruptVerdict {
  const index = INTERRUPT_VERDICT_ORDER.indexOf(current || 'continuous');
  return INTERRUPT_VERDICT_ORDER[(index + 1) % INTERRUPT_VERDICT_ORDER.length];
}

export function verdictIsInterrupted(value: InterruptVerdict | null | undefined): boolean {
  return value === 'interrupted';
}

export function paintLineHint(target: WallAnatomyTarget | null | undefined, zh: boolean): string {
  const meta = anatomyTargetMeta(target);
  return zh ? meta.lineZh : meta.lineEn;
}

export function paintToolLabel(painting: boolean, zh: boolean, spanCount = 0): string {
  if (!painting) return zh ? '补画短线' : 'Paint flanks';
  if (spanCount <= 0) return zh ? '画一侧短线' : 'Paint one flank';
  if (spanCount === 1) return zh ? '继续画对侧' : 'Draw other flank';
  return zh ? '再加一段' : 'Add another span';
}

export function analysisFocusHint(zh: boolean): string {
  return zh
    ? '只选一处最深浸润区。可点 AI 建议，或自己点病灶最靠近或最突出于外侧胃壁的位置。选完才开始分析。这不是突破点。再点同一处可取消。'
    : 'Select one deepest-invasion region. Tap the AI suggestion, or mark where the lesion is closest to or most proud of the outer wall. Analysis starts after you choose. This is not a breach. Tap the same spot to clear.';
}

export function addAnalysisFocusPoint(
  points: number[][],
  next: number[],
  hitPx = FOCUS_HIT_PX,
): number[][] {
  const x = Number(next[0]);
  const y = Number(next[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return points.slice();
  const hit = points.findIndex((point) => {
    const dx = Number(point[0]) - x;
    const dy = Number(point[1]) - y;
    return (dx * dx) + (dy * dy) <= hitPx * hitPx;
  });
  if (hit >= 0) return points.filter((_, index) => index !== hit);
  return [[x, y]];
}

/** Confirm a deepest mark. Same spot does not toggle it off. */
export function confirmAnalysisFocusPoint(
  points: number[][],
  next: number[],
  hitPx = FOCUS_HIT_PX,
): number[][] {
  const x = Number(next[0]);
  const y = Number(next[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return points.slice();
  const hit = points.findIndex((point) => {
    const dx = Number(point[0]) - x;
    const dy = Number(point[1]) - y;
    return (dx * dx) + (dy * dy) <= hitPx * hitPx;
  });
  if (hit >= 0) return [[x, y]];
  return [[x, y]];
}

export function wallPromptProse(input: {
  targetLayers?: WallAnatomyTarget | null;
  visibility?: WallVisibility | null;
  anchorMode?: SerosaAnchorMode | null;
  focusCount?: number;
  zh: boolean;
}): string {
  const meta = anatomyTargetMeta(input.targetLayers);
  const parts: string[] = [];
  parts.push(input.zh
    ? `目标：${meta.askZh}。请框选病灶并确认最深浸润区。两侧短线仅在自动锚点失败时手画。`
    : `Target: ${meta.askEn} Box the lesion and confirm the deepest-invasion region. Paint short flanks only if auto-anchors fail.`);
  if (input.visibility) {
    parts.push(input.zh
      ? `可见度：${visibilityLabel(input.visibility, true)}。看不清不等于中断。`
      : `Visibility: ${visibilityLabel(input.visibility, false)}. Not seen is not interruption.`);
  }
  if (input.anchorMode) {
    parts.push(input.zh
      ? `提示方式：${anchorModeLabel(input.anchorMode, true)}。`
      : `Prompt: ${anchorModeLabel(input.anchorMode, false)}.`);
  }
  if ((input.focusCount || 0) > 0) {
    parts.push(input.zh
      ? '已确认最深浸润区，开始分析。'
      : 'Deepest-invasion region confirmed; analysis has started.');
  }
  return parts.join(input.zh ? '' : ' ');
}

export type WallProtocolKind =
  | 'ghost'
  | 'unseen'
  | 'need_lesion'
  | 'need_spans'
  | 'need_other_flank'
  | 'need_deepest'
  | 'need_confirm_deepest'
  | 'review_both'
  | 'joined'
  | 'joined_overshoot'
  | 'stopped'
  | 'angle_sign'
  | 'special_anatomy'
  | 'ready';

export function wallProtocolBanner(input: {
  hasLesion?: boolean;
  spanCount?: number;
  focusCount?: number;
  joinVerdict?: string | null;
  joinNoteZh?: string;
  joinNoteEn?: string;
  spanLayers?: string;
  visibility?: WallVisibility | null;
  ghost?: boolean;
  keyframeTimeSec?: number | null;
  autoAnchors?: 'ok' | 'failed' | null;
  proposedDeepestCount?: number;
  deepestDisagree?: boolean;
  zh: boolean;
}): { kind: WallProtocolKind; text: string } {
  const spanCount = input.spanCount || 0;
  const focusCount = input.focusCount || 0;
  const layers = input.spanLayers ? (input.zh ? ` ${input.spanLayers}。` : ` ${input.spanLayers}.`) : '';
  if (input.ghost) {
    const t = Number.isFinite(input.keyframeTimeSec) ? Number(input.keyframeTimeSec).toFixed(2) : '';
    return {
      kind: 'ghost',
      text: input.zh
        ? `邻帧残影${t ? `（关键帧 ${t}s）` : ''}。对照浆膜还在不在。不定 cT。`
        : `Neighbor-frame ghost${t ? ` (keyframe ${t}s)` : ''}. Check whether serosa is still there. Not a definite cT.`,
    };
  }
  if (input.visibility === 'unseen') {
    return {
      kind: 'unseen',
      text: input.zh
        ? '本帧看不清。看不清不等于中断。不定 cT。'
        : 'This frame is not seen. Not seen is not interruption. Not a definite cT.',
    };
  }
  if (!input.hasLesion) {
    return {
      kind: 'need_lesion',
      text: input.zh ? '先框选病灶，再确认最深浸润区。' : 'Box the lesion first, then confirm the deepest-invasion region.',
    };
  }
  if (focusCount <= 0) {
    return {
      kind: 'need_confirm_deepest',
      text: input.zh
        ? ((input.proposedDeepestCount || 0) > 0
          ? '请先选一处最深浸润区。可点 AI 建议，或自己点。选完才开始分析。这不是突破点。'
          : '请先选一处最深浸润区。点病灶最靠近或最突出于外侧胃壁的位置。选完才开始分析。这不是突破点。')
        : ((input.proposedDeepestCount || 0) > 0
          ? 'Select one deepest-invasion region first. Tap the AI suggestion or mark your own. Analysis starts after that. This is not a breach.'
          : 'Select one deepest-invasion region first. Tap where the lesion is closest to or most proud of the outer wall. Analysis starts after that. This is not a breach.'),
    };
  }
  if (spanCount <= 0) {
    return {
      kind: 'need_spans',
      text: input.zh
        ? (input.autoAnchors === 'failed'
          ? '自动双侧锚点不够稳。请左右各画一段看得见的胃壁，不必穿过病灶。'
          : '两侧短线可手动画。自动锚点失败时再补。不必穿过病灶。')
        : (input.autoAnchors === 'failed'
          ? 'Auto flanks are not stable. Paint a short visible wall span on each flank. Do not cross the mass.'
          : 'Paint short flanks if needed. Use this when auto-anchors fail. Do not cross the mass.'),
    };
  }
  if (spanCount === 1) {
    return {
      kind: 'need_other_flank',
      text: input.zh
        ? '已留 1 段。请再画对侧看得见的胃壁。'
        : '1 span kept. Paint the opposite visible flank.',
    };
  }
  if (input.joinVerdict === 'joined' || input.joinVerdict === 'joined_overshoot'
    || input.joinVerdict === 'stopped' || input.joinVerdict === 'angle_sign'
    || input.joinVerdict === 'special_anatomy') {
    return {
      kind: input.joinVerdict,
      text: input.zh
        ? `${input.joinNoteZh || '两侧已留下。不定 cT。'}${layers}`
        : `${input.joinNoteEn || 'Both flanks are kept. Not a definite cT.'}${layers}`,
    };
  }
  return {
    kind: 'ready',
    text: input.zh
      ? '病灶和最深区已齐。可点辅助分析。不定 cT。'
      : 'Lesion and deepest region are ready. Assist is optional. Not a definite cT.',
  };
}
