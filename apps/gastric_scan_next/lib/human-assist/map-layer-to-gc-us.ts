/**
 * Map ContactGeom / LayerBridge results into GC-US derive inputs.
 * Proxy only: never unlock definite cT from wall_proxy / tHint alone.
 */

import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import type { GcUsDeriveInput } from '@/lib/gc-us-report-template';

export type ContourIrregularityFn = (polygon: number[][]) => number | null;

function finiteRatio(value: unknown): number | null {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  if (n < 0) return 0;
  if (n > 1) return n > 1.5 ? Math.min(1, n / 100) : 1;
  return n;
}

/** Soft morphology / growth / boundary from penetration ratio (geometry proxy). */
export function proxyFromPenetration(ratio: number | null): {
  morphology: string | null;
  growth: string | null;
  boundary: string | null;
  serosa: string | null;
} {
  if (ratio == null) {
    return { morphology: null, growth: null, boundary: null, serosa: null };
  }
  if (ratio < 0.25) {
    return {
      morphology: '局限隆起型',
      growth: '膨胀型',
      boundary: '边界清晰、规则',
      serosa: '浆膜连续光滑',
    };
  }
  if (ratio < 0.55) {
    return {
      morphology: '局部浸润型',
      growth: '局部浸润性',
      boundary: '边界部分欠清',
      serosa: '浆膜面欠光整',
    };
  }
  return {
    morphology: '溃疡浸润型',
    growth: '明显浸润性',
    boundary: '边界不规则',
    serosa: '浆膜连续性可疑破坏',
  };
}

export function hasLumenOrientation(input: {
  lumenPrefer?: [number, number] | null;
  lumenPolygon?: number[][] | null;
  lumenBBox?: { x1: number; y1: number; x2: number; y2: number } | null;
  wallPolygon?: number[][] | null;
}): boolean {
  if (input.wallPolygon && input.wallPolygon.length >= 3) return true;
  if (input.lumenPrefer && Number.isFinite(input.lumenPrefer[0]) && Number.isFinite(input.lumenPrefer[1])) {
    return true;
  }
  if (input.lumenPolygon && input.lumenPolygon.length >= 3) return true;
  if (input.lumenBBox) {
    const w = Math.abs(Number(input.lumenBBox.x2) - Number(input.lumenBBox.x1));
    const h = Math.abs(Number(input.lumenBBox.y2) - Number(input.lumenBBox.y1));
    if (w > 1 && h > 1) return true;
  }
  return false;
}

/**
 * Build deriveGcUsSigns input fragments from a live LayerBridge result.
 * Callers still supply clinical and must rebuild via buildGcUsTemplateReport.
 */
export function mapLayerResultToGcUsDerive(
  layerResult: LayerAnalyzeResult | null | undefined,
  opts: {
    lesionPolygon: number[][];
    wallPolygon?: number[][];
    frameSize?: { width: number; height: number } | null;
    lumenOriented?: boolean;
    irregularityFn?: ContourIrregularityFn;
    caseId?: string | null;
    frameId?: string | null;
  },
): Pick<GcUsDeriveInput, 'layer' | 'pixel' | 'evidenceRef'> {
  const irregularity = opts.irregularityFn?.(opts.lesionPolygon) ?? null;
  const inContact = layerResult?.inContact;
  const layer = layerResult?.layer;
  const penRatio = finiteRatio(layerResult?.pen?.ratio)
    ?? finiteRatio(layerResult?.analysis?.ratioHint)
    ?? finiteRatio(layerResult?.geom?.contact_ratio);
  const proxy = proxyFromPenetration(inContact === false ? 0 : penRatio);
  const pixelBased = Boolean(layerResult?.pixelBased && !layerResult?.analysis?.imaginary);
  const layerSource = pixelBased ? 'pixel' : 'live_contour';
  const oriented = Boolean(opts.lumenOriented);
  const confidenceRaw = typeof layer?.confidence === 'number' ? layer.confidence : null;
  const confidence = confidenceRaw != null
    ? Math.max(0.05, Math.min(0.85, confidenceRaw * (oriented ? 1 : 0.75) * (pixelBased ? 1 : 0.85)))
    : (layerResult?.ok ? (oriented ? (pixelBased ? 0.55 : 0.4) : 0.28) : null);

  const evidenceRef = [
    opts.caseId || 'case_unknown',
    opts.frameId || 'frame_unknown',
    opts.frameSize
      ? `frame_size:${opts.frameSize.width}x${opts.frameSize.height}`
      : 'frame_size:unknown',
    opts.wallPolygon && opts.wallPolygon.length >= 3 ? 'wall_polygon' : 'wall_unavailable',
    oriented ? 'lumen_oriented' : 'lumen_orientation_missing',
    layerResult?.ok ? 'layer_bridge_ok' : 'layer_bridge_unavailable',
    pixelBased ? 'layer_pixel' : 'layer_geometry_proxy',
    penRatio != null ? `pen_ratio:${penRatio.toFixed(3)}` : 'pen_ratio:na',
  ];

  return {
    layer: {
      label: inContact === false ? null : (layer?.label ?? null),
      // tHint stays proxy-only; deriveGcUsSigns must not treat it as definite cT.
      tHint: inContact === false ? null : (layer?.tHint ?? null),
      inContact: inContact ?? null,
      confidence,
      source: layer?.label || layer?.tHint ? layerSource : 'not_available',
    },
    pixel: {
      irregularity,
      morphology: proxy.morphology,
      growth: proxy.growth,
      boundary: proxy.boundary,
      serosa: proxy.serosa,
      penetration_ratio: penRatio,
      wall_proxy: true,
      lumen_oriented: oriented,
      layer_pixel_based: pixelBased,
    },
    evidenceRef,
  };
}
