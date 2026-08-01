import type { MaskBoundaryOverride } from '@/types';

export function bboxFromPolygon(points: number[][]): MaskBoundaryOverride['roi_bbox'] | undefined {
  if (!points || points.length < 3) return undefined;
  let x1 = Infinity;
  let y1 = Infinity;
  let x2 = -Infinity;
  let y2 = -Infinity;
  for (const pt of points) {
    const x = Number(pt[0]);
    const y = Number(pt[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    x1 = Math.min(x1, x);
    y1 = Math.min(y1, y);
    x2 = Math.max(x2, x);
    y2 = Math.max(y2, y);
  }
  if (!Number.isFinite(x1) || x2 <= x1 || y2 <= y1) return undefined;
  return {
    x1: Math.floor(x1),
    y1: Math.floor(y1),
    x2: Math.ceil(x2),
    y2: Math.ceil(y2),
  };
}

export function isValidMaskOverride(value: unknown): value is MaskBoundaryOverride {
  if (!value || typeof value !== 'object') return false;
  const v = value as MaskBoundaryOverride;
  if (typeof v.patientId !== 'string' || !v.patientId) return false;
  if (!Array.isArray(v.mask_polygon) || v.mask_polygon.length < 3) return false;
  if (typeof v.imageWidth !== 'number' || typeof v.imageHeight !== 'number') return false;
  if (v.imageWidth <= 0 || v.imageHeight <= 0) return false;
  const validPolygon = (polygon: unknown) => Array.isArray(polygon)
    && polygon.length >= 3
    && polygon.every(
      (pt) => Array.isArray(pt) && pt.length >= 2
        && Number.isFinite(Number(pt[0])) && Number.isFinite(Number(pt[1])),
    );
  if (!validPolygon(v.mask_polygon)) return false;
  if (v.video_frames !== undefined) {
    if (!Array.isArray(v.video_frames)) return false;
    if (!v.video_frames.every((frame) => (
      frame
      && Number.isFinite(Number(frame.timestamp_sec))
      && Number(frame.imageWidth) > 0
      && Number(frame.imageHeight) > 0
      && validPolygon(frame.mask_polygon)
    ))) return false;
  }
  return true;
}

/** Payload fragment attached to /api/agent/analyze. */
export function maskOverrideToAnalyzePayload(override: MaskBoundaryOverride | null | undefined) {
  if (!override || !isValidMaskOverride(override)) return {};
  return {
    mask_override: {
      mask_polygon: override.mask_polygon,
      wall_polygon: override.wall_polygon,
      roi_bbox: override.roi_bbox || bboxFromPolygon(override.mask_polygon),
      image_width: override.imageWidth,
      image_height: override.imageHeight,
      source: override.source || 'manual',
      video_time_sec: override.video_time_sec,
      video_url: override.video_url,
      video_frames: override.video_frames,
    },
    roi_mode: override.roi_mode || 'predicted',
    use_mask_override: true,
  };
}
