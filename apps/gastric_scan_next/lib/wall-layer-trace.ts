/**
 * Trace gastric-wall layers from a doctor-painted heading.
 *
 * Public expected lines use the local four-interface joint tracker:
 * unwrap the heading, learn four ordered gray jumps outside the lesion,
 * and dash a short continuation inside. Does not walk a closed lesion loop.
 * Soft draft only. Does not unlock definite cT.
 */

import { trackDirectionalInterfaces } from './wall-directional-interfaces';
import type { LayerFate } from './wall-ordered-track';
import type { WallClusterSummary } from './wall-pixel-cluster';
import type { Pt } from './wall-polyline';
import type { WallLayerReadout } from './wall-layer-breach';

export type LayerStatus = 'present' | 'thinned' | 'absent' | 'imaginary' | 'unseen';

export type TracedLayer = {
  layer: 1 | 2 | 3 | 4 | 5;
  nameZh: string;
  nameEn: string;
  curve: Pt[];
  imaginaryMask: boolean[];
  status: LayerStatus;
  vanishIndex: number | null;
  offsetPx: number;
};

export type WallLayerTickDraft = {
  layer: 1 | 2 | 3 | 4 | 5;
  nameZh: string;
  nameEn: string;
  status: LayerStatus;
  labelZh: string;
  labelEn: string;
};

export type WallLayerTrace = {
  available: boolean;
  paintedLayers: number;
  layers: TracedLayer[];
  ticks: WallLayerTickDraft[];
  wall: Pt[];
  extensionMask: boolean[];
  remainPx: number | null;
  overshootPx: number | null;
  thicknessPx: number;
  layersBreached: 0 | 1 | 2 | 3 | 4 | 5;
  deepestZh: string;
  deepestEn: string;
  extraserosal: boolean;
  mucosaBreached: boolean;
  noteZh: string;
  noteEn: string;
  method?: 'directional' | 'ordered' | 'paint';
  fates?: LayerFate[];
  headingFlanks?: Pt[][];
  cluster?: WallClusterSummary;
};

export function readoutFromTrace(trace: WallLayerTrace): WallLayerReadout {
  return {
    layersBreached: trace.layersBreached,
    deepestZh: trace.deepestZh,
    deepestEn: trace.deepestEn,
    remainPx: trace.remainPx,
    overshootPx: trace.overshootPx,
    thicknessPx: trace.thicknessPx,
    ratio: trace.thicknessPx > 0 && trace.remainPx != null
      ? Number(Math.max(0, (trace.thicknessPx - trace.remainPx) / trace.thicknessPx).toFixed(3))
      : null,
    extraserosal: trace.extraserosal,
    source: 'pixel',
    noteZh: trace.noteZh,
    noteEn: trace.noteEn,
    ticks: trace.ticks,
    paintedLayers: trace.paintedLayers,
    mucosaBreached: trace.mucosaBreached,
    method: trace.method,
    fates: trace.fates,
    cluster: trace.cluster,
  };
}

export function traceWallLayersFromPaint(input: {
  gray: ArrayLike<number>;
  width: number;
  height: number;
  stroke: number[][];
  brushRadius?: number | null;
  lesion?: number[][] | null;
  lumen?: number[][] | null;
  targetLayers?: 1 | 2 | 3 | null;
}): WallLayerTrace {
  return trackDirectionalInterfaces(input);
}
