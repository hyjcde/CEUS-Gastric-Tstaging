/**
 * Local-style thin wall ribbons: filled mucosa / MP / serosa bands,
 * not a stack of interface polylines. Draft only; does not unlock cT.
 */

import { isFourInterfaceSet } from './wall-directional-interfaces';
import { closestOnPoly, offsetAlongNormals, type Pt } from './wall-polyline';
import { doctorClinicalIds } from './wall-layer-interrupt';
import { firstHeadingEntry, headingThroughMask, HEADING_GAP_PX, nearLesion } from './wall-ordered-track';

export const THIN_BAND_COLORS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: '#facc15',
  2: '#fde68a',
  3: '#fdba74',
  4: '#fb7185',
  5: '#4ade80',
};

// Keep the analysis cue cool and quiet. Yellow dashed interfaces were visually
// confused with an additional doctor-drawn expected line.
export const WALL_INTERFACE_COLORS = ['#fde047', '#38bdf8', '#f472b6', '#4ade80'] as const;

export function thinBandColor(layer: 1 | 2 | 3 | 4 | 5): string {
  return THIN_BAND_COLORS[layer] || '#94a3b8';
}

export function thinBandLayers(target: 1 | 2 | 3, bandCount: number): Array<1 | 2 | 3 | 4 | 5> {
  const ids = doctorClinicalIds(target);
  if (bandCount <= ids.length) return ids.slice(0, Math.max(1, bandCount));
  return Array.from({ length: bandCount }, (_, index) => ids[Math.min(index, ids.length - 1)]);
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function ribbonHalfWidth(band: number[][], neighbors: number[][][], fallback = 4): number {
  if (band.length < 2) return fallback;
  if (!neighbors.length) return fallback;
  const dists: number[] = [];
  const step = Math.max(1, Math.round(band.length / 24));
  for (let index = 0; index < band.length; index += step) {
    const point = band[index] as Pt;
    let best = Infinity;
    neighbors.forEach((other) => {
      if (other.length < 2) return;
      best = Math.min(best, closestOnPoly(point, other as Pt[], false).dist);
    });
    if (Number.isFinite(best)) dists.push(best);
  }
  return Math.max(2.6, Math.min(8.5, (median(dists) || fallback * 2) * 0.52));
}

export function ribbonPolygon(
  band: number[][],
  half: number,
  toward?: Pt | null,
): number[][] {
  if (band.length < 2) return [];
  const inner = offsetAlongNormals(band as Pt[], -half, toward || null, false);
  const outer = offsetAlongNormals(band as Pt[], half, toward || null, false);
  return [...inner, ...outer.slice().reverse()];
}

export function lesionToward(lesion?: number[][] | null): Pt | null {
  const pts = (lesion || []).filter((point) => point.length >= 2);
  if (!pts.length) return null;
  return [
    pts.reduce((sum, point) => sum + point[0], 0) / pts.length,
    pts.reduce((sum, point) => sum + point[1], 0) / pts.length,
  ];
}

function lesionGap(point: Pt, lesion: Pt[]): number {
  if (lesion.length < 3) return 80;
  if (nearLesion(point, lesion, 0)) return 0;
  return closestOnPoly(point, lesion, true).dist;
}

export function drawThinBandRibbons(
  ctx: CanvasRenderingContext2D,
  bands: number[][][],
  map: (x: number, y: number) => { x: number; y: number },
  input: {
    targetLayers?: 1 | 2 | 3;
    lesion?: number[][] | null;
    imaginary?: boolean[][];
  } = {},
): void {
  const usable = bands.filter((band) => band.length >= 2);
  if (!usable.length) return;
  const layers = thinBandLayers(input.targetLayers === 2 || input.targetLayers === 3 ? input.targetLayers : 1, usable.length);
  const toward = lesionToward(input.lesion);
  const lesion = (input.lesion || []).filter((point) => point.length >= 2) as Pt[];
  const exclusive = usable.length >= 3;
  usable.forEach((band, index) => {
    const neighbors = usable.filter((_, other) => other !== index);
    const half = ribbonHalfWidth(band, neighbors, 4);
    const innerPts = exclusive && index > 0
      ? usable[index - 1]
      : offsetAlongNormals(band as Pt[], -half, toward || null, false);
    const outerPts = exclusive && index < usable.length - 1
      ? usable[index + 1]
      : offsetAlongNormals(band as Pt[], half, toward || null, false);
    if (innerPts.length < 2 || outerPts.length < 2) return;
    const last = Math.min(band.length, innerPts.length, outerPts.length) - 1;
    const mask = input.imaginary?.[index] || [];
    const color = thinBandColor(layers[index] || 5);
    for (let cursor = 0; cursor < last; cursor += 1) {
      const gap = lesionGap(band[Math.min(cursor, band.length - 1)] as Pt, lesion);
      const imagined = Boolean(mask[Math.min(cursor, Math.max(0, mask.length - 1))]);
      const t = Math.max(0, Math.min(1, (gap - 6) / 22));
      const innerA = exclusive && index > 0
        ? lerpPt(innerPts[cursor] as Pt, band[cursor] as Pt, 0.5)
        : innerPts[cursor] as Pt;
      const innerB = exclusive && index > 0
        ? lerpPt(innerPts[cursor + 1] as Pt, band[Math.min(cursor + 1, band.length - 1)] as Pt, 0.5)
        : innerPts[cursor + 1] as Pt;
      const outerA = exclusive && index < usable.length - 1
        ? lerpPt(band[cursor] as Pt, outerPts[cursor] as Pt, 0.5)
        : outerPts[cursor] as Pt;
      const outerB = exclusive && index < usable.length - 1
        ? lerpPt(band[Math.min(cursor + 1, band.length - 1)] as Pt, outerPts[cursor + 1] as Pt, 0.5)
        : outerPts[cursor + 1] as Pt;
      ctx.beginPath();
      const a = map(innerA[0], innerA[1]);
      const b = map(innerB[0], innerB[1]);
      const c = map(outerB[0], outerB[1]);
      const d = map(outerA[0], outerA[1]);
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.lineTo(c.x, c.y);
      ctx.lineTo(d.x, d.y);
      ctx.closePath();
      ctx.fillStyle = color;
      // Keep the image readable like the local four-interface probe:
      // interfaces carry the result, while the intervening wash stays subdued.
      ctx.globalAlpha = imagined ? 0.025 : 0.065 + t * 0.055;
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  });
}

function midpointPath(left: number[][], right: number[][]): number[][] {
  const length = Math.min(left.length, right.length);
  return Array.from({ length }, (_, index) => [
    ((left[index]?.[0] || 0) + (right[index]?.[0] || 0)) * 0.5,
    ((left[index]?.[1] || 0) + (right[index]?.[1] || 0)) * 0.5,
  ]);
}

/**
 * Draw the four tracked interfaces. Prefer the joint-DP paths; only derive
 * midlines when an older three-ridge draft is still on screen.
 */
export function drawFourWallInterfaces(
  ctx: CanvasRenderingContext2D,
  bands: number[][][],
  map: (x: number, y: number) => { x: number; y: number },
  input: {
    lesion?: number[][] | null;
    imaginary?: boolean[][];
    toward?: Pt | null;
    asInterfaces?: boolean;
  } = {},
): void {
  const usable = bands.filter((band) => band.length >= 2);
  if (!usable.length) return;
  const tracked = input.asInterfaces || isFourInterfaceSet(usable);
  let interfaces: number[][][] = [];
  if (tracked && usable.length >= 4) {
    interfaces = usable.slice(0, 4);
  } else if (usable.length >= 3) {
    const firstHalf = ribbonHalfWidth(usable[0], usable.slice(1), 4);
    const lastHalf = ribbonHalfWidth(usable[usable.length - 1], usable.slice(0, -1), 4);
    interfaces = [
      offsetAlongNormals(usable[0] as Pt[], -firstHalf, input.toward || null, false),
      midpointPath(usable[0], usable[1]),
      midpointPath(usable[1], usable[2]),
      offsetAlongNormals(usable[2] as Pt[], lastHalf, input.toward || null, false),
    ];
  } else {
    return;
  }
  const lesion = (input.lesion || []).filter((point) => point.length >= 2) as Pt[];
  ctx.save();
  ctx.lineWidth = 1.45;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  interfaces.forEach((path, boundary) => {
    if (path.length < 2) return;
    ctx.strokeStyle = WALL_INTERFACE_COLORS[boundary];
    ctx.globalAlpha = 0.92;
    strokeDashedRuns(ctx, path, (index) => {
      const mask = input.imaginary?.[Math.min(boundary, (input.imaginary?.length || 1) - 1)] || [];
      const point = path[index] as Pt;
      return Boolean(mask[Math.min(index, Math.max(0, mask.length - 1))])
        || nearLesion(point, lesion, HEADING_GAP_PX);
    }, map);
  });
  ctx.globalAlpha = 1;
  ctx.restore();
}

function lerpPt(a: Pt, b: Pt, t: number): Pt {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

function strokeDashedRuns(
  ctx: CanvasRenderingContext2D,
  points: number[][],
  dashedAt: (index: number) => boolean,
  map: (x: number, y: number) => { x: number; y: number },
): void {
  if (points.length < 2) return;
  let mode: boolean | null = null;
  let drawing = false;
  const flush = () => {
    if (drawing) ctx.stroke();
    drawing = false;
  };
  points.forEach((point, index) => {
    if (point.length < 2) return;
    const mapped = map(point[0], point[1]);
    const dash = dashedAt(index);
    if (mode !== dash) {
      flush();
      ctx.beginPath();
      ctx.setLineDash(dash ? [7, 5] : []);
      ctx.moveTo(mapped.x, mapped.y);
      mode = dash;
      drawing = true;
      return;
    }
    ctx.lineTo(mapped.x, mapped.y);
    drawing = true;
  });
  flush();
  ctx.setLineDash([]);
}

export function drawHeadingFlanks(
  ctx: CanvasRenderingContext2D,
  wall: number[][],
  lesion: number[][] | null | undefined,
  map: (x: number, y: number) => { x: number; y: number },
): void {
  if (wall.length < 2) return;
  const through = headingThroughMask(wall, lesion, HEADING_GAP_PX);
  ctx.save();
  ctx.strokeStyle = 'rgba(254, 240, 138, 0.95)';
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  strokeDashedRuns(ctx, wall, (index) => Boolean(through[index]), map);
  ctx.restore();
}

export function drawBandCenterlines(
  ctx: CanvasRenderingContext2D,
  bands: number[][][],
  map: (x: number, y: number) => { x: number; y: number },
  input: {
    targetLayers?: 1 | 2 | 3;
    lesion?: number[][] | null;
    imaginary?: boolean[][];
  } = {},
): void {
  const usable = bands.filter((band) => band.length >= 2);
  if (!usable.length) return;
  const layers = thinBandLayers(input.targetLayers === 2 || input.targetLayers === 3 ? input.targetLayers : 1, usable.length);
  const lesion = (input.lesion || []).filter((point) => point.length >= 2) as Pt[];
  ctx.save();
  ctx.lineWidth = 2.4;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  usable.forEach((band, index) => {
    const mask = input.imaginary?.[index] || [];
    ctx.strokeStyle = thinBandColor(layers[index] || 5);
    ctx.globalAlpha = 0.92;
    strokeDashedRuns(ctx, band, (cursor) => {
      const point = band[cursor] as Pt;
      return Boolean(mask[cursor]) || nearLesion(point, lesion, HEADING_GAP_PX);
    }, map);
  });
  ctx.restore();
}

export function drawBreakthroughCross(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  scale = 1,
): void {
  const arm = 7 * scale;
  ctx.save();
  ctx.lineCap = 'round';
  ctx.strokeStyle = '#f8fafc';
  ctx.lineWidth = 2.2 * scale;
  ctx.beginPath();
  ctx.moveTo(x - arm, y - arm * 1.5);
  ctx.lineTo(x + arm, y + arm * 1.5);
  ctx.stroke();
  ctx.strokeStyle = '#f87171';
  ctx.lineWidth = 1.8 * scale;
  ctx.beginPath();
  ctx.moveTo(x + arm, y - arm * 1.5);
  ctx.lineTo(x - arm, y + arm * 1.5);
  ctx.stroke();
  ctx.restore();
}

export function drawBreakthroughMarks(
  ctx: CanvasRenderingContext2D,
  bands: number[][][],
  map: (x: number, y: number) => { x: number; y: number },
  input: {
    wall?: number[][] | null;
    lesion?: number[][] | null;
    imaginary?: boolean[][];
    interrupts?: Array<{ layer?: number; verdict?: string; interrupted?: boolean; suspected?: boolean }> | null;
    targetLayers?: 1 | 2 | 3;
  } = {},
): void {
  const usable = bands.filter((band) => band.length >= 2);
  const target = input.targetLayers === 2 || input.targetLayers === 3 ? input.targetLayers : 1;
  const ids = doctorClinicalIds(target);
  let pick: number[] | null = null;
  for (let index = usable.length - 1; index >= 0; index -= 1) {
    const band = usable[index];
    const interrupt = (input.interrupts || []).find((item) => item.layer === ids[Math.min(index, ids.length - 1)])
      || input.interrupts?.[index]
      || null;
    const broken = interrupt?.verdict === 'interrupted'
      || interrupt?.verdict === 'suspected'
      || Boolean(interrupt?.interrupted)
      || Boolean(interrupt?.suspected);
    const vanish = (input.imaginary?.[index] || []).findIndex(Boolean);
    const cursor = vanish >= 0 ? vanish : (broken ? Math.floor(band.length * 0.55) : -1);
    if (cursor >= 0) {
      pick = band[Math.max(0, Math.min(band.length - 1, cursor))];
      break;
    }
  }
  if (!pick) pick = firstHeadingEntry(input.wall || [], input.lesion);
  if (!pick) return;
  const mapped = map(pick[0], pick[1]);
  drawBreakthroughCross(ctx, mapped.x, mapped.y);
}
