/**
 * Four ordered wall interfaces, ported from
 * scripts/render_wall_directional_interfaces.py.
 *
 * The doctor stroke is a heading. Unwrap along its normals, jointly track
 * four alternating gray jumps, learn outside the lesion, and dash inside.
 * Single-frame draft only. Does not unlock cT.
 */

import { WALL_LAYER_NAMES } from './wall-layer-breach';
import { nearLesion, type LayerFate } from './wall-ordered-track';
import {
  centroidPts,
  densifySmooth,
  hypotPts,
  polyLength,
  resamplePoly,
  type Pt,
} from './wall-polyline';
import type { LayerStatus, TracedLayer, WallLayerTickDraft, WallLayerTrace } from './wall-layer-trace';

export const OFFSETS = Array.from({ length: 49 }, (_, index) => index - 24);
const STATION_STEP = 2;
const TOP_K = 80;
const INTERFACE_IDS: Array<1 | 3 | 4 | 5> = [1, 3, 4, 5];

export type DirectionalTrack = WallLayerTrace & {
  method: 'directional';
  heading: Pt[];
  interfaces: Pt[][];
  phase: 1 | -1;
  cavitySideSource: 'lumen_center' | 'heuristic' | 'unusable_image_window';
  headingSource: 'stored heading' | 'outside-lesion heading fallback';
};

const EMPTY: DirectionalTrack = {
  available: false,
  paintedLayers: 0,
  layers: [],
  ticks: [],
  wall: [],
  extensionMask: [],
  remainPx: null,
  overshootPx: null,
  thicknessPx: 0,
  layersBreached: 0,
  deepestZh: '未评估',
  deepestEn: 'Not assessed',
  extraserosal: false,
  mucosaBreached: false,
  noteZh: '走行还不够长，没法沿法向展开四条界面。',
  noteEn: 'The heading is too short to unwrap four wall interfaces.',
  method: 'directional',
  heading: [],
  interfaces: [],
  phase: 1,
  cavitySideSource: 'heuristic',
  headingSource: 'stored heading',
  headingFlanks: [],
  fates: [],
};

type Quad = [number, number, number, number];

function sampleBilinear(
  gray: ArrayLike<number>,
  width: number,
  height: number,
  x: number,
  y: number,
): number {
  if (x < 0 || y < 0 || x > width - 1 || y > height - 1) return 0;
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const x1 = Math.min(width - 1, x0 + 1);
  const y1 = Math.min(height - 1, y0 + 1);
  const tx = x - x0;
  const ty = y - y0;
  const a = Number(gray[y0 * width + x0]);
  const b = Number(gray[y0 * width + x1]);
  const c = Number(gray[y1 * width + x0]);
  const d = Number(gray[y1 * width + x1]);
  return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty;
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function percentile(values: number[], q: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.min(sorted.length - 1, Math.round((sorted.length - 1) * q)));
  return sorted[index];
}

function rollingMedian(values: number[], radius = 3): number[] {
  return values.map((_, index) => {
    const lo = Math.max(0, index - radius);
    const hi = Math.min(values.length, index + radius + 1);
    return median(values.slice(lo, hi));
  });
}

function runs(mask: boolean[]): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  let start = -1;
  for (let index = 0; index < mask.length; index += 1) {
    if (mask[index] && start < 0) start = index;
    if ((!mask[index] || index === mask.length - 1) && start >= 0) {
      out.push([start, mask[index] && index === mask.length - 1 ? index : index - 1]);
      start = -1;
    }
  }
  return out;
}

function gaussKernel(sigma: number, radius: number): number[] {
  const kernel: number[] = [];
  let sum = 0;
  for (let offset = -radius; offset <= radius; offset += 1) {
    const value = Math.exp(-(offset * offset) / (2 * sigma * sigma));
    kernel.push(value);
    sum += value;
  }
  return kernel.map((value) => value / sum);
}

function convAxis(
  src: Float32Array,
  rows: number,
  cols: number,
  kernel: number[],
  alongCols: boolean,
): Float32Array {
  const radius = (kernel.length - 1) >> 1;
  const out = new Float32Array(src.length);
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      let acc = 0;
      for (let tap = -radius; tap <= radius; tap += 1) {
        const rr = alongCols ? Math.max(0, Math.min(rows - 1, row + tap)) : row;
        const cc = alongCols ? col : Math.max(0, Math.min(cols - 1, col + tap));
        acc += src[rr * cols + cc] * kernel[tap + radius];
      }
      out[row * cols + col] = acc;
    }
  }
  return out;
}

function enhanceStrip(strip: Float32Array, stations: number, depth: number): Float32Array {
  const alongOffset = convAxis(strip, stations, depth, gaussKernel(0.65, 1), false);
  return convAxis(alongOffset, stations, depth, gaussKernel(1.8, 4), true);
}

function sobelOffset(values: Float32Array, stations: number, depth: number): Float32Array {
  const out = new Float32Array(values.length);
  for (let row = 0; row < stations; row += 1) {
    const base = row * depth;
    for (let col = 0; col < depth; col += 1) {
      const left = values[base + Math.max(0, col - 1)];
      const right = values[base + Math.min(depth - 1, col + 1)];
      out[base + col] = 0.25 * (right - left);
    }
  }
  return out;
}

const STATES: Quad[] = (() => {
  const states: Quad[] = [];
  for (let edge1 = 1; edge1 < OFFSETS.length - 10; edge1 += 1) {
    for (let gap1 = 3; gap1 < 9; gap1 += 1) {
      const edge2 = edge1 + gap1;
      for (let gap2 = 3; gap2 < 9; gap2 += 1) {
        const edge3 = edge2 + gap2;
        for (let gap3 = 3; gap3 < 9; gap3 += 1) {
          const edge4 = edge3 + gap3;
          if (edge4 >= OFFSETS.length - 1) continue;
          const center = 0.5 * (OFFSETS[edge1] + OFFSETS[edge4]);
          if (Math.abs(center) <= 9) states.push([edge1, edge2, edge3, edge4]);
        }
      }
    }
  }
  return states;
})();

function headingMetrics(points: Pt[]): { tortuosity: number; maxTurn: number } {
  if (points.length < 2) return { tortuosity: 1, maxTurn: 0 };
  let arc = 0;
  const units: Pt[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const dx = points[index][0] - points[index - 1][0];
    const dy = points[index][1] - points[index - 1][1];
    const len = Math.hypot(dx, dy) || 1e-6;
    arc += len;
    units.push([dx / len, dy / len]);
  }
  const chord = hypotPts(points[points.length - 1], points[0]) || 1e-6;
  let maxTurn = 0;
  for (let index = 1; index < units.length; index += 1) {
    const dot = Math.max(-1, Math.min(1, units[index][0] * units[index - 1][0] + units[index][1] * units[index - 1][1]));
    maxTurn = Math.max(maxTurn, (Math.acos(dot) * 180) / Math.PI);
  }
  return { tortuosity: arc / chord, maxTurn };
}

export function usableLumenCenter(
  lumen: Pt[],
  width: number,
  height: number,
): { center: Pt | null; source: DirectionalTrack['cavitySideSource'] } {
  const center = centroidPts(lumen);
  if (!center || lumen.length < 3) return { center: null, source: 'heuristic' };
  const xs = lumen.map((point) => point[0]);
  const ys = lumen.map((point) => point[1]);
  const area = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
  if (lumen.length <= 6 && area > 0.35 * width * height) {
    return { center: null, source: 'unusable_image_window' };
  }
  return { center, source: 'lumen_center' };
}

export function wallStationsAndNormals(
  heading: Pt[],
  lumen: Pt | null,
  lesion: Pt[],
): { stations: Pt[]; normals: Pt[] } {
  const dense = densifySmooth(heading, false, 80, 400);
  const pts = resamplePoly(dense, Math.max(12, Math.round(polyLength(dense, false) / STATION_STEP)), false);
  if (pts.length < 2) return { stations: [], normals: [] };
  const stations = pts.length >= 8 ? pts : resamplePoly(heading, 12, false);
  const normals: Pt[] = stations.map((_, index) => {
    const prev = stations[Math.max(0, index - 1)];
    const next = stations[Math.min(stations.length - 1, index + 1)];
    let tx = next[0] - prev[0];
    let ty = next[1] - prev[1];
    const len = Math.hypot(tx, ty) || 1;
    tx /= len;
    ty /= len;
    return [-ty, tx] as Pt;
  });
  const lesionCenter = centroidPts(lesion);
  let deepest: Pt | null = null;
  if (lesionCenter && lesion.length) {
    deepest = lesion.reduce((best, point) => (
      hypotPts(point, lesionCenter) >= hypotPts(best, lesionCenter) ? point : best
    ), lesion[0]);
  }
  const hint: Pt[] = stations.map((point) => {
    if (lumen) return [point[0] - lumen[0], point[1] - lumen[1]];
    if (deepest && lesionCenter) return [deepest[0] - lesionCenter[0], deepest[1] - lesionCenter[1]];
    if (lesionCenter) return [point[0] - lesionCenter[0], point[1] - lesionCenter[1]];
    return [0, 1];
  });
  const votes = normals.filter((normal, index) => normal[0] * hint[index][0] + normal[1] * hint[index][1] < 0).length;
  if (votes > normals.length * 0.5) {
    normals.forEach((normal) => {
      normal[0] *= -1;
      normal[1] *= -1;
    });
  }
  if (!lumen) {
    const meanY = normals.reduce((sum, normal) => sum + normal[1], 0) / normals.length;
    if (meanY < 0) {
      normals.forEach((normal) => {
        normal[0] *= -1;
        normal[1] *= -1;
      });
    }
  }
  return { stations, normals };
}

function stationInside(stations: Pt[], lesion: Pt[], gapPx = 7): boolean[] {
  return stations.map((point) => nearLesion(point, lesion, gapPx));
}

function offsetIndex(offset: number): number {
  let best = 0;
  let bestAbs = Infinity;
  OFFSETS.forEach((value, index) => {
    const dist = Math.abs(value - offset);
    if (dist < bestAbs) {
      bestAbs = dist;
      best = index;
    }
  });
  return best;
}

function enforceOrder(row: Quad): Quad {
  const next: Quad = [...row];
  for (let boundary = 1; boundary < 4; boundary += 1) {
    next[boundary] = Math.max(next[boundary - 1] + 2, Math.min(next[boundary - 1] + 10, next[boundary]));
  }
  return next;
}

function selectPhase(enhanced: Float32Array, stations: number, depth: number, phaseLock?: 1 | -1): { phase: 1 | -1; prior: Quad } {
  const profile = new Float32Array(depth);
  for (let col = 0; col < depth; col += 1) {
    const column: number[] = [];
    for (let row = 0; row < stations; row += 1) column.push(enhanced[row * depth + col]);
    profile[col] = median(column);
  }
  const grad = sobelOffset(profile, 1, depth);
  const phases: Array<1 | -1> = phaseLock === 1 || phaseLock === -1 ? [phaseLock] : [1, -1];
  let best = { score: -Infinity, phase: 1 as 1 | -1, prior: STATES[0] };
  phases.forEach((phase) => {
    const signed = [phase, -phase, phase, -phase];
    STATES.forEach((state) => {
      let score = 0;
      state.forEach((edge, boundary) => {
        score += grad[edge] * signed[boundary];
      });
      score -= 0.10 * Math.abs((OFFSETS[state[0]] + OFFSETS[state[3]]) * 0.5);
      if (score > best.score) best = { score, phase, prior: state };
    });
  });
  return { phase: best.phase, prior: best.prior };
}

function trackInterfaces(
  enhanced: Float32Array,
  valid: boolean[],
  stations: number,
  depth: number,
  phaseLock?: 1 | -1,
): {
  offsets: number[][];
  confidence: number[];
  phase: 1 | -1;
  gradient: Float32Array;
  signed: Quad;
} {
  const { phase, prior } = selectPhase(enhanced, stations, depth, phaseLock);
  const signed: Quad = [phase, -phase, phase, -phase];
  const states = STATES.filter((state) => state.every((edge, boundary) => Math.abs(edge - prior[boundary]) <= 5));
  const pool = states.length ? states : STATES;
  const topK = Math.min(TOP_K, pool.length);
  const gradient = sobelOffset(enhanced, stations, depth);
  const selected: number[][] = [];
  const unary: number[][] = [];
  const strengths: number[][] = [];

  for (let station = 0; station < stations; station += 1) {
    const scores: number[] = [];
    const strength: number[] = [];
    for (let index = 0; index < pool.length; index += 1) {
      const state = pool[index];
      const responses = state.map((edge, boundary) => gradient[station * depth + edge] * signed[boundary]);
      const weak = Math.min(...responses);
      let score = responses.reduce((sum, value) => sum + value, 0) + 1.8 * weak;
      score -= 0.35 * state.reduce((sum, edge, boundary) => sum + Math.abs(edge - prior[boundary]), 0);
      if (!state.every((edge) => valid[station * depth + edge])) score = -1e6;
      scores.push(score);
      strength.push(weak);
    }
    const order = scores.map((_, index) => index).sort((left, right) => scores[right] - scores[left]).slice(0, topK);
    selected.push(order);
    unary.push(order.map((index) => -scores[index]));
    strengths.push(order.map((index) => strength[index]));
  }

  const costs: number[][] = [];
  const backs: number[][] = [];
  selected.forEach((keep, station) => {
    if (station === 0) {
      costs.push(unary[station]);
      backs.push(keep.map(() => -1));
      return;
    }
    const prev = selected[station - 1];
    const nextCosts: number[] = [];
    const nextBacks: number[] = [];
    keep.forEach((curIdx, curPos) => {
      const current = pool[curIdx];
      let bestCost = Infinity;
      let bestPrev = 0;
      prev.forEach((prevIdx, prevPos) => {
        const previous = pool[prevIdx];
        let deltaSum = 0;
        let deltaMax = 0;
        for (let boundary = 0; boundary < 4; boundary += 1) {
          const delta = Math.abs(previous[boundary] - current[boundary]);
          deltaSum += delta;
          deltaMax = Math.max(deltaMax, delta);
        }
        let cost = costs[station - 1][prevPos] + 3.5 * deltaSum;
        if (deltaMax > 2) cost += 1e5;
        if (station >= 2) {
          const pred = Math.max(0, Math.min(selected[station - 2].length - 1, backs[station - 1][prevPos]));
          const prevPrev = pool[selected[station - 2][pred]];
          let second = 0;
          for (let boundary = 0; boundary < 4; boundary += 1) {
            second += Math.abs(current[boundary] - 2 * previous[boundary] + prevPrev[boundary]);
          }
          cost += 0.85 * second;
        }
        if (cost < bestCost) {
          bestCost = cost;
          bestPrev = prevPos;
        }
      });
      nextCosts.push(unary[station][curPos] + bestCost);
      nextBacks.push(bestPrev);
    });
    costs.push(nextCosts);
    backs.push(nextBacks);
  });

  let cursor = 0;
  costs[costs.length - 1].forEach((cost, index) => {
    if (cost < costs[costs.length - 1][cursor]) cursor = index;
  });
  const chosen: Quad[] = [];
  const confidence: number[] = [];
  for (let station = stations - 1; station >= 0; station -= 1) {
    const state = pool[selected[station][cursor]];
    chosen.push(state);
    confidence.push(strengths[station][cursor]);
    if (station) cursor = backs[station][cursor];
  }
  chosen.reverse();
  confidence.reverse();
  return {
    offsets: chosen.map((state) => state.map((edge) => OFFSETS[edge])),
    confidence,
    phase,
    gradient,
    signed,
  };
}

function snapOffsets(offsets: number[][], gradient: Float32Array, signed: Quad, depth: number): number[][] {
  return offsets.map((row, station) => {
    const candidate: Quad = [row[0], row[1], row[2], row[3]];
    for (let boundary = 0; boundary < 4; boundary += 1) {
      const center = offsetIndex(row[boundary]);
      const lo = Math.max(1, center - 2);
      const hi = Math.min(depth - 1, center + 3);
      let best = center;
      let bestVal = -Infinity;
      for (let index = lo; index < hi; index += 1) {
        const value = gradient[station * depth + index] * signed[boundary];
        if (value > bestVal) {
          bestVal = value;
          best = index;
        }
      }
      candidate[boundary] = OFFSETS[best];
    }
    const ordered = enforceOrder(candidate);
    const spacing = [ordered[1] - ordered[0], ordered[2] - ordered[1], ordered[3] - ordered[2]];
    if (spacing.some((gap) => gap < 2 - 1e-3 || gap > 10 + 1e-3)) return row;
    if (Math.abs((ordered[0] + ordered[1] + ordered[2] + ordered[3]) / 4) > 9) return row;
    return ordered;
  });
}

function smoothOffsets(offsets: number[][]): number[][] {
  const kernel = [1, 4, 6, 4, 1].map((value) => value / 16);
  return offsets.map((row, station) => {
    const next: Quad = [0, 0, 0, 0];
    for (let boundary = 0; boundary < 4; boundary += 1) {
      let acc = 0;
      for (let tap = -2; tap <= 2; tap += 1) {
        const src = offsets[Math.max(0, Math.min(offsets.length - 1, station + tap))][boundary];
        acc += src * kernel[tap + 2];
      }
      next[boundary] = Math.max(row[boundary] - 1, Math.min(row[boundary] + 1, acc));
    }
    return enforceOrder(next);
  });
}

function extrapolateOffsets(seed: number[][], count: number): number[][] {
  if (count <= 0) return [];
  const last = seed[seed.length - 1].slice() as Quad;
  const slope: Quad = seed.length >= 2
    ? last.map((value, index) => Math.max(-0.8, Math.min(0.8, value - seed[seed.length - 2][index]))) as Quad
    : [0, 0, 0, 0];
  const out: number[][] = [];
  let current = last.slice() as Quad;
  let grow = slope.slice() as Quad;
  for (let step = 0; step < count; step += 1) {
    current = current.map((value, index) => value + grow[index]) as Quad;
    current = enforceOrder(current);
    const mean = (current[0] + current[1] + current[2] + current[3]) / 4;
    if (Math.abs(mean) > 9) {
      const shift = Math.sign(mean) * (Math.abs(mean) - 9);
      current = current.map((value) => value - shift) as Quad;
      current = enforceOrder(current);
    }
    out.push(current.slice());
    grow = grow.map((value) => value * 0.9) as Quad;
  }
  return out;
}

function trackWithLesion(
  enhanced: Float32Array,
  valid: boolean[],
  inside: boolean[],
  stations: number,
  depth: number,
): ReturnType<typeof trackInterfaces> & { extrapolated: boolean[] } {
  const outside = inside.filter((flag) => !flag).length;
  if (!inside.some(Boolean) || inside.every(Boolean) || outside < 6) {
    return { ...trackInterfaces(enhanced, valid, stations, depth), extrapolated: inside.map(() => false) };
  }
  const span = runs(inside).sort((left, right) => (right[1] - right[0]) - (left[1] - left[0]))[0];
  const start = span[0];
  const stop = span[1];
  const midCount = stop - start + 1;
  const sliceBlock = (from: number, to: number) => {
    const count = to - from;
    const next = new Float32Array(count * depth);
    const nextValid: boolean[] = [];
    for (let row = from; row < to; row += 1) {
      for (let col = 0; col < depth; col += 1) {
        next[(row - from) * depth + col] = enhanced[row * depth + col];
        nextValid.push(valid[row * depth + col]);
      }
    }
    return { enhanced: next, valid: nextValid, count };
  };
  const left = start >= 6 ? sliceBlock(0, start) : null;
  const right = stations - stop - 1 >= 6 ? sliceBlock(stop + 1, stations) : null;
  const leftTrack = left ? trackInterfaces(left.enhanced, left.valid, left.count, depth) : null;
  const rightTrack = right
    ? trackInterfaces(right.enhanced, right.valid, right.count, depth, leftTrack?.phase)
    : null;
  if (!leftTrack && !rightTrack) {
    return { ...trackInterfaces(enhanced, valid, stations, depth), extrapolated: inside.map(() => false) };
  }
  const pick = leftTrack && rightTrack
    ? (median(leftTrack.confidence) >= median(rightTrack.confidence) ? leftTrack : rightTrack)
    : (leftTrack || rightTrack)!;
  const offsets = Array.from({ length: stations }, () => [0, 0, 0, 0]);
  const confidence = Array.from({ length: stations }, () => 0);
  const extrapolated = Array.from({ length: stations }, () => false);
  if (leftTrack) {
    leftTrack.offsets.forEach((row, index) => {
      offsets[index] = row;
      confidence[index] = leftTrack.confidence[index];
    });
  }
  if (rightTrack) {
    rightTrack.offsets.forEach((row, index) => {
      offsets[stop + 1 + index] = row;
      confidence[stop + 1 + index] = rightTrack.confidence[index];
    });
  }
  let mid: number[][] = [];
  let seedConf = 1;
  if (leftTrack && rightTrack) {
    const leftExt = extrapolateOffsets(leftTrack.offsets, midCount);
    const rightExt = extrapolateOffsets([...rightTrack.offsets].reverse(), midCount).reverse();
    mid = leftExt.map((row, index) => enforceOrder(row.map((value, boundary) => {
      const t = midCount <= 1 ? 0 : index / (midCount - 1);
      return value * (1 - t) + rightExt[index][boundary] * t;
    }) as Quad));
    seedConf = Math.min(median(leftTrack.confidence), median(rightTrack.confidence));
  } else if (leftTrack) {
    mid = extrapolateOffsets(leftTrack.offsets, midCount);
    seedConf = median(leftTrack.confidence);
  } else if (rightTrack) {
    mid = extrapolateOffsets([...rightTrack.offsets].reverse(), midCount).reverse();
    seedConf = median(rightTrack.confidence);
  }
  mid.forEach((row, index) => {
    offsets[start + index] = row;
    confidence[start + index] = 0.25 * seedConf;
    extrapolated[start + index] = true;
  });
  return {
    offsets,
    confidence,
    phase: pick.phase,
    gradient: sobelOffset(enhanced, stations, depth),
    signed: [pick.phase, -pick.phase, pick.phase, -pick.phase],
    extrapolated,
  };
}

function fateFromRatio(status: 'continuous' | 'suspected_interrupt' | 'cannot_judge'): LayerFate['verdict'] {
  return status;
}

function statusFromVerdict(verdict: LayerFate['verdict']): LayerStatus {
  if (verdict === 'continuous') return 'present';
  if (verdict === 'suspected_interrupt') return 'thinned';
  return 'unseen';
}

export function trackDirectionalInterfaces(input: {
  gray: ArrayLike<number>;
  width: number;
  height: number;
  stroke: number[][];
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  brushRadius?: number | null;
}): DirectionalTrack {
  const heading = densifySmooth(input.stroke, false, 80, 400);
  if (heading.length < 8 || input.width < 16 || input.height < 16) return EMPTY;
  const lesion = densifySmooth(input.lesion || [], true, 160, 800);
  const lumenPts = (input.lumen || []).filter((point) => point.length >= 2) as Pt[];
  const lumenInfo = usableLumenCenter(lumenPts, input.width, input.height);
  let { stations, normals } = wallStationsAndNormals(heading, lumenInfo.center, lesion);
  let headingSource: DirectionalTrack['headingSource'] = 'stored heading';
  const metrics = headingMetrics(stations);
  if (metrics.tortuosity > 2.5 || metrics.maxTurn > 60) {
    const keep = stations.filter((point) => !nearLesion(point, lesion, 15));
    if (keep.length >= 8) {
      const rebuilt = wallStationsAndNormals(keep, lumenInfo.center, lesion);
      stations = rebuilt.stations;
      normals = rebuilt.normals;
      headingSource = 'outside-lesion heading fallback';
    }
  }
  if (stations.length < 8) return EMPTY;

  const depth = OFFSETS.length;
  const strip = new Float32Array(stations.length * depth);
  const valid: boolean[] = [];
  stations.forEach((station, row) => {
    const normal = normals[row];
    OFFSETS.forEach((offset, col) => {
      const x = station[0] + normal[0] * offset;
      const y = station[1] + normal[1] * offset;
      const inside = x >= 0 && y >= 0 && x <= input.width - 1 && y <= input.height - 1;
      strip[row * depth + col] = inside
        ? sampleBilinear(input.gray, input.width, input.height, x, y)
        : 0;
      valid.push(inside && strip[row * depth + col] > 0);
    });
  });
  const enhanced = enhanceStrip(strip, stations.length, depth);
  const inside = stationInside(stations, lesion, 7);
  const tracked = trackWithLesion(enhanced, valid, inside, stations.length, depth);
  const snapped = snapOffsets(tracked.offsets, tracked.gradient, tracked.signed, depth);
  const smoothed = smoothOffsets(snapped);
  const paths: Pt[][] = [[], [], [], []];
  smoothed.forEach((row, index) => {
    row.forEach((offset, boundary) => {
      paths[boundary].push([
        stations[index][0] + normals[index][0] * offset,
        stations[index][1] + normals[index][1] * offset,
      ]);
    });
  });

  const conf = rollingMedian(tracked.confidence, 3);
  const positive = conf.filter((value) => value > 0);
  const threshold = positive.length
    ? Math.max(3, Math.min(8, percentile(positive, 0.35) * 0.55))
    : 4;
  const reliable = conf.map((value, index) => value >= threshold && !inside[index] && !tracked.extrapolated[index]);
  const dashed = stations.map((_, index) => inside[index] || tracked.extrapolated[index] || !reliable[index]);

  const layers: TracedLayer[] = paths.map((curve, index) => {
    const name = WALL_LAYER_NAMES.find((item) => item.layer === INTERFACE_IDS[index]) || WALL_LAYER_NAMES[index];
    const vanish = dashed.findIndex(Boolean);
    return {
      layer: INTERFACE_IDS[index],
      nameZh: name.zh,
      nameEn: name.en,
      curve,
      imaginaryMask: dashed,
      status: vanish >= 0 && vanish < curve.length * 0.85 ? 'thinned' : 'present',
      vanishIndex: vanish >= 0 ? vanish : null,
      offsetPx: Number((smoothed.reduce((sum, row) => sum + row[index], 0) / smoothed.length).toFixed(2)),
    };
  });

  const anatomic = [
    { id: 'mucosa' as const, zh: '黏膜', en: 'Mucosa', layer: layers[0] },
    { id: 'muscularis' as const, zh: '固有肌', en: 'Muscularis', layer: layers[2] },
    { id: 'serosa' as const, zh: '浆膜', en: 'Serosa', layer: layers[3] },
  ];
  const reliableFrac = reliable.filter(Boolean).length / Math.max(1, reliable.length);
  const contactUnseen = lesion.length >= 3 && reliableFrac < 0.35;
  const fates: LayerFate[] = anatomic.map((item) => {
    const verdict: LayerFate['verdict'] = contactUnseen
      ? 'cannot_judge'
      : reliableFrac >= 0.5
        ? 'continuous'
        : 'cannot_judge';
    const label = verdict === 'continuous'
      ? { zh: '连续', en: 'intact' }
      : { zh: '无法判断', en: 'unclear' };
    return {
      id: item.id,
      nameZh: item.zh,
      nameEn: item.en,
      verdict: fateFromRatio(verdict),
      labelZh: label.zh,
      labelEn: label.en,
    };
  });
  const byId = new Map(layers.map((layer) => [layer.layer, layer]));
  const ticks: WallLayerTickDraft[] = WALL_LAYER_NAMES.map((name) => {
    const hit = byId.get(name.layer);
    const status = hit ? statusFromVerdict(fates.find((fate) => (
      (fate.id === 'mucosa' && name.layer === 1)
      || (fate.id === 'muscularis' && name.layer === 4)
      || (fate.id === 'serosa' && name.layer === 5)
    ))?.verdict || 'cannot_judge') : 'unseen';
    return {
      layer: name.layer,
      nameZh: name.zh,
      nameEn: name.en,
      status,
      labelZh: status === 'present' ? '连续' : status === 'thinned' ? '变薄/虚线' : '无法判断',
      labelEn: status === 'present' ? 'intact' : status === 'thinned' ? 'dashed' : 'cannot judge',
    };
  });

  const pattern = tracked.phase > 0 ? 'bright-dark-bright' : 'dark-bright-dark';
  return {
    available: true,
    paintedLayers: 4,
    layers,
    ticks,
    wall: stations,
    extensionMask: dashed,
    remainPx: null,
    overshootPx: null,
    thicknessPx: Number((input.brushRadius || 8) * 2),
    layersBreached: 0,
    deepestZh: '未评估',
    deepestEn: 'Not assessed',
    extraserosal: false,
    mucosaBreached: false,
    noteZh: `四界面联合追踪（${pattern}）。灶内虚线是外推，不是绕病灶一圈。单帧不定 cT。`,
    noteEn: `Four-interface joint track (${pattern}). Dashes inside the lesion are a short continuation, not a loop around the mass. Single-frame draft only; not a cT.`,
    method: 'directional',
    heading: stations,
    headingFlanks: [stations.filter((_, index) => !dashed[index])],
    interfaces: paths,
    phase: tracked.phase,
    cavitySideSource: lumenInfo.source,
    headingSource,
    fates,
  };
}

export function isFourInterfaceSet(bands: number[][][]): boolean {
  if (bands.length !== 4) return false;
  const lengths = bands.map((band) => band.length);
  const min = Math.min(...lengths);
  const max = Math.max(...lengths);
  return min >= 8 && max - min <= Math.max(4, min * 0.25);
}
