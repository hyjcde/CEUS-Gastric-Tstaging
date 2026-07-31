export type AnnotationPoint = [number, number];

export interface AnnotationShape {
  label?: string;
  points: AnnotationPoint[];
}

export interface AnnotationBbox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface ImageMetrics {
  displayWidth: number;
  displayHeight: number;
  naturalWidth: number;
  naturalHeight: number;
  offsetLeft?: number;
  offsetTop?: number;
}

export const LABEL_KEYWORDS = ['lesion', 'roi', 'tumor', 'target'];

export const matchesAnnotation = (label?: string) => {
  if (!label) return false;
  const normalized = label.toLowerCase();
  return LABEL_KEYWORDS.some(keyword => normalized.includes(keyword));
};

export const extractAnnotationBbox = (shapes: AnnotationShape[] = []): AnnotationBbox | null => {
  if (!Array.isArray(shapes) || shapes.length === 0) return null;
  
  const filtered = shapes.filter(shape => matchesAnnotation(shape.label));
  const candidates = filtered.length > 0 ? filtered : shapes;
  
  let xMin = Infinity;
  let yMin = Infinity;
  let xMax = -Infinity;
  let yMax = -Infinity;

  candidates.forEach(shape => {
    if (!Array.isArray(shape.points)) return;
    shape.points.forEach(point => {
      const [x, y] = point;
      if (typeof x !== 'number' || typeof y !== 'number') return;
      xMin = Math.min(xMin, x);
      yMin = Math.min(yMin, y);
      xMax = Math.max(xMax, x);
      yMax = Math.max(yMax, y);
    });
  });

  if (xMin === Infinity || yMin === Infinity || xMax === -Infinity || yMax === -Infinity) {
    return null;
  }

  return {
    x1: xMin,
    y1: yMin,
    x2: xMax,
    y2: yMax
  };
};

// Calculate Distance (Pixels -> approx CM)
// Default assumption: 40px ~= 1cm for display purposes
export const calculateDistanceCm = (
  p1: { x: number, y: number }, 
  p2: { x: number, y: number }, 
  pixelsPerCm: number = 40
): string => {
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const distPx = Math.sqrt(dx*dx + dy*dy);
  return (distPx / pixelsPerCm).toFixed(2);
};

export const calculateDetectionOverlayStyle = (
  bbox: AnnotationBbox | null,
  metrics: ImageMetrics | null
): React.CSSProperties | null => {
  if (!bbox || !metrics) return null;

  const normalized = {
    x1: Math.max(0, Math.min(bbox.x1, metrics.naturalWidth)),
    y1: Math.max(0, Math.min(bbox.y1, metrics.naturalHeight)),
    x2: Math.max(0, Math.min(bbox.x2, metrics.naturalWidth)),
    y2: Math.max(0, Math.min(bbox.y2, metrics.naturalHeight))
  };

  const bboxWidth = Math.max(0, normalized.x2 - normalized.x1);
  const bboxHeight = Math.max(0, normalized.y2 - normalized.y1);

  if (bboxWidth === 0 || bboxHeight === 0 || metrics.naturalWidth === 0 || metrics.naturalHeight === 0) {
    return null;
  }

  const width = (bboxWidth / metrics.naturalWidth) * metrics.displayWidth;
  const height = (bboxHeight / metrics.naturalHeight) * metrics.displayHeight;
  let left = (normalized.x1 / metrics.naturalWidth) * metrics.displayWidth;
  let top = (normalized.y1 / metrics.naturalHeight) * metrics.displayHeight;

  // Add offset if available (to handle centered images)
  if (metrics.offsetLeft) left += metrics.offsetLeft;
  if (metrics.offsetTop) top += metrics.offsetTop;

  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`
  };
};

