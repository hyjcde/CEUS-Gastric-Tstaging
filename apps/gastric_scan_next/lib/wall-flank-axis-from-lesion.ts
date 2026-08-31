/**
 * Search short normal-wall headings around a lesion-derived axis.
 * The lesion mask excludes the tumour from scoring. This is only a local
 * coordinate-axis proposal for ordered layer tracking, not a staging result.
 */

import { headingFlankRuns, interfaceScores, nearLesion, pickInterfaces } from './wall-ordered-track';
import { provisionalHeadingFromLesion } from './wall-propose-from-lesion';
import { cleanPts, polyLength, type Pt } from './wall-polyline';

export type FlankAxis = {
  side: 'left' | 'right';
  heading: Pt[];
  score: number;
  validStations: number;
  source: 'layer_search' | 'geometric_fallback';
};

const MIN_FLANK_PX = 12;
const SEARCH_OFFSETS = [-18, -12, -6, 0, 6, 12, 18];

function normalOfLine(line: Pt[]): Pt {
  const a = line[0] || [0, 0];
  const b = line[line.length - 1] || [1, 0];
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = Math.hypot(dx, dy) || 1;
  return [-dy / length, dx / length];
}

function translate(line: Pt[], normal: Pt, offset: number): Pt[] {
  return line.map((point) => [point[0] + normal[0] * offset, point[1] + normal[1] * offset]);
}

function sampleProfile(
  gray: ArrayLike<number>,
  width: number,
  height: number,
  point: Pt,
  normal: Pt,
): number[] {
  const out: number[] = [];
  for (let offset = -18; offset <= 18; offset += 1) {
    const x = Math.round(point[0] + normal[0] * offset);
    const y = Math.round(point[1] + normal[1] * offset);
    out.push(x >= 0 && y >= 0 && x < width && y < height ? Number(gray[y * width + x]) : 0);
  }
  return out;
}

function scoreRun(
  run: Pt[],
  normal: Pt,
  gray: ArrayLike<number>,
  width: number,
  height: number,
  lesion: Pt[],
): { score: number; validStations: number } {
  if (run.length < 4 || polyLength(run) < MIN_FLANK_PX) return { score: 0, validStations: 0 };
  let score = 0;
  let validStations = 0;
  const stride = Math.max(1, Math.floor(run.length / 16));
  for (let index = 0; index < run.length; index += stride) {
    const point = run[index];
    if (nearLesion(point, lesion, 12)) continue;
    const profile = sampleProfile(gray, width, height, point, normal);
    const picked = pickInterfaces(profile);
    if (picked.b1 == null || picked.b2 == null || picked.b2 - picked.b1 < 3) continue;
    const edges = interfaceScores(profile);
    const b1 = Math.min(edges.inner.length - 1, Math.max(0, picked.b1));
    const b2 = Math.min(edges.outer.length - 1, Math.max(0, picked.b2));
    score += Math.max(0, edges.inner[b1] || 0) + Math.max(0, edges.outer[b2] || 0);
    validStations += 1;
  }
  return { score: validStations ? score / validStations : 0, validStations };
}

function splitSides(line: Pt[], lesion: Pt[]): Array<{ side: 'left' | 'right'; run: Pt[] }> {
  const runs = headingFlankRuns(line, lesion, 12)
    .filter((run) => run.length >= 4 && polyLength(run) >= MIN_FLANK_PX);
  if (runs.length < 2) return [];
  const centerX = lesion.reduce((sum, point) => sum + point[0], 0) / lesion.length;
  return runs
    .map((run) => ({
      side: (run.reduce((sum, point) => sum + point[0], 0) / run.length) <= centerX ? 'left' as const : 'right' as const,
      run,
    }))
    .filter((item, index, all) => all.findIndex((other) => other.side === item.side) === index);
}

/**
 * Propose one independently scored heading for each lesion flank.
 * A zero-score axis is retained only as an explicitly labeled geometric
 * fallback so the caller can request doctor-painted short lines instead.
 */
export function searchFlankAxesFromLesion(input: {
  gray: ArrayLike<number>;
  width: number;
  height: number;
  lesion?: number[][] | null;
  lumen?: number[][] | null;
}): FlankAxis[] {
  const lesion = cleanPts(input.lesion);
  if (lesion.length < 3 || input.width < 32 || input.height < 32) return [];
  const base = provisionalHeadingFromLesion(lesion, { width: input.width, height: input.height }, input.lumen);
  if (base.length < 8) return [];
  const normal = normalOfLine(base);
  const best = new Map<'left' | 'right', FlankAxis>();
  for (const offset of SEARCH_OFFSETS) {
    const candidate = translate(base, normal, offset);
    for (const item of splitSides(candidate, lesion)) {
      const scored = scoreRun(item.run, normal, input.gray, input.width, input.height, lesion);
      const next: FlankAxis = {
        side: item.side,
        heading: item.run,
        score: Number(scored.score.toFixed(2)),
        validStations: scored.validStations,
        source: scored.validStations >= 4 ? 'layer_search' : 'geometric_fallback',
      };
      const previous = best.get(item.side);
      if (!previous || next.score > previous.score) best.set(item.side, next);
    }
  }
  return ['left', 'right']
    .map((side) => best.get(side as 'left' | 'right'))
    .filter((axis): axis is FlankAxis => Boolean(axis));
}
