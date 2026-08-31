/**
 * Two-click wall-thickness caliper. The doctor taps the inner and outer
 * edges of visible normal wall; the distance becomes the recommended
 * expected-line brush radius (half the thickness, clamped). Soft draft
 * only. Does not unlock definite cT.
 */

export const WALL_BRUSH_MIN = 3;
export const WALL_BRUSH_MAX = 22;

export type WallThicknessMeasure = {
  inner: number[];
  outer: number[];
  thicknessPx: number;
  recommendedBrush: number;
  brushUsed: number | null;
  frameIndex: number | null;
  videoTimeSec: number | null;
  paintedAtMs: number;
};

export type WallStrokeRecenter = {
  points: number[][];
  applied: boolean;
  offsetPx: number;
  reason: 'no_measure' | 'invalid_stroke' | 'outside_local_window' | 'offset_too_large' | 'already_centered' | 'recentered';
};

function finitePoint(point: number[] | null | undefined): number[] | null {
  if (!Array.isArray(point) || point.length < 2) return null;
  const x = Number(point[0]);
  const y = Number(point[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
}

export function thicknessPxFromCaliper(
  inner: number[] | null | undefined,
  outer: number[] | null | undefined,
): number {
  const a = finitePoint(inner);
  const b = finitePoint(outer);
  if (!a || !b) return 0;
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

export function clampWallBrushRadius(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 8;
  return Math.max(WALL_BRUSH_MIN, Math.min(WALL_BRUSH_MAX, Math.round(n)));
}

/** Brush radius so the disc diameter matches measured wall thickness. */
export function recommendedBrushFromThickness(thicknessPx: number): number {
  if (!Number.isFinite(thicknessPx) || thicknessPx <= 0) return 8;
  return clampWallBrushRadius(thicknessPx / 2);
}

/**
 * Keep the doctor's drawn heading intact for audit, but use a modest normal
 * shift toward the measured wall midline while tracing. A caliper far from the
 * stroke or a large offset is deliberately ignored rather than guessed.
 */
export function recenterWallStroke(
  stroke: number[][] | null | undefined,
  measure: WallThicknessMeasure | null | undefined,
): WallStrokeRecenter {
  const points = (stroke || [])
    .map(finitePoint)
    .filter((point): point is number[] => Boolean(point));
  const original = points.map((point) => point.slice());
  if (!measure) return { points: original, applied: false, offsetPx: 0, reason: 'no_measure' };
  if (points.length < 2) return { points: original, applied: false, offsetPx: 0, reason: 'invalid_stroke' };
  const inner = finitePoint(measure.inner);
  const outer = finitePoint(measure.outer);
  if (!inner || !outer || measure.thicknessPx < 1.5) {
    return { points: original, applied: false, offsetPx: 0, reason: 'invalid_stroke' };
  }
  const nx = outer[0] - inner[0];
  const ny = outer[1] - inner[1];
  const length = Math.hypot(nx, ny);
  if (length < 1e-6) return { points: original, applied: false, offsetPx: 0, reason: 'invalid_stroke' };
  const ux = nx / length;
  const uy = ny / length;
  const tx = -uy;
  const ty = ux;
  const midpoint = points.reduce((sum, point) => [sum[0] + point[0], sum[1] + point[1]], [0, 0])
    .map((value) => value / points.length);
  const target = [(inner[0] + outer[0]) / 2, (inner[1] + outer[1]) / 2];
  const dx = midpoint[0] - target[0];
  const dy = midpoint[1] - target[1];
  const along = Math.abs(dx * tx + dy * ty);
  const offset = dx * ux + dy * uy;
  const localWindow = Math.max(32, measure.thicknessPx * 3);
  const maxShift = Math.max(2, measure.thicknessPx * 0.65);
  if (along > localWindow) {
    return { points: original, applied: false, offsetPx: Number(offset.toFixed(1)), reason: 'outside_local_window' };
  }
  if (Math.abs(offset) > maxShift) {
    return { points: original, applied: false, offsetPx: Number(offset.toFixed(1)), reason: 'offset_too_large' };
  }
  if (Math.abs(offset) < 0.75) {
    return { points: original, applied: false, offsetPx: Number(offset.toFixed(1)), reason: 'already_centered' };
  }
  const shifted = points.map((point) => [point[0] - offset * ux, point[1] - offset * uy]);
  return {
    points: shifted,
    applied: true,
    offsetPx: Number(offset.toFixed(1)),
    reason: 'recentered',
  };
}

export function completeWallThicknessMeasure(input: {
  inner: number[];
  outer: number[];
  brushUsed?: number | null;
  frameIndex?: number | null;
  videoTimeSec?: number | null;
  paintedAtMs?: number;
}): WallThicknessMeasure | null {
  const inner = finitePoint(input.inner);
  const outer = finitePoint(input.outer);
  if (!inner || !outer) return null;
  const thicknessPx = Number(thicknessPxFromCaliper(inner, outer).toFixed(1));
  if (thicknessPx < 1.5) return null;
  const recommendedBrush = recommendedBrushFromThickness(thicknessPx);
  return {
    inner,
    outer,
    thicknessPx,
    recommendedBrush,
    brushUsed: input.brushUsed == null ? recommendedBrush : clampWallBrushRadius(input.brushUsed),
    frameIndex: Number.isFinite(Number(input.frameIndex)) ? Number(input.frameIndex) : null,
    videoTimeSec: Number.isFinite(Number(input.videoTimeSec)) ? Number(input.videoTimeSec) : null,
    paintedAtMs: Number.isFinite(Number(input.paintedAtMs)) ? Number(input.paintedAtMs) : Date.now(),
  };
}

export function hydrateWallThicknessMeasure(raw: unknown): WallThicknessMeasure | null {
  if (!raw || typeof raw !== 'object') return null;
  const rec = raw as Record<string, unknown>;
  return completeWallThicknessMeasure({
    inner: Array.isArray(rec.inner) ? rec.inner as number[] : [],
    outer: Array.isArray(rec.outer) ? rec.outer as number[] : [],
    brushUsed: rec.brushUsed as number | null | undefined,
    frameIndex: rec.frameIndex as number | null | undefined,
    videoTimeSec: rec.videoTimeSec as number | null | undefined,
    paintedAtMs: rec.paintedAtMs as number | undefined,
  });
}

export function thicknessCaliperHint(pendingCount: number, zh: boolean): string {
  if (pendingCount <= 0) {
    return zh
      ? '十字对准正常胃壁内缘点一下，再点外缘。厚度会转成笔刷宽度，可再改。不定 cT。'
      : 'Aim the cross at the inner wall edge, then the outer edge. Thickness sets the brush; you can still edit it. Not a definite cT.';
  }
  return zh
    ? '再点浆膜外缘（或另一侧壁缘）完成测厚。'
    : 'Tap the outer serosal edge (or the other wall edge) to finish the caliper.';
}
