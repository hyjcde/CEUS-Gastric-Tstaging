/**
 * Longitudinal bright-dark-bright interruption along an expected wall trajectory.
 * The doctor stroke is a spatial prior, not a continuity answer.
 * Soft draft only. Does not unlock definite cT.
 */

import {
  judgeWallLayerBreach,
  WALL_LAYER_NAMES,
  type WallLayerReadout,
  type WallLayerTick,
} from './wall-layer-breach';
import {
  anatomyTargetMeta,
  cycleInterruptVerdict,
  interruptVerdictFromRaw,
  verdictIsInterrupted,
  verdictLabel,
  type InterruptVerdict,
  type SerosaAnchorMode,
  type WallVisibility,
} from './reader/wall-prompt';

export type LayerInterrupt = {
  layer: 1 | 2 | 3 | 4 | 5;
  nameZh: string;
  nameEn: string;
  interrupted: boolean;
  endBright: number;
  midDark: number;
  delta: number;
  suspected?: boolean;
  verdict?: InterruptVerdict;
  doctorOverride?: boolean;
};

const DOCTOR_CLINICAL: Record<1 | 2 | 3, Array<1 | 2 | 3 | 4 | 5>> = {
  1: [5],
  2: [4, 5],
  3: [1, 4, 5],
};

export function doctorClinicalIds(count: 1 | 2 | 3): Array<1 | 2 | 3 | 4 | 5> {
  return DOCTOR_CLINICAL[count];
}

function sample(gray: ArrayLike<number>, width: number, height: number, x: number, y: number): number {
  const xi = Math.round(x);
  const yi = Math.round(y);
  if (xi < 0 || yi < 0 || xi >= width || yi >= height) return -1;
  return Number(gray[yi * width + xi]);
}

function mean(values: number[]): number {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function smooth1d(values: number[], rounds = 3): number[] {
  let current = values.slice();
  for (let round = 0; round < rounds; round += 1) {
    const next = current.slice();
    for (let index = 1; index < current.length - 1; index += 1) {
      next[index] = current[index - 1] * 0.25 + current[index] * 0.5 + current[index + 1] * 0.25;
    }
    current = next;
  }
  return current;
}

export function detectBrightDarkInterrupt(values: number[]): {
  interrupted: boolean;
  suspected: boolean;
  endBright: number;
  midDark: number;
  delta: number;
} {
  if (values.length < 12) {
    return { interrupted: false, suspected: false, endBright: 0, midDark: 0, delta: 0 };
  }
  const smooth = smooth1d(values, 3);
  const n = smooth.length;
  const left = mean(smooth.slice(0, Math.max(2, Math.floor(n * 0.18))));
  const right = mean(smooth.slice(Math.floor(n * 0.82)));
  const mid = mean(smooth.slice(Math.floor(n * 0.3), Math.ceil(n * 0.7)));
  const endBright = Number(Math.min(left, right).toFixed(1));
  const midDark = Number(mid.toFixed(1));
  const delta = Number((endBright - midDark).toFixed(1));
  // Relative bright-dark-bright. TAUS serosa is often below 88/255, so do not
  // require an absolute white. Both ends must be brighter than the middle.
  const drop = Math.max(12, endBright * 0.12);
  const bothEndsBrighter = left > mid + 8 && right > mid + 8;
  const interrupted = values.length >= 8 && bothEndsBrighter && delta >= drop;
  const suspected = !interrupted
    && values.length >= 8
    && bothEndsBrighter
    && delta >= Math.max(8, endBright * 0.07);
  return { interrupted, suspected, endBright, midDark, delta };
}

/** Index of the darkest sample in the same mid-span used by detectBrightDarkInterrupt. */
export function interruptDipIndex(values: number[]): number | null {
  if (values.length < 8) return null;
  const smooth = smooth1d(values, 3);
  const start = Math.floor(smooth.length * 0.3);
  const end = Math.max(start + 1, Math.ceil(smooth.length * 0.7));
  let best = start;
  let bestVal = Infinity;
  for (let index = start; index < end; index += 1) {
    if (smooth[index] < bestVal) {
      bestVal = smooth[index];
      best = index;
    }
  }
  return best;
}

export function sampleCurveGray(
  gray: ArrayLike<number>,
  width: number,
  height: number,
  curve: number[][],
): number[] {
  const values: number[] = [];
  for (const point of curve) {
    const value = sample(gray, width, height, point[0], point[1]);
    if (value >= 0) values.push(value);
  }
  return values;
}

export function interruptAlongCurve(
  gray: ArrayLike<number>,
  width: number,
  height: number,
  curve: number[][],
  layer: 1 | 2 | 3 | 4 | 5,
  meta?: { visibility?: WallVisibility | null; anchorMode?: SerosaAnchorMode | null },
): LayerInterrupt {
  const name = WALL_LAYER_NAMES.find((item) => item.layer === layer) || WALL_LAYER_NAMES[4];
  const raw = detectBrightDarkInterrupt(sampleCurveGray(gray, width, height, curve));
  const verdict = interruptVerdictFromRaw({
    interrupted: raw.interrupted,
    suspected: raw.suspected,
    visibility: meta?.visibility,
    anchorMode: meta?.anchorMode,
  });
  return {
    layer,
    nameZh: name.zh,
    nameEn: name.en,
    ...raw,
    interrupted: verdictIsInterrupted(verdict),
    verdict,
  };
}

export function interruptsForCurves(
  gray: ArrayLike<number>,
  width: number,
  height: number,
  curves: Array<{ layer: 1 | 2 | 3 | 4 | 5; curve: number[][] }>,
  meta?: { visibility?: WallVisibility | null; anchorMode?: SerosaAnchorMode | null },
): LayerInterrupt[] {
  return curves
    .filter((item) => item.curve.length >= 6)
    .map((item) => interruptAlongCurve(gray, width, height, item.curve, item.layer, meta));
}

function tickFromVerdict(verdict: InterruptVerdict | undefined, hasHit: boolean): {
  status: WallLayerTick['status'];
  labelZh: string;
  labelEn: string;
} {
  if (verdict === 'cannot_judge' || (!hasHit && !verdict)) {
    return { status: 'unseen', labelZh: '无法判断', labelEn: 'cannot judge' };
  }
  if (verdict === 'interrupted') {
    return { status: 'absent', labelZh: '中断', labelEn: 'interrupted' };
  }
  if (verdict === 'suspected') {
    return { status: 'thinned', labelZh: '疑似中断', labelEn: 'suspected' };
  }
  if (hasHit) {
    return { status: 'present', labelZh: '连续', labelEn: 'continuous' };
  }
  return { status: 'unseen', labelZh: '未分出', labelEn: 'not seen' };
}

export function ticksFromInterrupts(
  interrupts: LayerInterrupt[],
  targetLayers: 1 | 2 | 3,
): WallLayerTick[] {
  const byId = new Map(interrupts.map((item) => [item.layer, item]));
  return doctorClinicalIds(targetLayers).map((layer) => {
    const name = WALL_LAYER_NAMES.find((item) => item.layer === layer) || WALL_LAYER_NAMES[4];
    const hit = byId.get(layer);
    const labels = tickFromVerdict(hit?.verdict, Boolean(hit));
    return {
      layer,
      nameZh: name.zh,
      nameEn: name.en,
      ...labels,
    };
  });
}

export function toggleDoctorInterrupt(
  interrupts: LayerInterrupt[] | undefined,
  layer: number,
): LayerInterrupt[] {
  return (interrupts || []).map((item) => {
    if (item.layer !== layer) return item;
    const verdict = cycleInterruptVerdict(item.verdict || (item.interrupted ? 'interrupted' : 'continuous'));
    return {
      ...item,
      verdict,
      interrupted: verdictIsInterrupted(verdict),
      suspected: verdict === 'suspected',
      doctorOverride: true,
    };
  });
}

export function mergeDoctorInterruptOverrides(
  computed: LayerInterrupt[],
  previous?: Array<{
    layer: number;
    interrupted?: boolean;
    verdict?: InterruptVerdict;
    doctorOverride?: boolean;
  }> | null,
): LayerInterrupt[] {
  const keep = new Map(
    (previous || [])
      .filter((item) => item.doctorOverride)
      .map((item) => [item.layer, item]),
  );
  return computed.map((item) => {
    const prior = keep.get(item.layer);
    if (!prior) return item;
    const verdict = prior.verdict
      || (prior.interrupted ? 'interrupted' : 'continuous');
    return {
      ...item,
      verdict,
      interrupted: verdictIsInterrupted(verdict),
      suspected: verdict === 'suspected',
      doctorOverride: true,
    };
  });
}

export function applyWallPromptMeta(
  readout: WallLayerReadout,
  meta?: { visibility?: WallVisibility | null; anchorMode?: SerosaAnchorMode | null },
): WallLayerReadout {
  const interrupts = (readout.interrupts || []).map((item) => {
    if (item.doctorOverride) return item;
    const verdict = interruptVerdictFromRaw({
      interrupted: item.interrupted,
      suspected: item.suspected,
      visibility: meta?.visibility,
      anchorMode: meta?.anchorMode,
    });
    return {
      ...item,
      verdict,
      interrupted: verdictIsInterrupted(verdict),
    };
  });
  return {
    ...readout,
    interrupts,
    ticks: ticksFromInterrupts(interrupts, readout.targetLayers || 1),
  };
}

export function attachLayerInterrupts(
  readout: WallLayerReadout,
  gray: ArrayLike<number> | null | undefined,
  width: number | undefined,
  height: number | undefined,
  curves: Array<{ layer: 1 | 2 | 3 | 4 | 5; curve: number[][] }>,
  targetLayers: 1 | 2 | 3,
  meta?: { visibility?: WallVisibility | null; anchorMode?: SerosaAnchorMode | null },
): WallLayerReadout {
  const anatomy = anatomyTargetMeta(targetLayers);
  if (!gray || !width || !height || width < 8 || height < 8 || !curves.length) {
    return {
      ...readout,
      targetLayers,
      ticks: ticksFromInterrupts([], targetLayers),
    };
  }
  const interrupts = mergeDoctorInterruptOverrides(
    interruptsForCurves(gray, width, height, curves, meta),
    readout.interrupts,
  );
  const ticks = ticksFromInterrupts(interrupts, targetLayers);
  const primary = interrupts[0];
  const verdict = primary?.verdict || (primary?.interrupted ? 'interrupted' : 'continuous');
  const labelZh = verdictLabel(verdict, true);
  const labelEn = verdictLabel(verdict, false);
  const fateNoteZh = (readout.fates || []).map((item) => item.labelZh).join('，');
  const fateNoteEn = (readout.fates || []).map((item) => item.labelEn).join(', ');
  const clusterZh = readout.cluster?.available
    ? `走廊像素已按胃壁层次聚类（${readout.cluster.pattern || '浅层 / 固有肌 / 浆膜'}）。`
    : '';
  const clusterEn = readout.cluster?.available
    ? `Corridor pixels clustered into wall layers (${readout.cluster.pattern || 'shallow / MP / serosa'}). `
    : '';
  const noteZh = readout.method === 'ordered'
    ? `${clusterZh}沿走向联合追踪层界。${fateNoteZh || `${anatomy.lineZh}相对亮暗提示${labelZh}`}。单帧草稿，不定 cT。`
    : `${anatomy.lineZh}：沿线相对亮暗提示${labelZh}。线是预期走向，不是医生给出的中断答案。请核对，不定 cT。`;
  const noteEn = readout.method === 'ordered'
    ? `${clusterEn}Joint ordered interfaces along the heading. ${fateNoteEn || `${anatomy.lineEn} suggests ${labelEn}`}. Single-frame draft, not a definite cT.`
    : `${anatomy.lineEn}: relative bright-dark along the span suggests ${labelEn}. The stroke is a trajectory prompt, not a continuity answer. Doctor check only.`;
  return {
    ...readout,
    targetLayers,
    interrupts,
    ticks: readout.method === 'ordered' && readout.ticks?.length ? readout.ticks : ticks,
    paintedLayers: targetLayers,
    noteZh,
    noteEn,
  };
}

/** Re-sample bright-dark-bright on this frame. Drops copied doctor overrides. */
export function recheckWallInterruptDraft(input: {
  wall: number[][];
  gray: ArrayLike<number>;
  width: number;
  height: number;
  targetLayers: 1 | 2 | 3;
  readout?: WallLayerReadout | null;
  bands?: number[][][] | null;
  lesion?: number[][] | null;
  lumen?: number[][] | null;
}): { readout: WallLayerReadout; bands: number[][][] } {
  const kept = (input.bands || []).filter((band) => band.length >= 2);
  const bands = kept;
  const ids = bands.length === 4
    ? [1, 3, 4, 5] as Array<1 | 2 | 3 | 4 | 5>
    : doctorClinicalIds(input.targetLayers);
  const curves = bands.map((curve, index) => ({
    layer: ids[index] || 5,
    curve,
  }));
  const base = input.readout || judgeWallLayerBreach({
    remainPx: null,
    source: 'propagated',
  });
  const clean = {
    ...base,
    interrupts: (base.interrupts || []).map((item) => ({ ...item, doctorOverride: undefined })),
  };
  return {
    readout: attachLayerInterrupts(
      clean,
      input.gray,
      input.width,
      input.height,
      curves,
      input.targetLayers,
    ),
    bands,
  };
}
