/**
 * Local echo clustering on the deepest-invasion narrow band.
 * Purpose: layer draft from bright / mid / dark regions. Not full-image super-resolution.
 * Soft draft only. Does not unlock definite cT.
 */

import { centroidPts, closestOnPoly, hypotPts, type Pt } from './wall-polyline';

export type EchoClass = 'dark' | 'mid' | 'bright';

export type EchoBand = {
  cls: EchoClass;
  fracStart: number;
  fracEnd: number;
};

export type WallEchoClarify = {
  available: boolean;
  origin: Pt;
  quad: Pt[];
  box: { x1: number; y1: number; x2: number; y2: number };
  alongPx: number;
  acrossPx: number;
  classCount: number;
  classes: Array<{ id: EchoClass; mean: number; count: number; nameZh: string; nameEn: string }>;
  bands: EchoBand[];
  patternZh: string;
  patternEn: string;
  noteZh: string;
  noteEn: string;
  cropW: number;
  cropH: number;
  original: Uint8ClampedArray;
  clarified: Uint8ClampedArray;
};

const CLASS_TONE: Record<EchoClass, number> = { dark: 36, mid: 128, bright: 220 };
const CLASS_NAME: Record<EchoClass, { zh: string; en: string }> = {
  dark: { zh: '暗', en: 'dark' },
  mid: { zh: '中', en: 'mid' },
  bright: { zh: '亮', en: 'bright' },
};

const EMPTY: WallEchoClarify = {
  available: false,
  origin: [0, 0],
  quad: [],
  box: { x1: 0, y1: 0, x2: 0, y2: 0 },
  alongPx: 0,
  acrossPx: 0,
  classCount: 0,
  classes: [],
  bands: [],
  patternZh: '',
  patternEn: '',
  noteZh: '请先框选病灶并画邻近胃壁，再在浸润最深窄带做回声聚类。',
  noteEn: 'Box the lesion and paint the adjacent wall first, then cluster echo on the deepest narrow band.',
  cropW: 0,
  cropH: 0,
  original: new Uint8ClampedArray(0),
  clarified: new Uint8ClampedArray(0),
};

function sample(gray: ArrayLike<number>, width: number, height: number, x: number, y: number): number {
  const xi = Math.round(x);
  const yi = Math.round(y);
  if (xi < 0 || yi < 0 || xi >= width || yi >= height) return -1;
  return Number(gray[yi * width + xi]);
}

function kmeans1d(values: number[], k: number, iters = 16): { means: number[]; labels: number[] } {
  const sorted = [...values].sort((left, right) => left - right);
  const means = Array.from({ length: k }, (_, index) => (
    sorted[Math.min(sorted.length - 1, Math.floor((index + 0.5) * sorted.length / k))] || 0
  ));
  const labels = values.map(() => 0);
  for (let iter = 0; iter < iters; iter += 1) {
    for (let index = 0; index < values.length; index += 1) {
      let best = 0;
      let bestD = Infinity;
      for (let cluster = 0; cluster < k; cluster += 1) {
        const dist = Math.abs(values[index] - means[cluster]);
        if (dist < bestD) {
          bestD = dist;
          best = cluster;
        }
      }
      labels[index] = best;
    }
    const sums = Array.from({ length: k }, () => 0);
    const counts = Array.from({ length: k }, () => 0);
    for (let index = 0; index < values.length; index += 1) {
      sums[labels[index]] += values[index];
      counts[labels[index]] += 1;
    }
    for (let cluster = 0; cluster < k; cluster += 1) {
      if (counts[cluster]) means[cluster] = sums[cluster] / counts[cluster];
    }
  }
  return { means, labels };
}

function chooseK(values: number[]): number {
  if (values.length < 24) return 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max - min < 28) return 2;
  return 3;
}

function remapClasses(means: number[], labels: number[]): EchoClass[] {
  const order = means.map((mean, index) => ({ mean, index })).sort((left, right) => left.mean - right.mean);
  const ids: EchoClass[] = order.length >= 3
    ? ['dark', 'mid', 'bright']
    : order.length === 2
      ? ['dark', 'bright']
      : ['mid'];
  const lookup = new Map<number, EchoClass>();
  order.forEach((item, rank) => lookup.set(item.index, ids[Math.min(rank, ids.length - 1)]));
  return labels.map((label) => lookup.get(label) || 'mid');
}

function majorityVote(grid: EchoClass[], width: number, height: number): EchoClass[] {
  const next = grid.slice();
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const tally: Record<EchoClass, number> = { dark: 0, mid: 0, bright: 0 };
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const xx = x + dx;
          const yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= width || yy >= height) continue;
          tally[grid[yy * width + xx]] += 1;
        }
      }
      next[y * width + x] = (['dark', 'mid', 'bright'] as EchoClass[])
        .sort((left, right) => tally[right] - tally[left])[0];
    }
  }
  return next;
}

function collapseBands(row: EchoClass[]): EchoBand[] {
  if (!row.length) return [];
  const bands: EchoBand[] = [];
  let start = 0;
  for (let index = 1; index <= row.length; index += 1) {
    if (index < row.length && row[index] === row[start]) continue;
    bands.push({
      cls: row[start],
      fracStart: start / row.length,
      fracEnd: index / row.length,
    });
    start = index;
  }
  return bands.filter((band) => band.fracEnd - band.fracStart >= 0.08 || bands.length <= 2);
}

function patternText(bands: EchoBand[]): { zh: string; en: string } {
  const zh = bands.map((band) => CLASS_NAME[band.cls].zh).join('-');
  const en = bands.map((band) => CLASS_NAME[band.cls].en).join('-');
  return { zh, en };
}

export function deepestInvasionPoint(input: {
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  wall?: number[][] | null;
}): Pt | null {
  const lesion = (input.lesion || []).filter((point) => point.length >= 2) as Pt[];
  const lumen = (input.lumen || []).filter((point) => point.length >= 2) as Pt[];
  const wall = (input.wall || []).filter((point) => point.length >= 2) as Pt[];
  const origin = centroidPts(lumen) || centroidPts(lesion);
  if (lesion.length >= 3 && origin) {
    const deep = lesion.reduce((best, point) => (
      hypotPts(point, origin) >= hypotPts(best, origin) ? point : best
    ), lesion[0]);
    if (wall.length >= 2) return closestOnPoly(deep, wall, false).point;
    return deep;
  }
  if (wall.length >= 4) {
    const index = Math.min(wall.length - 1, Math.floor(wall.length * 0.82));
    return wall[index];
  }
  return null;
}

export function clarifyDeepestEcho(input: {
  gray: ArrayLike<number>;
  width: number;
  height: number;
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  wall?: number[][] | null;
  brushRadius?: number | null;
  origin?: number[] | null;
}): WallEchoClarify {
  if (input.width < 12 || input.height < 12) return EMPTY;
  const wall = (input.wall || []).filter((point) => point.length >= 2) as Pt[];
  const requested = Array.isArray(input.origin) && input.origin.length >= 2
    ? [Number(input.origin[0]), Number(input.origin[1])] as Pt
    : null;
  const origin = (requested && Number.isFinite(requested[0]) && Number.isFinite(requested[1]))
    ? requested
    : deepestInvasionPoint(input);
  if (!origin) return EMPTY;

  const hit = wall.length >= 2 ? closestOnPoly(origin, wall, false) : { point: origin, index: 0 };
  const a = wall[Math.max(0, hit.index - 1)] || origin;
  const b = wall[Math.min(wall.length - 1, hit.index + 1)] || origin;
  let tx = b[0] - a[0];
  let ty = b[1] - a[1];
  const tlen = Math.hypot(tx, ty) || 1;
  tx /= tlen;
  ty /= tlen;
  let nx = -ty;
  let ny = tx;
  const lumenCenter = centroidPts(input.lumen || []) || centroidPts(input.lesion || []);
  if (lumenCenter && (origin[0] - lumenCenter[0]) * nx + (origin[1] - lumenCenter[1]) * ny < 0) {
    nx = -nx;
    ny = -ny;
  }

  const brush = Math.max(3, Math.min(22, Number(input.brushRadius) || 8));
  const acrossHalf = Math.max(3.2, Math.min(brush * 0.48, 8.5));
  const alongHalf = 22;
  const alongCount = 56;
  const acrossCount = 28;
  const values: number[] = [];
  for (let row = 0; row < acrossCount; row += 1) {
    const across = -acrossHalf + (2 * acrossHalf * row) / Math.max(1, acrossCount - 1);
    for (let col = 0; col < alongCount; col += 1) {
      const along = -alongHalf + (2 * alongHalf * col) / Math.max(1, alongCount - 1);
      const x = origin[0] + tx * along + nx * across;
      const y = origin[1] + ty * along + ny * across;
      const value = sample(input.gray, input.width, input.height, x, y);
      values.push(value < 0 ? 0 : value);
    }
  }
  const usable = values.filter((value) => value > 0);
  if (usable.length < 40) return { ...EMPTY, origin, noteZh: '浸润最深窄带像素不足。', noteEn: 'Too few pixels in the deepest narrow band.' };

  const k = chooseK(usable);
  const clustered = kmeans1d(values, k);
  let classes = remapClasses(clustered.means, clustered.labels);
  classes = majorityVote(classes, alongCount, acrossCount);

  const rowMajor: EchoClass[] = [];
  for (let row = 0; row < acrossCount; row += 1) {
    const slice = classes.slice(row * alongCount, (row + 1) * alongCount);
    const tally: Record<EchoClass, number> = { dark: 0, mid: 0, bright: 0 };
    slice.forEach((cls) => { tally[cls] += 1; });
    rowMajor.push((['dark', 'mid', 'bright'] as EchoClass[]).sort((left, right) => tally[right] - tally[left])[0]);
  }
  const bands = collapseBands(rowMajor);
  const pattern = patternText(bands);
  const classStats = (['dark', 'mid', 'bright'] as EchoClass[]).map((id) => {
    const hits = classes.map((cls, index) => (cls === id ? values[index] : -1)).filter((value) => value >= 0);
    return {
      id,
      mean: hits.length ? hits.reduce((sum, value) => sum + value, 0) / hits.length : 0,
      count: hits.length,
      nameZh: CLASS_NAME[id].zh,
      nameEn: CLASS_NAME[id].en,
    };
  }).filter((item) => item.count > 0);

  const original = new Uint8ClampedArray(alongCount * acrossCount);
  const clarified = new Uint8ClampedArray(alongCount * acrossCount);
  for (let index = 0; index < values.length; index += 1) {
    original[index] = Math.max(0, Math.min(255, Math.round(values[index])));
    clarified[index] = CLASS_TONE[classes[index]];
  }

  const quad: Pt[] = [
    [origin[0] - tx * alongHalf - nx * acrossHalf, origin[1] - ty * alongHalf - ny * acrossHalf],
    [origin[0] + tx * alongHalf - nx * acrossHalf, origin[1] + ty * alongHalf - ny * acrossHalf],
    [origin[0] + tx * alongHalf + nx * acrossHalf, origin[1] + ty * alongHalf + ny * acrossHalf],
    [origin[0] - tx * alongHalf + nx * acrossHalf, origin[1] - ty * alongHalf + ny * acrossHalf],
  ];
  const xs = quad.map((point) => point[0]);
  const ys = quad.map((point) => point[1]);
  const box = {
    x1: Math.max(0, Math.min(...xs) - 4),
    y1: Math.max(0, Math.min(...ys) - 4),
    x2: Math.min(input.width, Math.max(...xs) + 4),
    y2: Math.min(input.height, Math.max(...ys) + 4),
  };
  const used = classStats.map((item) => item.nameZh).join('/');
  const noteZh = `只在浸润最深窄带做回声区聚类（${used}），不是全图超分。沿厚度方向：${pattern.zh || '未分出'}。不定 cT。`;
  const noteEn = `Regional echo clustering on the deepest narrow band only (${classStats.map((item) => item.nameEn).join('/')}), not full-image super-resolution. Across the wall: ${pattern.en || 'unresolved'}. Not a definite cT.`;

  return {
    available: true,
    origin: hit.point,
    quad,
    box,
    alongPx: Number((alongHalf * 2).toFixed(1)),
    acrossPx: Number((acrossHalf * 2).toFixed(1)),
    classCount: classStats.length,
    classes: classStats,
    bands,
    patternZh: pattern.zh,
    patternEn: pattern.en,
    noteZh,
    noteEn,
    cropW: alongCount,
    cropH: acrossCount,
    original,
    clarified,
  };
}

export function grayCropToDataUrl(gray: Uint8ClampedArray, width: number, height: number): string | null {
  if (typeof document === 'undefined' || !width || !height || gray.length < width * height) return null;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const pixels = ctx.createImageData(width, height);
  for (let index = 0; index < width * height; index += 1) {
    const value = gray[index];
    const offset = index * 4;
    pixels.data[offset] = value;
    pixels.data[offset + 1] = value;
    pixels.data[offset + 2] = value;
    pixels.data[offset + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL('image/png');
}
