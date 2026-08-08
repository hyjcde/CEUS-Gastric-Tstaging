/**
 * Stable scribble / lasso stroke helpers for interactive refinement.
 * Keep raw capture dense enough for display, but submit a bounded path.
 */

export type PromptPoint = number[];

const DEFAULT_MIN_STEP_PX = 2;
const DEFAULT_SUBMIT_MAX_POINTS = 48;
const DEFAULT_LASSO_MIN_AREA_PX2 = 64;

export function clonePoints(points: PromptPoint[]): PromptPoint[] {
  return points.map((point) => [Number(point[0]), Number(point[1])]);
}

export function pointDistance(a: PromptPoint, b: PromptPoint): number {
  return Math.hypot(Number(a[0]) - Number(b[0]), Number(a[1]) - Number(b[1]));
}

export function appendPromptPoint(
  points: PromptPoint[],
  next: PromptPoint,
  minStepPx = DEFAULT_MIN_STEP_PX,
): PromptPoint[] {
  if (!Number.isFinite(Number(next[0])) || !Number.isFinite(Number(next[1]))) {
    return clonePoints(points);
  }
  if (!points.length) return [[Number(next[0]), Number(next[1])]];
  const last = points[points.length - 1];
  if (pointDistance(last, next) < minStepPx) return clonePoints(points);
  return [...points, [Number(next[0]), Number(next[1])]];
}

export function appendFinalPromptPoint(
  points: PromptPoint[],
  finalPoint: PromptPoint | null | undefined,
  minStepPx = 0.5,
): PromptPoint[] {
  if (!finalPoint) return clonePoints(points);
  return appendPromptPoint(points, finalPoint, minStepPx);
}

function pathLength(points: PromptPoint[]): number {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    total += pointDistance(points[index - 1], points[index]);
  }
  return total;
}

/** Arc-length resample for open or closed strokes with a hard point budget. */
export function resamplePromptPath(
  points: PromptPoint[],
  maxPoints = DEFAULT_SUBMIT_MAX_POINTS,
  closed = false,
): PromptPoint[] {
  const cleaned = points.filter((point) => (
    Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]))
  ));
  if (cleaned.length <= 2) return clonePoints(cleaned);
  const target = Math.max(2, Math.min(maxPoints, cleaned.length));
  if (cleaned.length <= target) {
    if (closed && cleaned.length >= 3) {
      const first = cleaned[0];
      const last = cleaned[cleaned.length - 1];
      if (pointDistance(first, last) > 0.5) return [...clonePoints(cleaned), [first[0], first[1]]];
    }
    return clonePoints(cleaned);
  }

  const ring = closed
    ? cleaned.concat([[cleaned[0][0], cleaned[0][1]]])
    : cleaned;
  const total = pathLength(ring);
  if (total < 1e-6) return clonePoints(cleaned.slice(0, target));

  const out: PromptPoint[] = [];
  const sampleCount = closed ? target : target;
  for (let sample = 0; sample < sampleCount; sample += 1) {
    const want = closed
      ? (sample / sampleCount) * total
      : (sample / Math.max(1, sampleCount - 1)) * total;
    let acc = 0;
    let found = false;
    for (let index = 0; index < ring.length - 1; index += 1) {
      const a = ring[index];
      const b = ring[index + 1];
      const segment = pointDistance(a, b);
      if (acc + segment >= want || index === ring.length - 2) {
        const t = segment < 1e-9 ? 0 : (want - acc) / segment;
        out.push([
          a[0] + (b[0] - a[0]) * t,
          a[1] + (b[1] - a[1]) * t,
        ]);
        found = true;
        break;
      }
      acc += segment;
    }
    if (!found) out.push([ring[0][0], ring[0][1]]);
  }
  return out;
}

export function polygonAreaAbs(points: PromptPoint[]): number {
  if (points.length < 3) return 0;
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current[0] * next[1] - next[0] * current[1];
  }
  return Math.abs(area) / 2;
}

export function ensureClosedPromptPath(points: PromptPoint[]): PromptPoint[] {
  const cleaned = clonePoints(points);
  if (cleaned.length < 3) return cleaned;
  const first = cleaned[0];
  const last = cleaned[cleaned.length - 1];
  if (pointDistance(first, last) > 0.5) cleaned.push([first[0], first[1]]);
  return cleaned;
}

export type PromptStrokeValidation = {
  ok: boolean;
  reason?: string;
  points: PromptPoint[];
  areaPx2?: number;
  lengthPx?: number;
};

export function prepareSubmitPromptStroke(
  points: PromptPoint[],
  kind: 'scribble' | 'lasso',
  options?: {
    maxPoints?: number;
    minPoints?: number;
    minLengthPx?: number;
    minAreaPx2?: number;
  },
): PromptStrokeValidation {
  const minPoints = options?.minPoints ?? 2;
  const maxPoints = options?.maxPoints ?? (kind === 'lasso' ? 64 : DEFAULT_SUBMIT_MAX_POINTS);
  const minLengthPx = options?.minLengthPx ?? 4;
  const minAreaPx2 = options?.minAreaPx2 ?? DEFAULT_LASSO_MIN_AREA_PX2;
  if (points.length < minPoints) {
    return { ok: false, reason: 'too_few_points', points: clonePoints(points) };
  }
  const lengthPx = pathLength(points);
  if (lengthPx < minLengthPx) {
    return { ok: false, reason: 'too_short', points: clonePoints(points), lengthPx };
  }
  if (kind === 'lasso') {
    const closed = ensureClosedPromptPath(points);
    const areaPx2 = polygonAreaAbs(closed);
    if (areaPx2 < minAreaPx2) {
      return {
        ok: false,
        reason: 'lasso_area_too_small',
        points: closed,
        areaPx2,
        lengthPx,
      };
    }
    return {
      ok: true,
      points: resamplePromptPath(closed, maxPoints, true),
      areaPx2,
      lengthPx,
    };
  }
  return {
    ok: true,
    points: resamplePromptPath(points, maxPoints, false),
    lengthPx,
  };
}

/** Draw a closed polyline without Catmull-Rom overshoot. */
export function strokeClosedPolyline(
  ctx: CanvasRenderingContext2D,
  pts: number[][],
  map: (x: number, y: number) => { x: number; y: number },
): void {
  if (pts.length < 3) return;
  const first = map(pts[0][0], pts[0][1]);
  ctx.beginPath();
  ctx.moveTo(first.x, first.y);
  for (let index = 1; index < pts.length; index += 1) {
    const mapped = map(pts[index][0], pts[index][1]);
    ctx.lineTo(mapped.x, mapped.y);
  }
  ctx.closePath();
}
