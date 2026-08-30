/**
 * Unwrap the painted wall corridor the same way layer tracing does:
 * along the infiltration path (outer pixel band), across the brush,
 * then mark vanish / bright-dark-bright breaks from the live readout.
 * Draft only; does not unlock cT.
 */

import { closestOnPoly, densifySmooth, type Pt } from './wall-polyline';
import { WALL_LAYER_NAMES } from './wall-layer-breach';
import {
  detectBrightDarkInterrupt,
  doctorClinicalIds,
  interruptDipIndex,
} from './wall-layer-interrupt';
import {
  drawFourWallInterfaces,
  drawBreakthroughMarks,
  drawHeadingFlanks,
  drawThinBandRibbons,
  lesionToward,
  thinBandColor,
} from './wall-thin-bands';
import { headingFlankRuns } from './wall-ordered-track';

export const PAINTED_BAND_COLORS = ['#7dd3fc', '#c4b5fd', '#86efac', '#fcd34d', '#fb7185'] as const;

export type CorridorStation = {
  point: Pt;
  nx: number;
  ny: number;
};

export type CorridorProjection = {
  s: number;
  n: number;
};

export type InfiltrationFocusKind = 'vanish' | 'interrupt' | 'contact' | 'mid';

export type InfiltrationFocus = {
  index: number;
  kind: InfiltrationFocusKind;
};

export type CorridorBreakMark = {
  index: number;
  layer: 1 | 2 | 3 | 4 | 5;
  kind: InfiltrationFocusKind;
  s: number;
  n: number;
  label: string;
};

export type CorridorLayerZoom = {
  index: number;
  layer: 1 | 2 | 3 | 4 | 5;
  nameZh: string;
  nameEn: string;
  color: string;
  dataUrl: string;
  focusKind: InfiltrationFocusKind;
  hero?: boolean;
};

type InterruptHint = {
  layer?: number;
  verdict?: string;
  interrupted?: boolean;
  suspected?: boolean;
};

export function corridorToward(
  wall: number[][],
  lesion?: number[][] | null,
  lumenPrefer?: [number, number] | null,
): Pt | null {
  const lesionPts = (lesion || []).filter((point) => point.length >= 2);
  if (lesionPts.length) {
    const cx = lesionPts.reduce((sum, point) => sum + point[0], 0) / lesionPts.length;
    const cy = lesionPts.reduce((sum, point) => sum + point[1], 0) / lesionPts.length;
    return [cx, cy];
  }
  if (lumenPrefer && Number.isFinite(lumenPrefer[0]) && Number.isFinite(lumenPrefer[1])) {
    const mid = wall[Math.floor(wall.length / 2)];
    if (!mid) return null;
    return [mid[0] + lumenPrefer[0] * 40, mid[1] + lumenPrefer[1] * 40];
  }
  return null;
}

export function buildCorridorStations(wall: number[][], toward: Pt | null): CorridorStation[] {
  const spine = densifySmooth(wall, false, 80, 220);
  if (spine.length < 2) return [];
  return spine.map((point, index) => {
    const prev = spine[Math.max(0, index - 1)];
    const next = spine[Math.min(spine.length - 1, index + 1)];
    let tx = next[0] - prev[0];
    let ty = next[1] - prev[1];
    const tlen = Math.hypot(tx, ty) || 1;
    tx /= tlen;
    ty /= tlen;
    let nx = -ty;
    let ny = tx;
    if (toward && (toward[0] - point[0]) * nx + (toward[1] - point[1]) * ny < 0) {
      nx = -nx;
      ny = -ny;
    }
    return { point, nx, ny };
  });
}

export function projectOntoCorridor(
  point: number[],
  stations: CorridorStation[],
): CorridorProjection | null {
  if (point.length < 2 || stations.length < 2) return null;
  let best = Infinity;
  let bestIndex = 0;
  let bestN = 0;
  for (let index = 0; index < stations.length; index += 1) {
    const station = stations[index];
    const dx = point[0] - station.point[0];
    const dy = point[1] - station.point[1];
    const n = dx * station.nx + dy * station.ny;
    const t = -dx * station.ny + dy * station.nx;
    const dist = Math.hypot(n, t);
    if (dist < best) {
      best = dist;
      bestIndex = index;
      bestN = n;
    }
  }
  if (best > 96) return null;
  return {
    s: bestIndex / Math.max(1, stations.length - 1),
    n: bestN,
  };
}

export function firstVanishIndex(mask?: boolean[] | null): number | null {
  if (!mask?.length) return null;
  const index = mask.findIndex(Boolean);
  return index >= 0 ? index : null;
}

export function contactIndexOnBand(band: number[][], lesion?: number[][] | null): number | null {
  const wall = (lesion || []).filter((point) => point.length >= 2);
  if (band.length < 2 || wall.length < 3) return null;
  let best = 0;
  let bestDist = Infinity;
  for (let index = 0; index < band.length; index += 1) {
    const hit = closestOnPoly(band[index] as Pt, wall as Pt[], true);
    if (hit.dist < bestDist) {
      bestDist = hit.dist;
      best = index;
    }
  }
  return best;
}

export function interruptLooksBroken(item?: InterruptHint | null): boolean {
  if (!item) return false;
  return item.verdict === 'interrupted'
    || item.verdict === 'suspected'
    || Boolean(item.interrupted)
    || Boolean(item.suspected);
}

export function pickInfiltrationFocus(input: {
  bandLength: number;
  imaginary?: boolean[] | null;
  interrupt?: InterruptHint | null;
  darkDipIndex?: number | null;
  contactIndex?: number | null;
}): InfiltrationFocus {
  const vanish = firstVanishIndex(input.imaginary);
  if (vanish != null) return { index: vanish, kind: 'vanish' };
  if (interruptLooksBroken(input.interrupt) && input.darkDipIndex != null) {
    return { index: input.darkDipIndex, kind: 'interrupt' };
  }
  if (input.contactIndex != null) return { index: input.contactIndex, kind: 'contact' };
  return {
    index: Math.max(0, Math.floor(Math.max(1, input.bandLength) * 0.55)),
    kind: 'mid',
  };
}

function sampleImage(
  data: Uint8ClampedArray,
  width: number,
  height: number,
  x: number,
  y: number,
): [number, number, number] {
  const xi = Math.max(0, Math.min(width - 1, Math.round(x)));
  const yi = Math.max(0, Math.min(height - 1, Math.round(y)));
  const i = (yi * width + xi) * 4;
  return [data[i], data[i + 1], data[i + 2]];
}

function luma(rgb: [number, number, number]): number {
  return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
}

function layerMeta(index: number, targetLayers: 1 | 2 | 3) {
  const ids = doctorClinicalIds(targetLayers);
  const layer = ids[Math.min(index, ids.length - 1)] || ((index + 1) as 1 | 2 | 3 | 4 | 5);
  const name = WALL_LAYER_NAMES.find((item) => item.layer === layer) || WALL_LAYER_NAMES[Math.min(index, 4)];
  return {
    index,
    layer,
    nameZh: name.zh,
    nameEn: name.en,
    color: thinBandColor(layer),
  };
}

function breakLabel(kind: InfiltrationFocusKind, interrupt?: InterruptHint | null): string {
  if (kind === 'vanish') return 'lost echo';
  if (kind === 'interrupt') {
    return interrupt?.verdict === 'interrupted' || interrupt?.interrupted ? 'break' : 'suspected';
  }
  if (kind === 'contact') return 'contact';
  return '';
}

function toStripY(n: number, half: number, outH: number): number {
  return ((n / half) * 0.5 + 0.5) * (outH - 1);
}

export function renderPaintedCorridor(input: {
  image: HTMLImageElement;
  wall: number[][];
  bands?: number[][][];
  imaginary?: boolean[][];
  interrupts?: InterruptHint[] | null;
  brushRadius?: number | null;
  lesion?: number[][] | null;
  lumenPrefer?: [number, number] | null;
  targetLayers?: 1 | 2 | 3;
  outWidth?: number;
}): { dataUrl: string; spatialCrop: string; unwrap: string; layerZooms: CorridorLayerZoom[]; heroZoom: CorridorLayerZoom | null; breaks: CorridorBreakMark[] } | null {
  if (typeof document === 'undefined') return null;
  const painted = (input.wall || []).filter((point) => point.length >= 2);
  const bands = (input.bands || []).filter((band) => band.length >= 2);
  const outer = bands.length ? bands[bands.length - 1] : [];
  const wall = outer.length >= 3 ? outer : (painted.length >= 3 ? painted : []);
  if (wall.length < 3) return null;
  const toward = corridorToward(wall, input.lesion, input.lumenPrefer);
  const stations = buildCorridorStations(wall, toward);
  if (stations.length < 2) return null;

  const brush = Math.max(4, Math.min(28, Number(input.brushRadius) || 8));
  let half = brush;
  bands.forEach((band) => {
    band.forEach((point) => {
      const hit = projectOntoCorridor(point, stations);
      if (hit) half = Math.max(half, Math.abs(hit.n) + 2);
    });
  });
  half = Math.max(8, Math.min(40, half));

  const src = document.createElement('canvas');
  src.width = input.image.naturalWidth || input.image.width;
  src.height = input.image.naturalHeight || input.image.height;
  const srcCtx = src.getContext('2d', { willReadFrequently: true });
  if (!srcCtx) return null;
  srcCtx.drawImage(input.image, 0, 0);
  let pixels: ImageData;
  try {
    pixels = srcCtx.getImageData(0, 0, src.width, src.height);
  } catch {
    return null;
  }

  const outW = Math.max(640, Math.min(920, input.outWidth || 800));
  const outH = Math.max(240, Math.round(half * 18));
  const canvas = document.createElement('canvas');
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const image = ctx.createImageData(outW, outH);
  for (let x = 0; x < outW; x += 1) {
    const station = stations[Math.round((x / Math.max(1, outW - 1)) * (stations.length - 1))];
    for (let y = 0; y < outH; y += 1) {
      const n = ((y / Math.max(1, outH - 1)) * 2 - 1) * half;
      const [r, g, b] = sampleImage(
        pixels.data,
        src.width,
        src.height,
        station.point[0] + station.nx * n,
        station.point[1] + station.ny * n,
      );
      const i = (y * outW + x) * 4;
      image.data[i] = r;
      image.data[i + 1] = g;
      image.data[i + 2] = b;
      image.data[i + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);

  type Hit = CorridorProjection & { index: number };
  const mapBand = (band: number[][]): Hit[] => band
    .map((point, index) => {
      const hit = projectOntoCorridor(point, stations);
      if (!hit || Math.abs(hit.n) > half + 4) return null;
      return { ...hit, index };
    })
    .filter((hit): hit is Hit => hit != null);

  const target = input.targetLayers === 1 || input.targetLayers === 2 || input.targetLayers === 3
    ? input.targetLayers
    : 3;
  const breaks: CorridorBreakMark[] = [];

  bands.forEach((band, index) => {
    const projected = mapBand(band);
    if (projected.length < 2) return;
    const color = PAINTED_BAND_COLORS[index % PAINTED_BAND_COLORS.length];
    const next = index + 1 < bands.length ? mapBand(bands[index + 1]) : [];
    if (next.length >= 2) {
      ctx.beginPath();
      projected.forEach((hit, cursor) => {
        const x = hit.s * (outW - 1);
        const y = toStripY(hit.n, half, outH);
        if (cursor === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      for (let cursor = next.length - 1; cursor >= 0; cursor -= 1) {
        const hit = next[cursor];
        ctx.lineTo(hit.s * (outW - 1), toStripY(hit.n, half, outH));
      }
      ctx.closePath();
      ctx.fillStyle = `${color}2e`;
      ctx.fill();
    }
    const mask = input.imaginary?.[index] || [];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    let drawing = false;
    let dashed: boolean | null = null;
    const flush = () => {
      if (drawing) ctx.stroke();
      drawing = false;
    };
    projected.forEach((hit) => {
      const x = hit.s * (outW - 1);
      const y = toStripY(hit.n, half, outH);
      const nextDash = Boolean(mask[hit.index]);
      if (dashed !== nextDash) {
        flush();
        ctx.beginPath();
        ctx.setLineDash(nextDash ? [5, 3] : []);
        ctx.moveTo(x, y);
        dashed = nextDash;
        drawing = true;
        return;
      }
      ctx.lineTo(x, y);
      drawing = true;
    });
    flush();
    ctx.setLineDash([]);
  });

  ctx.strokeStyle = 'rgba(248,250,252,0.22)';
  ctx.setLineDash([3, 3]);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, outH / 2);
  ctx.lineTo(outW, outH / 2);
  ctx.stroke();
  ctx.setLineDash([]);

  const layerZooms: CorridorLayerZoom[] = [];
  bands.forEach((band, index) => {
    const meta = layerMeta(index, target);
    const interrupt = (input.interrupts || []).find((item) => item.layer === meta.layer)
      || input.interrupts?.[index]
      || null;
    const values = band.map((point) => luma(sampleImage(pixels.data, src.width, src.height, point[0], point[1])));
    const raw = detectBrightDarkInterrupt(values);
    const focus = pickInfiltrationFocus({
      bandLength: band.length,
      imaginary: input.imaginary?.[index],
      interrupt: interrupt || (raw.interrupted || raw.suspected
        ? { verdict: raw.interrupted ? 'interrupted' : 'suspected', interrupted: raw.interrupted, suspected: raw.suspected }
        : null),
      darkDipIndex: interruptDipIndex(values),
      contactIndex: contactIndexOnBand(band, input.lesion),
    });
    const pick = band[Math.max(0, Math.min(band.length - 1, focus.index))]
      || band[Math.floor(band.length / 2)];
    if (!pick) return;
    const projected = projectOntoCorridor(pick, stations);
    if (projected && (focus.kind === 'vanish' || focus.kind === 'interrupt')) {
      breaks.push({
        index,
        layer: meta.layer,
        kind: focus.kind,
        s: projected.s,
        n: projected.n,
        label: breakLabel(focus.kind, interrupt),
      });
    }
    const zoom = cropFocusZoom({
      image: input.image,
      cx: pick[0],
      cy: pick[1],
      srcSize: Math.max(18, Math.min(28, brush * 1.6)),
      outSize: 360,
      color: meta.color,
    });
    if (zoom) {
      layerZooms.push({
        ...meta,
        dataUrl: zoom,
        focusKind: focus.kind,
      });
    }
  });

  breaks.forEach((mark) => {
    const x = mark.s * (outW - 1);
    const y = toStripY(mark.n, half, outH);
    const width = Math.max(14, outW * 0.055);
    ctx.fillStyle = 'rgba(251, 113, 133, 0.20)';
    ctx.fillRect(x - width / 2, 0, width, outH);
    ctx.strokeStyle = 'rgba(251, 113, 133, 0.95)';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, outH);
    ctx.stroke();
    ctx.fillStyle = '#fb7185';
    ctx.beginPath();
    ctx.moveTo(x, 3);
    ctx.lineTo(x - 6, 13);
    ctx.lineTo(x + 6, 13);
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, 4.2, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = '#fb7185';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.font = '600 11px ui-sans-serif, system-ui, sans-serif';
    ctx.fillStyle = '#fecdd3';
    ctx.fillText(mark.label, Math.min(outW - 72, x + 8), 16);
  });

  let heroZoom: CorridorLayerZoom | null = null;
  const heroSource = [...layerZooms]
    .reverse()
    .find((item) => item.focusKind === 'interrupt' || item.focusKind === 'vanish');
  if (heroSource) {
    const band = bands[heroSource.index];
    const interrupt = (input.interrupts || []).find((item) => item.layer === heroSource.layer);
    const values = band.map((point) => luma(sampleImage(pixels.data, src.width, src.height, point[0], point[1])));
    const focus = pickInfiltrationFocus({
      bandLength: band.length,
      imaginary: input.imaginary?.[heroSource.index],
      interrupt,
      darkDipIndex: interruptDipIndex(values),
      contactIndex: contactIndexOnBand(band, input.lesion),
    });
    const pick = band[Math.max(0, Math.min(band.length - 1, focus.index))];
    if (pick) {
      const dataUrl = cropFocusZoom({
        image: input.image,
        cx: pick[0],
        cy: pick[1],
        srcSize: Math.max(14, Math.min(20, brush * 1.15)),
        outSize: 360,
        color: heroSource.color,
      });
      if (dataUrl) {
        heroZoom = {
          ...heroSource,
          dataUrl,
          hero: true,
          focusKind: focus.kind,
        };
      }
    }
  }

  const spatial = renderSpatialBandCrop({
    image: input.image,
    bands,
    imaginary: input.imaginary,
    interrupts: input.interrupts,
    lesion: input.lesion,
    wall: painted.length >= 2 ? painted : wall,
    targetLayers: target,
  });

  const unwrap = renderFilledUnwrap({
    image: input.image,
    stations,
    bands,
    imaginary: input.imaginary,
    interrupts: input.interrupts,
    lesion: input.lesion,
    targetLayers: target,
    half,
  });

  return {
    dataUrl: unwrap || canvas.toDataURL('image/jpeg', 0.92),
    spatialCrop: spatial?.dataUrl || '',
    layerZooms,
    heroZoom,
    breaks,
    unwrap: unwrap || '',
  };
}

function renderFilledUnwrap(input: {
  image: HTMLImageElement;
  stations: CorridorStation[];
  bands: number[][][];
  imaginary?: boolean[][];
  interrupts?: InterruptHint[] | null;
  lesion?: number[][] | null;
  targetLayers: 1 | 2 | 3;
  half: number;
}): string {
  if (typeof document === 'undefined' || input.stations.length < 2) return '';
  const src = document.createElement('canvas');
  src.width = input.image.naturalWidth || input.image.width;
  src.height = input.image.naturalHeight || input.image.height;
  const srcCtx = src.getContext('2d', { willReadFrequently: true });
  if (!srcCtx) return '';
  srcCtx.drawImage(input.image, 0, 0);
  let pixels: ImageData;
  try {
    pixels = srcCtx.getImageData(0, 0, src.width, src.height);
  } catch {
    return '';
  }
  const outW = 800;
  const outH = 176;
  const canvas = document.createElement('canvas');
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  const image = ctx.createImageData(outW, outH);
  for (let x = 0; x < outW; x += 1) {
    const station = input.stations[Math.round((x / Math.max(1, outW - 1)) * (input.stations.length - 1))];
    for (let y = 0; y < outH; y += 1) {
      const n = ((y / Math.max(1, outH - 1)) * 2 - 1) * input.half;
      const [r, g, b] = sampleImage(
        pixels.data,
        src.width,
        src.height,
        station.point[0] + station.nx * n,
        station.point[1] + station.ny * n,
      );
      const i = (y * outW + x) * 4;
      image.data[i] = r;
      image.data[i + 1] = g;
      image.data[i + 2] = b;
      image.data[i + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);

  const projected = input.bands.map((band) => band
    .map((point) => projectOntoCorridor(point, input.stations))
    .filter((hit): hit is CorridorProjection => hit != null && Math.abs(hit.n) <= input.half + 4));
  input.bands.forEach((band, index) => {
    const hits = projected[index];
    if (hits.length < 2) return;
    const meta = layerMeta(index, input.targetLayers);
    const halfBand = index === 0 && projected[index + 1]
      ? Math.max(2.2, Math.abs(hits[Math.floor(hits.length / 2)].n - (projected[index + 1][Math.floor(projected[index + 1].length / 2)]?.n || hits[0].n)) * 0.48)
      : 3.4;
    ctx.beginPath();
    hits.forEach((hit, cursor) => {
      const x = hit.s * (outW - 1);
      const y = toStripY(hit.n - halfBand, input.half, outH);
      if (cursor === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    for (let cursor = hits.length - 1; cursor >= 0; cursor -= 1) {
      const hit = hits[cursor];
      ctx.lineTo(hit.s * (outW - 1), toStripY(hit.n + halfBand, input.half, outH));
    }
    ctx.closePath();
    const faded = (input.imaginary?.[index] || []).filter(Boolean).length > (input.imaginary?.[index]?.length || 1) * 0.45;
    ctx.fillStyle = meta.color;
    ctx.globalAlpha = faded ? 0.22 : 0.48;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    hits.forEach((hit, cursor) => {
      const x = hit.s * (outW - 1);
      const y = toStripY(hit.n, input.half, outH);
      if (cursor === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = meta.color;
    ctx.lineWidth = 2.2;
    ctx.stroke();
  });
  drawFourWallInterfaces(ctx, input.bands, (x, y) => {
    const hit = projectOntoCorridor([x, y], input.stations);
    return {
      x: (hit?.s || 0) * (outW - 1),
      y: toStripY(hit?.n || 0, input.half, outH),
    };
  }, {
    lesion: input.lesion,
    imaginary: input.imaginary,
    asInterfaces: input.bands.length === 4,
  });

  const hero = input.bands[input.bands.length - 1];
  if (hero?.length) {
    const interrupt = (input.interrupts || []).find((item) => item.layer === doctorClinicalIds(input.targetLayers).at(-1))
      || input.interrupts?.at(-1)
      || null;
    const focus = pickInfiltrationFocus({
      bandLength: hero.length,
      imaginary: input.imaginary?.[input.bands.length - 1],
      interrupt,
      contactIndex: contactIndexOnBand(hero, input.lesion),
    });
    if (focus.kind === 'vanish' || focus.kind === 'interrupt') {
      const pick = hero[Math.max(0, Math.min(hero.length - 1, focus.index))];
      const hit = pick ? projectOntoCorridor(pick, input.stations) : null;
      if (hit) {
        const x = hit.s * (outW - 1);
        const width = Math.max(10, outW * 0.04);
        ctx.fillStyle = 'rgba(251, 113, 133, 0.22)';
        ctx.fillRect(x - width / 2, 0, width, outH);
      }
    }
  }
  return canvas.toDataURL('image/jpeg', 0.9);
}

export function periLesionViewBox(input: {
  bands: number[][][];
  lesion?: number[][] | null;
  width: number;
  height: number;
  win?: number;
}): { x1: number; y1: number; x2: number; y2: number } | null {
  const bands = (input.bands || []).filter((band) => band.length >= 2);
  const lesion = (input.lesion || []).filter((point) => point.length >= 2);
  if (!bands.length && lesion.length < 3) return null;
  const win = Math.max(72, input.win ?? 110);
  if (lesion.length >= 3) {
    const cx = lesion.reduce((sum, point) => sum + point[0], 0) / lesion.length;
    const cy = lesion.reduce((sum, point) => sum + point[1], 0) / lesion.length;
    return {
      x1: Math.max(0, cx - win),
      y1: Math.max(0, cy - win),
      x2: Math.min(input.width, cx + win),
      y2: Math.min(input.height, cy + win),
    };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  bands.forEach((band) => {
    band.forEach((point) => {
      minX = Math.min(minX, point[0]);
      minY = Math.min(minY, point[1]);
      maxX = Math.max(maxX, point[0]);
      maxY = Math.max(maxY, point[1]);
    });
  });
  if (!Number.isFinite(minX)) return null;
  const midX = (minX + maxX) / 2;
  const midY = (minY + maxY) / 2;
  return {
    x1: Math.max(0, midX - win),
    y1: Math.max(0, midY - win),
    x2: Math.min(input.width, midX + win),
    y2: Math.min(input.height, midY + win),
  };
}

function cropFocusZoom(input: {
  image: HTMLImageElement;
  cx: number;
  cy: number;
  srcSize: number;
  outSize: number;
  color: string;
}): string {
  const canvas = document.createElement('canvas');
  canvas.width = input.outSize;
  canvas.height = input.outSize;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  ctx.fillStyle = '#050506';
  ctx.fillRect(0, 0, input.outSize, input.outSize);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  const half = input.srcSize / 2;
  ctx.drawImage(
    input.image,
    input.cx - half,
    input.cy - half,
    input.srcSize,
    input.srcSize,
    0,
    0,
    input.outSize,
    input.outSize,
  );
  ctx.strokeStyle = input.color;
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, input.outSize - 3, input.outSize - 3);
  return canvas.toDataURL('image/jpeg', 0.9);
}

export function renderSpatialBandCrop(input: {
  image: HTMLImageElement;
  bands?: number[][][];
  imaginary?: boolean[][];
  interrupts?: Array<{ layer?: number; verdict?: string; interrupted?: boolean; suspected?: boolean }> | null;
  lesion?: number[][] | null;
  wall?: number[][] | null;
  targetLayers?: 1 | 2 | 3;
}): { dataUrl: string; focusKind: InfiltrationFocusKind } | null {
  if (typeof document === 'undefined') return null;
  const bands = (input.bands || []).filter((band) => band.length >= 2);
  if (!bands.length) return null;
  const srcW = input.image.naturalWidth || input.image.width;
  const srcH = input.image.naturalHeight || input.image.height;
  const box = periLesionViewBox({
    bands,
    lesion: input.lesion,
    width: srcW,
    height: srcH,
    win: 110,
  });
  if (!box) return null;
  const minX = box.x1;
  const minY = box.y1;
  const maxX = box.x2;
  const maxY = box.y2;
  const width = Math.max(32, maxX - minX);
  const height = Math.max(32, maxY - minY);
  const scale = Math.min(840 / width, 640 / height, 8);
  const outW = Math.max(1, Math.round(width * scale));
  const outH = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(input.image, minX, minY, width, height, 0, 0, outW, outH);
  const map = (x: number, y: number) => ({
    x: (x - minX) * scale,
    y: (y - minY) * scale,
  });
  const lesion = input.lesion || [];
  if (lesion.length >= 3) {
    ctx.beginPath();
    lesion.forEach((point, index) => {
      const mapped = map(point[0], point[1]);
      if (index === 0) ctx.moveTo(mapped.x, mapped.y);
      else ctx.lineTo(mapped.x, mapped.y);
    });
    ctx.closePath();
    ctx.strokeStyle = 'rgba(191, 219, 254, 0.9)';
    ctx.lineWidth = 1.4;
    ctx.stroke();
  }
  drawThinBandRibbons(ctx, bands, map, {
    targetLayers: input.targetLayers,
    lesion,
    imaginary: input.imaginary,
  });
  drawFourWallInterfaces(ctx, bands, map, {
    lesion,
    imaginary: input.imaginary,
    toward: lesionToward(lesion),
    asInterfaces: bands.length === 4,
  });
  if ((input.wall || []).length >= 2) {
    drawHeadingFlanks(ctx, input.wall || [], lesion, map);
  }
  const target = input.targetLayers === 2 || input.targetLayers === 3 ? input.targetLayers : 1;
  const flanks = headingFlankRuns(input.wall || bands[0] || [], lesion);
  const labelAt = flanks[0]?.[Math.min(8, (flanks[0]?.length || 1) - 1)] || bands[0]?.[4];
  if (labelAt) {
    ctx.font = '700 16px ui-sans-serif, system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    bands.forEach((band, index) => {
      const meta = layerMeta(index, target);
      const pick = band[Math.min(6, band.length - 1)] || labelAt;
      const { x, y } = map(pick[0], pick[1]);
      ctx.fillStyle = 'rgba(2, 6, 23, 0.62)';
      const text = meta.nameEn;
      const width = ctx.measureText(text).width + 8;
      ctx.fillRect(x + 8, y - 10, width, 20);
      ctx.fillStyle = meta.color;
      ctx.fillText(text, x + 12, y);
    });
  }
  const hero = bands[bands.length - 1];
  const interrupt = (input.interrupts || []).find((item) => item.layer === doctorClinicalIds(target).at(-1))
    || input.interrupts?.at(-1)
    || null;
  const focus = pickInfiltrationFocus({
    bandLength: hero.length,
    imaginary: input.imaginary?.[bands.length - 1],
    interrupt,
    contactIndex: contactIndexOnBand(hero, lesion),
  });
  drawBreakthroughMarks(ctx, bands, map, {
    wall: input.wall,
    lesion,
    imaginary: input.imaginary,
    interrupts: input.interrupts,
    targetLayers: target,
  });
  return {
    dataUrl: canvas.toDataURL('image/jpeg', 0.92),
    focusKind: focus.kind,
  };
}

export function corridorNeedsPaint(wall: number[][], bands: number[][][]): boolean {
  return wall.length < 3 && bands.every((band) => band.length < 2);
}
