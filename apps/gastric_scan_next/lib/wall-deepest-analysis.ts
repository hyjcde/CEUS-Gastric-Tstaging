/**
 * Deepest-region analysis on the current frame.
 * Runs only after the doctor selects one deepest window.
 * Uses existing layer trace and narrow-band echo. Draft only; not a cT.
 */

import { clarifyDeepestEcho, type WallEchoClarify } from './wall-echo-clarify';
import { readoutFromTrace, traceWallLayersFromPaint, type WallLayerTrace } from './wall-layer-trace';
import { type ProposedDeepestRegion } from './wall-propose-from-lesion';
import type { WallPaintSegment } from './reader/wall-prompt';
import { cleanPts, polyLength, type Pt } from './wall-polyline';

export type DeepestChannelDraft = {
  source: 'doctor' | 'ai';
  origin: Pt;
  echo: WallEchoClarify | null;
};

export type DualDeepestAnalysis = {
  doctor: DeepestChannelDraft | null;
  ai: DeepestChannelDraft | null;
  primary: WallEchoClarify | null;
  disagree: boolean;
  noteZh: string;
  noteEn: string;
};

function asPt(point: number[] | ProposedDeepestRegion | null | undefined): Pt | null {
  const raw = Array.isArray(point) ? point : point?.center;
  if (!raw || raw.length < 2) return null;
  const x = Number(raw[0]);
  const y = Number(raw[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
}

export function pickFlankStroke(segments: WallPaintSegment[] | null | undefined): number[][] {
  const usable = (segments || [])
    .map((segment) => cleanPts(segment.points))
    .filter((points) => points.length >= 4)
    .sort((left, right) => polyLength(right) - polyLength(left));
  return usable[0] || [];
}

export function traceVisibleFlanks(input: {
  gray: ArrayLike<number>;
  width: number;
  height: number;
  segments?: WallPaintSegment[] | null;
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  brushRadius?: number | null;
  targetLayers?: 1 | 2 | 3 | null;
}): WallLayerTrace | null {
  const segments = (input.segments || []).filter((segment) => cleanPts(segment.points).length >= 4);
  let best: WallLayerTrace | null = null;
  for (const segment of segments.slice(0, 2)) {
    const traced = traceWallLayersFromPaint({
      gray: input.gray,
      width: input.width,
      height: input.height,
      stroke: segment.points,
      brushRadius: input.brushRadius,
      lesion: input.lesion,
      lumen: input.lumen,
      targetLayers: input.targetLayers,
    });
    if (!traced.available) continue;
    if (!best || polyLength(traced.wall) > polyLength(best.wall)) best = traced;
  }
  return best;
}

export function analyzeDeepestChannels(input: {
  gray: ArrayLike<number>;
  width: number;
  height: number;
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  wall?: number[][] | null;
  segments?: WallPaintSegment[] | null;
  brushRadius?: number | null;
  doctorDeepest?: number[] | null;
  aiDeepest?: number[] | ProposedDeepestRegion | null;
}): DualDeepestAnalysis {
  const doctorPt = asPt(input.doctorDeepest);
  if (!doctorPt) {
    return {
      doctor: null,
      ai: null,
      primary: null,
      disagree: false,
      noteZh: '请先选择一处最深浸润区，选完才开始分析。不定 cT。',
      noteEn: 'Select one deepest-invasion region first. Analysis starts after that. Not a definite cT.',
    };
  }
  const wall = (input.wall && input.wall.length >= 3)
    ? input.wall
    : pickFlankStroke(input.segments);
  const doctorEcho = clarifyDeepestEcho({
    gray: input.gray,
    width: input.width,
    height: input.height,
    lesion: input.lesion,
    lumen: input.lumen,
    wall,
    brushRadius: input.brushRadius,
    origin: doctorPt,
  });
  const doctor: DeepestChannelDraft = {
    source: 'doctor',
    origin: doctorPt,
    echo: doctorEcho.available ? doctorEcho : null,
  };
  const primary = doctor.echo;
  return {
    doctor,
    ai: null,
    primary,
    disagree: false,
    noteZh: primary
      ? `最深区回声：${primary.patternZh || '未分出'}。不定 cT。`
      : '最深区已选定，回声还不够。不定 cT。',
    noteEn: primary
      ? `Deepest-region echo: ${primary.patternEn || 'unresolved'}. Not a definite cT.`
      : 'Deepest region selected; echo is not ready. Not a definite cT.',
  };
}

export { readoutFromTrace };
