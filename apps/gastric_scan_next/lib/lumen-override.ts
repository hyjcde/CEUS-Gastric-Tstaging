import type { LumenOverride } from '@/types';

export type LumenBBox = { x1: number; y1: number; x2: number; y2: number };

export function normalizeLumenBBox(box: LumenBBox): LumenBBox {
  return {
    x1: Math.min(box.x1, box.x2),
    y1: Math.min(box.y1, box.y2),
    x2: Math.max(box.x1, box.x2),
    y2: Math.max(box.y1, box.y2),
  };
}

export function isValidLumenBBox(value: unknown): value is LumenBBox {
  if (!value || typeof value !== 'object') return false;
  const box = value as Record<string, unknown>;
  const x1 = Number(box.x1);
  const y1 = Number(box.y1);
  const x2 = Number(box.x2);
  const y2 = Number(box.y2);
  return Number.isFinite(x1) && Number.isFinite(y1) && Number.isFinite(x2) && Number.isFinite(y2) && x2 > x1 && y2 > y1;
}

export function isValidLumenOverride(value: unknown): value is LumenOverride {
  if (!value || typeof value !== 'object') return false;
  const v = value as LumenOverride;
  if (typeof v.patientId !== 'string' || !v.patientId) return false;
  if (typeof v.imageWidth !== 'number' || typeof v.imageHeight !== 'number') return false;
  if (v.imageWidth <= 0 || v.imageHeight <= 0) return false;
  if (!isValidLumenBBox(v.lumen_bbox)) return false;
  if (v.lumen_polygon !== undefined) {
    if (!Array.isArray(v.lumen_polygon) || v.lumen_polygon.length < 3) return false;
    if (!v.lumen_polygon.every(
      (pt) => Array.isArray(pt) && pt.length >= 2
        && Number.isFinite(Number(pt[0])) && Number.isFinite(Number(pt[1])),
    )) return false;
  }
  return true;
}

/** Payload fragment attached to Agent analyze for doctor-confirmed lumen geometry. */
export function lumenOverrideToAnalyzePayload(override: LumenOverride | null | undefined) {
  if (!override || !isValidLumenOverride(override)) return {};
  return {
    lumen_override: {
      lumen_bbox: normalizeLumenBBox(override.lumen_bbox),
      lumen_polygon: override.lumen_polygon,
      image_width: override.imageWidth,
      image_height: override.imageHeight,
      source: override.source || 'manual',
      lumen_confidence: override.lumen_confidence,
      lumen_mask_type: override.lumen_mask_type,
      detector_backend_id: override.detector_backend_id,
      sam_backend_id: override.sam_backend_id,
      sam_score: override.sam_score,
      video_time_sec: override.video_time_sec,
      video_url: override.video_url,
    },
    use_lumen_override: true,
  };
}
