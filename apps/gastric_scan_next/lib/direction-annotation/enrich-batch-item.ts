import fs from 'fs';
import path from 'path';
import type { DirectionBatchItem } from '@/lib/direction-annotation/directionAnnotationTypes';
import { parseLesionMaskFromLabelMe } from '@/lib/direction-annotation/labelme-utils';

export function enrichBatchItemWithMask(
  projectRoot: string,
  item: DirectionBatchItem,
): DirectionBatchItem {
  if (item.has_mask && item.mask_bbox) return item;
  if (!item.annotation_path) return item;

  const annotationPath = path.join(projectRoot, item.annotation_path);
  if (!fs.existsSync(annotationPath)) return item;

  try {
    const payload = JSON.parse(fs.readFileSync(annotationPath, 'utf-8'));
    const parsed = parseLesionMaskFromLabelMe(payload);
    if (!parsed) return item;

    return {
      ...item,
      has_mask: true,
      mask_centroid: parsed.centroid,
      mask_bbox: parsed.bbox,
    };
  } catch {
    return item;
  }
}
