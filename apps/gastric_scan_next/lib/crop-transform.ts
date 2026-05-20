import { AnnotationBbox, AnnotationShape } from '@/lib/image-utils';

export interface CropOffset {
  offsetX: number;
  offsetY: number;
  originalWidth: number;
  originalHeight: number;
  cropWidth: number;
  cropHeight: number;
  matchScore?: number;
}

export function transformBboxToCropSpace(bbox: AnnotationBbox, offset: CropOffset): AnnotationBbox {
  return {
    x1: bbox.x1 - offset.offsetX,
    y1: bbox.y1 - offset.offsetY,
    x2: bbox.x2 - offset.offsetX,
    y2: bbox.y2 - offset.offsetY,
  };
}

export function transformShapesToCropSpace(shapes: AnnotationShape[], offset: CropOffset): AnnotationShape[] {
  return shapes.map((shape) => ({
    ...shape,
    points: shape.points.map(([x, y]) => [x - offset.offsetX, y - offset.offsetY] as [number, number]),
  }));
}

export function clampBboxToCrop(bbox: AnnotationBbox, offset: CropOffset): AnnotationBbox | null {
  const transformed = transformBboxToCropSpace(bbox, offset);
  const x1 = Math.max(0, Math.min(transformed.x1, offset.cropWidth));
  const y1 = Math.max(0, Math.min(transformed.y1, offset.cropHeight));
  const x2 = Math.max(0, Math.min(transformed.x2, offset.cropWidth));
  const y2 = Math.max(0, Math.min(transformed.y2, offset.cropHeight));
  if (x2 - x1 < 2 || y2 - y1 < 2) return null;
  return { x1, y1, x2, y2 };
}
