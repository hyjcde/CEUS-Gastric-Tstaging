/**
 * Auto bilateral wall anchors from a lesion mask.
 * Ports scripts/wall_lesion_aware_cluster.py:provisional_wall_from_lesion
 * and splits the heading outside the mass. Does not invent layers in the
 * lesion. Auto spans are not bilateral gold. Does not unlock cT.
 */

import { deepestInvasionPoint } from './wall-echo-clarify';
import { headingFlankRuns } from './wall-ordered-track';
import {
  assignSpanSides,
  type WallPaintSegment,
  type WallSpanSource,
  type WallVisibleLayerCount,
} from './reader/wall-prompt';
import {
  centroidPts,
  cleanPts,
  hypotPts,
  polyLength,
  type Pt,
} from './wall-polyline';

export const MAX_DEEPEST_CANDIDATES = 1;
export const MIN_FLANK_LENGTH_PX = 12;
export const DEEPEST_DISAGREE_MIN_PX = 18;

export type ProposedDeepestRegion = {
  center: Pt;
  radius: number;
  source: 'ai';
};

export type ProposeWallReason = 'ok' | 'need_lesion' | 'need_more_spans';

export type ProposedWallFromLesion = {
  available: boolean;
  reason: ProposeWallReason;
  heading: Pt[];
  segments: WallPaintSegment[];
  deepestCandidates: ProposedDeepestRegion[];
  aiDeepest: ProposedDeepestRegion | null;
  noteZh: string;
  noteEn: string;
};

function principalAxis(pts: Pt[]): Pt {
  const center = centroidPts(pts);
  if (!center) return [1, 0];
  let xx = 0;
  let xy = 0;
  let yy = 0;
  pts.forEach((point) => {
    const dx = point[0] - center[0];
    const dy = point[1] - center[1];
    xx += dx * dx;
    xy += dx * dy;
    yy += dy * dy;
  });
  const trace = xx + yy;
  const det = xx * yy - xy * xy;
  const disc = Math.sqrt(Math.max(0, (trace * trace) / 4 - det));
  const lambda = trace / 2 + disc;
  let ax = xy;
  let ay = lambda - xx;
  if (Math.hypot(ax, ay) < 1e-8) {
    ax = lambda - yy;
    ay = xy;
  }
  const n = Math.hypot(ax, ay) || 1;
  return [ax / n, ay / n];
}

function clipPt(point: Pt, width: number, height: number): Pt {
  return [
    Math.max(1, Math.min(width - 2, point[0])),
    Math.max(1, Math.min(height - 2, point[1])),
  ];
}

function pickTwoLongest(runs: Pt[][]): Pt[][] {
  return runs
    .slice()
    .sort((a, b) => polyLength(b) - polyLength(a))
    .slice(0, 2)
    .filter((run) => run.length >= 4 && polyLength(run) >= MIN_FLANK_LENGTH_PX);
}

function axialSplit(heading: Pt[], lesion: Pt[], padPx: number): Pt[][] {
  if (heading.length < 4 || lesion.length < 2) return [];
  const axis = principalAxis(heading.length >= 3 ? heading : lesion);
  const origin = heading[0];
  const along = (point: Pt) => (point[0] - origin[0]) * axis[0] + (point[1] - origin[1]) * axis[1];
  const projs = lesion.map(along);
  const tmin = Math.min(...projs) - padPx;
  const tmax = Math.max(...projs) + padPx;
  const left: Pt[] = [];
  const right: Pt[] = [];
  heading.forEach((point) => {
    const t = along(point);
    if (t < tmin) left.push(point);
    else if (t > tmax) right.push(point);
  });
  return pickTwoLongest([left, right]);
}

export function frameSizeFromLesion(lesion: number[][] | null | undefined): { width: number; height: number } {
  const pts = cleanPts(lesion);
  if (!pts.length) return { width: 320, height: 240 };
  const xs = pts.map((point) => point[0]);
  const ys = pts.map((point) => point[1]);
  return {
    width: Math.max(64, Math.ceil(Math.max(...xs) + 48)),
    height: Math.max(64, Math.ceil(Math.max(...ys) + 48)),
  };
}

export function deepestRegionRadius(lesion: number[][] | null | undefined): number {
  const pts = cleanPts(lesion);
  const center = centroidPts(pts);
  if (!center || pts.length < 3) return 12;
  const maxR = Math.max(...pts.map((point) => hypotPts(point, center)));
  return Math.max(10, Math.min(28, maxR * 0.18));
}

export function deepestRegionsDisagree(
  doctor: number[] | ProposedDeepestRegion | null | undefined,
  ai: number[] | ProposedDeepestRegion | null | undefined,
  threshPx?: number,
): boolean {
  const a = Array.isArray(doctor) ? doctor : doctor?.center;
  const b = Array.isArray(ai) ? ai : ai?.center;
  if (!a || a.length < 2 || !b || b.length < 2) return false;
  const ra = Array.isArray(doctor) ? 0 : (doctor?.radius || 0);
  const rb = Array.isArray(ai) ? 0 : (ai?.radius || 0);
  const limit = Math.max(DEEPEST_DISAGREE_MIN_PX, ra, rb, Number(threshPx) || 0);
  return hypotPts([Number(a[0]), Number(a[1])], [Number(b[0]), Number(b[1])]) > limit;
}

export function hitProposedDeepestRegion(
  candidates: ProposedDeepestRegion[] | null | undefined,
  point: number[],
): ProposedDeepestRegion | null {
  if (!point || point.length < 2) return null;
  const x = Number(point[0]);
  const y = Number(point[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  let best: ProposedDeepestRegion | null = null;
  let bestDist = Infinity;
  (candidates || []).forEach((item) => {
    const dist = hypotPts(item.center, [x, y]);
    const hit = Math.max(10, item.radius);
    if (dist <= hit && dist < bestDist) {
      best = item;
      bestDist = dist;
    }
  });
  return best;
}

export function hasDoctorPaintedSpans(
  segments: Array<{ source?: WallSpanSource | null }> | null | undefined,
): boolean {
  return (segments || []).some((segment) => segment.source !== 'ai_propose');
}

/** Keep doctor strokes. Replace or drop leftover auto spans. */
export function mergeAutoProposedSpans(
  existing: WallPaintSegment[] | null | undefined,
  proposed: WallPaintSegment[] | null | undefined,
): WallPaintSegment[] {
  const current = existing || [];
  if (hasDoctorPaintedSpans(current)) return current.map((segment) => ({
    ...segment,
    points: segment.points.map((point) => point.slice()),
  }));
  const next = (proposed || []).filter((segment) => segment.points.length >= 2);
  if (next.length >= 2) return next;
  return [];
}

/**
 * Temporary heading: lesion major axis, shifted toward the deep face,
 * extended past both flanks. Lumen, when present, sets the outward direction.
 */
export function provisionalHeadingFromLesion(
  lesion: number[][] | null | undefined,
  frameSize: { width: number; height: number },
  lumen?: number[][] | null,
): Pt[] {
  const pts = cleanPts(lesion);
  const width = Math.max(8, Number(frameSize.width) || 8);
  const height = Math.max(8, Number(frameSize.height) || 8);
  if (pts.length < 3) return [];
  const center = centroidPts(pts);
  if (!center) return [];
  const axis = principalAxis(pts);
  const originRef = centroidPts(lumen) || center;
  const projs = pts.map((point) => (
    (point[0] - center[0]) * axis[0] + (point[1] - center[1]) * axis[1]
  ));
  const tmin = Math.min(...projs);
  const tmax = Math.max(...projs);
  const pad = Math.max(40, 0.55 * (tmax - tmin));
  const deep = pts.reduce((best, point) => (
    hypotPts(point, originRef) >= hypotPts(best, originRef) ? point : best
  ), pts[0]);
  let ox = deep[0] - center[0];
  let oy = deep[1] - center[1];
  const olen = Math.hypot(ox, oy) || 1;
  ox /= olen;
  oy /= olen;
  const normal: Pt = [-axis[1], axis[0]];
  const halfW = Math.sqrt(
    pts.reduce((sum, point) => {
      const t = (point[0] - center[0]) * normal[0] + (point[1] - center[1]) * normal[1];
      return sum + t * t;
    }, 0) / pts.length,
  );
  const shift = Math.max(4, halfW * 0.35);
  const origin: Pt = [center[0] + ox * shift, center[1] + oy * shift];
  const count = 90;
  const line: Pt[] = [];
  for (let i = 0; i < count; i += 1) {
    const t = tmin - pad + ((tmax + pad) - (tmin - pad)) * (i / (count - 1));
    line.push(clipPt([origin[0] + t * axis[0], origin[1] + t * axis[1]], width, height));
  }
  return line;
}

export function proposeWallFromLesion(input: {
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  frameSize?: { width: number; height: number } | null;
  visibleLayers?: WallVisibleLayerCount | null;
  brushRadius?: number | null;
  frameIndex?: number | null;
  paintedAtMs?: number | null;
}): ProposedWallFromLesion {
  const lesion = cleanPts(input.lesion);
  const lumen = cleanPts(input.lumen);
  const empty: ProposedWallFromLesion = {
    available: false,
    reason: 'need_lesion',
    heading: [],
    segments: [],
    deepestCandidates: [],
    aiDeepest: null,
    noteZh: '请先框选病灶，再确认最深浸润区。',
    noteEn: 'Box the lesion first, then confirm the deepest-invasion region.',
  };
  if (lesion.length < 3) return empty;

  const frameSize = input.frameSize && input.frameSize.width >= 8 && input.frameSize.height >= 8
    ? input.frameSize
    : frameSizeFromLesion(lesion);
  const heading = provisionalHeadingFromLesion(lesion, frameSize, lumen);
  const fromNear = pickTwoLongest(headingFlankRuns(heading, lesion));
  const fromAxis = axialSplit(heading, lesion, 16);
  const flanks = fromNear.length >= 2 ? fromNear : fromAxis;
  const radius = deepestRegionRadius(lesion);
  const origin = centroidPts(lumen) || centroidPts(lesion);
  const wallForDeep = heading.length >= 2 ? heading : null;
  const primary = deepestInvasionPoint({
    lesion,
    lumen: lumen.length >= 3 ? lumen : null,
    wall: wallForDeep,
  });
  const deepestCandidates = primary
    ? [{ center: [primary[0], primary[1]] as Pt, radius, source: 'ai' as const }]
    : [];
  const aiDeepest = deepestCandidates[0] || null;

  const paintedAt = Number.isFinite(Number(input.paintedAtMs)) ? Number(input.paintedAtMs) : Date.now();
  const rawSegments: WallPaintSegment[] = flanks.map((points) => ({
    points: points.map((point) => [point[0], point[1]]),
    visibleLayers: input.visibleLayers || 3,
    brushRadius: Number.isFinite(Number(input.brushRadius)) ? Number(input.brushRadius) : null,
    frameIndex: Number.isFinite(Number(input.frameIndex)) ? Number(input.frameIndex) : null,
    paintedAtMs: paintedAt,
    source: 'ai_propose' as const,
  }));
  const attract = aiDeepest?.center || (origin ? [origin[0], origin[1]] : null);
  const segments = assignSpanSides(rawSegments, attract);

  if (segments.length < 2) {
    return {
      available: false,
      reason: 'need_more_spans',
      heading,
      segments,
      deepestCandidates,
      aiDeepest,
      noteZh: '自动双侧锚点不够稳。请先选一处最深浸润区，选完才开始分析；或左右各画一段看得见的胃壁。',
      noteEn: 'Auto flanks are not stable. Select one deepest region first; analysis starts after that. Or paint a short visible span on each flank.',
    };
  }

  return {
    available: true,
    reason: 'ok',
    heading,
    segments,
    deepestCandidates,
    aiDeepest,
    noteZh: '已按病灶留下两侧短线建议。请先选一处最深浸润区，选完才开始分析。不定 cT。',
    noteEn: 'Auto flanks kept outside the mass. Select one deepest-invasion region first; analysis starts after that. Not a definite cT.',
  };
}
