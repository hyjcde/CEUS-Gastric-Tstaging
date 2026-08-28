/** Crop DINO overlays to the current-frame peri-lesion ROI. Draft only. */

export type DinoRoiBox = { x1: number; y1: number; x2: number; y2: number };

export function clampDinoRoiBox(
  box: DinoRoiBox | null | undefined,
  width: number,
  height: number,
): DinoRoiBox | null {
  if (!box || width < 8 || height < 8) return null;
  const x1 = Math.max(0, Math.min(width - 2, Math.round(Number(box.x1))));
  const y1 = Math.max(0, Math.min(height - 2, Math.round(Number(box.y1))));
  const x2 = Math.max(x1 + 2, Math.min(width, Math.round(Number(box.x2))));
  const y2 = Math.max(y1 + 2, Math.min(height, Math.round(Number(box.y2))));
  if (x2 - x1 < 8 || y2 - y1 < 8) return null;
  return { x1, y1, x2, y2 };
}

export function scaleDinoRoiBox(box: DinoRoiBox | null | undefined, scale: number): DinoRoiBox | null {
  if (!box || !Number.isFinite(scale) || scale <= 0) return box || null;
  return {
    x1: box.x1 * scale,
    y1: box.y1 * scale,
    x2: box.x2 * scale,
    y2: box.y2 * scale,
  };
}

export function cropDataUrlToRoi(
  dataUrl: string | null | undefined,
  box: DinoRoiBox | null | undefined,
): Promise<string | null> {
  if (!dataUrl || !box || typeof document === 'undefined') {
    return Promise.resolve(dataUrl || null);
  }
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      const width = image.naturalWidth || image.width;
      const height = image.naturalHeight || image.height;
      const roi = clampDinoRoiBox(box, width, height);
      if (!roi) {
        resolve(dataUrl);
        return;
      }
      const canvas = document.createElement('canvas');
      canvas.width = roi.x2 - roi.x1;
      canvas.height = roi.y2 - roi.y1;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(dataUrl);
        return;
      }
      ctx.drawImage(
        image,
        roi.x1,
        roi.y1,
        canvas.width,
        canvas.height,
        0,
        0,
        canvas.width,
        canvas.height,
      );
      resolve(canvas.toDataURL('image/png'));
    };
    image.onerror = () => resolve(dataUrl);
    image.src = dataUrl;
  });
}

export async function attachRoiOverlays<T extends {
  feature_overlay_png?: string;
  wall_evidence_overlay_png?: string;
  roi_feature_overlay_png?: string;
  roi_wall_evidence_overlay_png?: string;
}>(layer: T, box: DinoRoiBox | null): Promise<T> {
  if (!box) return layer;
  const [feature, wall] = await Promise.all([
    layer.roi_feature_overlay_png
      ? Promise.resolve(layer.roi_feature_overlay_png)
      : cropDataUrlToRoi(layer.feature_overlay_png, box),
    layer.roi_wall_evidence_overlay_png
      ? Promise.resolve(layer.roi_wall_evidence_overlay_png)
      : cropDataUrlToRoi(layer.wall_evidence_overlay_png, box),
  ]);
  return {
    ...layer,
    roi_feature_overlay_png: feature || layer.feature_overlay_png,
    roi_wall_evidence_overlay_png: wall || layer.wall_evidence_overlay_png,
  };
}
