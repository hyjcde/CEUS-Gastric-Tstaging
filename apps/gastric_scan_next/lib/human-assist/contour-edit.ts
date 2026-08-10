/**
 * Contour edit helpers ported from reader_study_v150 direction_demo + ContactGeom.
 * Keep dense polygons; edit via sparse controlIndices + Gaussian softDeform.
 */

export function clonePoly(pts: number[][]): number[][] {
  return pts.map((p) => [p[0], p[1]]);
}

/** Evenly sample control-point indices along a closed contour (HTML controlIndices). */
export function controlIndices(n: number, count: number): number[] {
  if (n <= 0) return [];
  const k = Math.max(1, Math.min(n, count | 0));
  if (k >= n) return Array.from({ length: n }, (_, i) => i);
  const out: number[] = [];
  for (let i = 0; i < k; i += 1) out.push(Math.round((i * n) / k) % n);
  return [...new Set(out)];
}

/**
 * Soft-drag: neighbors follow with spatial Gaussian (doctor-friendly).
 * Mutates `pts` in place (like ContactGeom.softDeform).
 */
export function softDeform(
  pts: number[][],
  anchorIdx: number,
  newX: number,
  newY: number,
  sigmaPx?: number,
): void {
  if (!pts.length || anchorIdx < 0 || anchorIdx >= pts.length) return;
  const ax = pts[anchorIdx][0];
  const ay = pts[anchorIdx][1];
  const dx = newX - ax;
  const dy = newY - ay;
  if (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6) return;
  const sigma = sigmaPx ?? Math.max(18, Math.min(40, Math.sqrt(pts.length) * 3.2));
  const inv = 1 / (2 * sigma * sigma);
  for (let j = 0; j < pts.length; j += 1) {
    const ddx = pts[j][0] - ax;
    const ddy = pts[j][1] - ay;
    const w = Math.exp(-(ddx * ddx + ddy * ddy) * inv);
    if (w < 0.015) continue;
    pts[j][0] += dx * w;
    pts[j][1] += dy * w;
  }
}

/** Arc-length uniform resample for closed polygons (better than index decimate). */
export function resampleClosed(pts: number[][], targetN: number): number[][] {
  if (!pts.length) return [];
  if (pts.length < 3) return clonePoly(pts);
  const n = Math.max(3, Math.round(targetN));
  if (pts.length === n) return clonePoly(pts);

  const closed = clonePoly(pts);
  // ensure closed ring for length
  const ring = closed.concat([[closed[0][0], closed[0][1]]]);
  const segLen: number[] = [];
  let total = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    const len = Math.hypot(ring[i + 1][0] - ring[i][0], ring[i + 1][1] - ring[i][1]);
    segLen.push(len);
    total += len;
  }
  if (total < 1e-6) return clonePoly(pts);

  const out: number[][] = [];
  for (let k = 0; k < n; k += 1) {
    const target = (k / n) * total;
    let acc = 0;
    let found = false;
    for (let i = 0; i < segLen.length; i += 1) {
      if (acc + segLen[i] >= target || i === segLen.length - 1) {
        const t = segLen[i] < 1e-9 ? 0 : (target - acc) / segLen[i];
        const x = ring[i][0] + (ring[i + 1][0] - ring[i][0]) * t;
        const y = ring[i][1] + (ring[i + 1][1] - ring[i][1]) * t;
        out.push([x, y]);
        found = true;
        break;
      }
      acc += segLen[i];
    }
    if (!found) out.push([ring[0][0], ring[0][1]]);
  }
  return out;
}

/** Cap for editable lesion / wall / lumen contours (keep dense; edit via sparse handles). */
export const LESION_CONTOUR_MAX_POINTS = 2048;
export const WALL_CONTOUR_MAX_POINTS = 1536;
export const LUMEN_CONTOUR_MAX_POINTS = 1024;
/** Explicit “resample” action: still dense enough for irregular lesion borders. */
export const LESION_SIMPLIFY_TARGET = 768;
export const WALL_SIMPLIFY_TARGET = 512;

/**
 * After SAM / load: keep the original dense mesh.
 * Only arc-length resample when point count exceeds maxPoints.
 */
export function prepareEditableContour(
  pts: number[][],
  maxPoints = LESION_CONTOUR_MAX_POINTS,
): number[][] {
  if (pts.length < 3) return clonePoly(pts);
  if (pts.length <= maxPoints) return clonePoly(pts);
  return resampleClosed(pts, maxPoints);
}

/** Draw closed Catmull-Rom-smoothed path in canvas image space (mapped by caller). */
export function strokeSmoothClosed(
  ctx: CanvasRenderingContext2D,
  pts: number[][],
  map: (x: number, y: number) => { x: number; y: number },
): void {
  if (pts.length < 3) return;
  const n = pts.length;
  const mapped = pts.map((p) => map(p[0], p[1]));
  ctx.beginPath();
  ctx.moveTo(mapped[0].x, mapped[0].y);
  for (let i = 0; i < n; i += 1) {
    const p0 = mapped[(i - 1 + n) % n];
    const p1 = mapped[i];
    const p2 = mapped[(i + 1) % n];
    const p3 = mapped[(i + 2) % n];
    for (let t = 0; t < 1; t += 0.34) {
      const t2 = t * t;
      const t3 = t2 * t;
      const x =
        0.5 *
        (2 * p1.x
          + (-p0.x + p2.x) * t
          + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2
          + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3);
      const y =
        0.5 *
        (2 * p1.y
          + (-p0.y + p2.y) * t
          + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2
          + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3);
      ctx.lineTo(x, y);
    }
  }
  ctx.closePath();
}

/** Denser sparse handles so small lesions stay editable without huge grabbers. */
export const LESION_CTRL_COUNT = 28;
export const WALL_CTRL_COUNT = 36;
export const LESION_SOFT_SIGMA = 22;
export const WALL_SOFT_SIGMA = 30;
