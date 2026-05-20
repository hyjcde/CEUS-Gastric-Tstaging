import type { DirectionBatchItem } from '@/lib/direction-annotation/directionAnnotationTypes';

export type LabelMeShape = {
  label?: string;
  points?: number[][];
};

export type ParsedLesionMask = {
  label: string;
  points: number[][];
  centroid: [number, number];
  bbox: [number, number, number, number];
};

const LESION_LABELS = new Set([
  'tumor',
  'lesion',
  '病灶',
  'target',
  'gastric_cancer',
  'gc',
]);

function normalizeLabel(label?: string): string {
  return (label || '').trim().toLowerCase();
}

function isLesionLabel(label?: string): boolean {
  const normalized = normalizeLabel(label);
  if (!normalized) return false;
  if (LESION_LABELS.has(normalized)) return true;
  return normalized.includes('tumor') || normalized.includes('lesion') || normalized.includes('病灶');
}

export function parseLesionMaskFromShapes(shapes?: LabelMeShape[]): ParsedLesionMask | null {
  if (!shapes?.length) return null;

  for (const shape of shapes) {
    if (!isLesionLabel(shape.label)) continue;
    const points = shape.points;
    if (!points || points.length < 3) continue;

    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    return {
      label: shape.label || 'lesion',
      points,
      centroid: [
        Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10,
        Math.round((ys.reduce((a, b) => a + b, 0) / ys.length) * 10) / 10,
      ],
      bbox: [
        Math.floor(Math.min(...xs)),
        Math.floor(Math.min(...ys)),
        Math.ceil(Math.max(...xs)),
        Math.ceil(Math.max(...ys)),
      ],
    };
  }

  return null;
}

export function parseLesionMaskFromLabelMe(data: { shapes?: LabelMeShape[] }): ParsedLesionMask | null {
  return parseLesionMaskFromShapes(data.shapes);
}

export function encodeDatasetPath(relPath: string): string {
  return relPath
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

export function resolveMaskBbox(item: DirectionBatchItem | null): [number, number, number, number] | null {
  if (!item?.mask_bbox || item.mask_bbox.length !== 4) return null;
  const [x0, y0, x1, y1] = item.mask_bbox;
  if (x1 <= x0 || y1 <= y0) return null;
  return item.mask_bbox;
}
