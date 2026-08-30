/**
 * Map remaining-wall geometry onto the five clinical TAUS layers.
 * Soft readout only. Does not unlock definite cT.
 */

import { WALL_RATIO_BINS } from '@/lib/gc-us-wall-concepts';
import {
  centroidPts,
  closestOnPoly,
  densifySmooth,
  offsetAlongNormals,
  layerOffsetFractions,
  thinLayerOffsets,
  walkClosedArc,
} from './wall-polyline';

export const WALL_LAYER_NAMES = [
  { layer: 1 as const, zh: '黏膜浅层', en: 'Superficial mucosa' },
  { layer: 2 as const, zh: '黏膜肌层', en: 'Muscularis mucosae' },
  { layer: 3 as const, zh: '黏膜下层', en: 'Submucosa' },
  { layer: 4 as const, zh: '固有肌层', en: 'Muscularis propria' },
  { layer: 5 as const, zh: '浆膜', en: 'Serosa' },
] as const;

export type WallLayerTick = {
  layer: 1 | 2 | 3 | 4 | 5;
  nameZh: string;
  nameEn: string;
  status: 'present' | 'thinned' | 'absent' | 'imaginary' | 'unseen';
  labelZh: string;
  labelEn: string;
};

export type WallLayerReadout = {
  layersBreached: 0 | 1 | 2 | 3 | 4 | 5;
  deepestZh: string;
  deepestEn: string;
  remainPx: number | null;
  overshootPx: number | null;
  thicknessPx: number | null;
  ratio: number | null;
  extraserosal: boolean;
  source: 'pixel' | 'geometry' | 'propagated';
  noteZh: string;
  noteEn: string;
  ticks?: WallLayerTick[];
  paintedLayers?: number;
  mucosaBreached?: boolean;
  method?: 'directional' | 'ordered' | 'paint';
  fates?: Array<{
    id: 'mucosa' | 'muscularis' | 'serosa';
    nameZh: string;
    nameEn: string;
    verdict: string;
    labelZh: string;
    labelEn: string;
  }>;
  cluster?: {
    available: boolean;
    pattern: string;
    brightDarkBright: boolean;
    offsets: number[];
    means: number[];
  };
  /** Doctor-chosen remaining layers (1=serosa, 2=MP+serosa, 3=shallow+MP+serosa). */
  targetLayers?: 1 | 2 | 3;
  interrupts?: Array<{
    layer: 1 | 2 | 3 | 4 | 5;
    nameZh: string;
    nameEn: string;
    interrupted: boolean;
    endBright: number;
    midDark: number;
    delta: number;
    suspected?: boolean;
    verdict?: 'continuous' | 'suspected' | 'interrupted' | 'cannot_judge';
    doctorOverride?: boolean;
  }>;
};

export function occupiedRatio(input: {
  remainPx?: number | null;
  overshootPx?: number | null;
  thicknessPx?: number | null;
}): number | null {
  const remain = Number(input.remainPx);
  const overshoot = Number(input.overshootPx);
  const thick = Number(input.thicknessPx);
  if (Number.isFinite(overshoot) && overshoot > 1 && Number.isFinite(thick) && thick > 1) {
    return Math.max(1, (thick + overshoot) / thick);
  }
  if (Number.isFinite(remain) && Number.isFinite(thick) && thick > 1) {
    return Math.max(0, (thick - Math.max(0, remain)) / thick);
  }
  if (Number.isFinite(overshoot) && overshoot > 1) return 1.05;
  return null;
}

export function layersBreachedFromRatio(ratio: number | null): 0 | 1 | 2 | 3 | 4 | 5 {
  if (ratio == null || !Number.isFinite(ratio)) return 0;
  if (ratio >= 1) return 5;
  for (const bin of WALL_RATIO_BINS) {
    if (ratio < bin.max) return bin.layer;
  }
  return 5;
}

export function judgeWallLayerBreach(input: {
  remainPx?: number | null;
  overshootPx?: number | null;
  thicknessPx?: number | null;
  source?: WallLayerReadout['source'];
}): WallLayerReadout {
  const remainPx = Number.isFinite(Number(input.remainPx)) ? Number(Number(input.remainPx).toFixed(1)) : null;
  const overshootPx = Number.isFinite(Number(input.overshootPx)) ? Number(Number(input.overshootPx).toFixed(1)) : null;
  const thicknessPx = Number.isFinite(Number(input.thicknessPx)) ? Number(Number(input.thicknessPx).toFixed(1)) : null;
  const ratio = occupiedRatio({ remainPx, overshootPx, thicknessPx });
  const extraserosal = Boolean(overshootPx != null && overshootPx > 1);
  const layersBreached = layersBreachedFromRatio(ratio);
  const name = WALL_LAYER_NAMES.find((item) => item.layer === layersBreached);
  const source = input.source || 'pixel';
  const deepestZh = name?.zh || (layersBreached === 0 ? '未评估' : '浆膜');
  const deepestEn = name?.en || (layersBreached === 0 ? 'Not assessed' : 'Serosa');
  const noteZh = layersBreached === 0
    ? '还没有可用的余厚，分层只是草稿。'
    : extraserosal
      ? `像素分层：沿突破方向已越过外缘约 ${overshootPx} px，提示累及浆膜以外。请医生核对，不自动改分期。`
      : `像素分层：余厚约 ${remainPx ?? '—'} px，约占壁厚 ${ratio != null ? Math.round(ratio * 100) : '—'}%，最深到${deepestZh}（约 ${layersBreached} 层）。请医生核对，不自动改分期。`;
  const noteEn = layersBreached === 0
    ? 'No remain thickness yet; the layer readout is a draft.'
    : extraserosal
      ? `Pixel layers: the mass overshoots the outer edge by about ${overshootPx} px, suggesting extraserosal involvement. Doctor check only; this does not change Assist stage.`
      : `Pixel layers: remain about ${remainPx ?? '—'} px, occupied ${ratio != null ? Math.round(ratio * 100) : '—'}%, deepest ${deepestEn} (about ${layersBreached} layers). Doctor check only; this does not change Assist stage.`;
  return {
    layersBreached,
    deepestZh,
    deepestEn,
    remainPx,
    overshootPx,
    thicknessPx,
    ratio: ratio == null ? null : Number(ratio.toFixed(3)),
    extraserosal,
    source,
    noteZh,
    noteEn,
  };
}

export function layerBandOffsets(
  wall: number[][],
  center: [number, number] | null,
  thicknessPx: number,
  lesion?: number[][] | null,
): number[][][] {
  return clusterThreeLayersAlongWall({
    wall,
    center,
    lesion,
    thicknessPx,
  });
}

function sampleGray(
  gray: ArrayLike<number>,
  width: number,
  height: number,
  x: number,
  y: number,
): number {
  const xi = Math.round(x);
  const yi = Math.round(y);
  if (xi < 0 || yi < 0 || xi >= width || yi >= height) return -1;
  return Number(gray[yi * width + xi]);
}

function forceThreeStops(profile: number[]): [number, number, number] {
  const n = profile.length;
  if (n < 3) return [0.2, 0.5, 0.85];
  const diffs: Array<{ i: number; mag: number }> = [];
  for (let i = 1; i < n; i += 1) {
    diffs.push({ i, mag: Math.abs(profile[i] - profile[i - 1]) });
  }
  diffs.sort((a, b) => b.mag - a.mag);
  const peaks = diffs.slice(0, 3).map((item) => item.i / (n - 1)).sort((a, b) => a - b);
  const contrast = diffs[0]?.mag || 0;
  if (contrast < 8 || peaks.length < 3) {
    return [0.22, 0.5, 0.82];
  }
  return [
    Math.min(0.35, Math.max(0.12, peaks[0])),
    Math.min(0.7, Math.max(0.35, peaks[1])),
    Math.min(0.95, Math.max(0.62, peaks[2])),
  ];
}

/** Thin layers hugging the lesion face. Count is doctor-chosen 1/2/3. */
export function clusterLayersAlongWall(input: {
  wall: number[][];
  center?: [number, number] | null;
  lesion?: number[][] | null;
  gray?: ArrayLike<number> | null;
  width?: number;
  height?: number;
  thicknessPx?: number | null;
  layerCount?: 1 | 2 | 3;
}): number[][][] {
  const wall = densifySmooth(input.wall || [], false, 320, 1200);
  if (wall.length < 2) return [];
  const lesion = densifySmooth(input.lesion || [], true, 280, 1000);
  let guide = wall;
  if (lesion.length >= 8) {
    const hits = wall.map((point) => closestOnPoly(point, lesion, true));
    const nearest = hits.reduce((best, hit, index) => (
      hit.dist < hits[best].dist ? index : best
    ), 0);
    const thr = Math.min(12, hits[nearest].dist + 6);
    let first = hits.findIndex((hit) => hit.dist <= thr);
    let last = hits.length - 1;
    for (let index = hits.length - 1; index >= 0; index -= 1) {
      if (hits[index].dist <= thr) {
        last = index;
        break;
      }
    }
    if (first < 0) first = nearest;
    const arc = walkClosedArc(lesion, hits[first].index, hits[last].index, hits[nearest].point);
    if (arc.length >= 6) guide = arc;
  }
  const spine = densifySmooth(guide, false, 480, 1200);
  const toward = centroidPts(wall) || input.center || centroidPts(lesion);
  const count = (input.layerCount === 1 || input.layerCount === 2 || input.layerCount === 3)
    ? input.layerCount
    : 3;
  const fracs = layerOffsetFractions(count);
  const triple = thinLayerOffsets(input.thicknessPx);
  const band = triple[2];
  const tuned = fracs.map((frac) => band * frac);
  if (input.gray && input.width && input.height && spine.length && count === 3) {
    const mid = spine[Math.floor(spine.length / 2)];
    const prev = spine[Math.max(0, Math.floor(spine.length / 2) - 1)];
    const next = spine[Math.min(spine.length - 1, Math.floor(spine.length / 2) + 1)];
    let nx = -(next[1] - prev[1]);
    let ny = next[0] - prev[0];
    const nlen = Math.hypot(nx, ny) || 1;
    nx /= nlen;
    ny /= nlen;
    if (toward && (toward[0] - mid[0]) * nx + (toward[1] - mid[1]) * ny < 0) {
      nx = -nx;
      ny = -ny;
    }
    const profile: number[] = [];
    for (let step = 0; step <= 20; step += 1) {
      profile.push(sampleGray(
        input.gray,
        input.width,
        input.height,
        mid[0] + nx * (band * step) / 20,
        mid[1] + ny * (band * step) / 20,
      ));
    }
    const stops = forceThreeStops(profile);
    tuned[0] = band * stops[0];
    tuned[1] = band * stops[1];
    tuned[2] = band * stops[2];
  }
  return tuned.map((offset) => offsetAlongNormals(spine, offset, toward, false));
}

/** Always 3 thin layers hugging the lesion face, even when contrast is flat. */
export function clusterThreeLayersAlongWall(input: {
  wall: number[][];
  center?: [number, number] | null;
  lesion?: number[][] | null;
  gray?: ArrayLike<number> | null;
  width?: number;
  height?: number;
  thicknessPx?: number | null;
}): number[][][] {
  return clusterLayersAlongWall({ ...input, layerCount: 3 });
}
