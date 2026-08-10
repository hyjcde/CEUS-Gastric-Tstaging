import type { GcUsReportImage } from '@/lib/gc-us-report-template';
import { computeLesionLumenGeometry } from '@/lib/lesion-lumen-geometry';

export type ReportEvidenceFrameInput = {
  frameDataUrl: string;
  maskPolygon: number[][];
  frameWidth: number;
  frameHeight: number;
  frameTime?: number | null;
  frameIndex?: number | null;
  normalizedMask?: boolean;
  sourceFrameId?: string | null;
  sourceVideoUrl?: string | null;
  label?: string;
};

export type ReportEvidenceImageInput = {
  current: ReportEvidenceFrameInput;
  wallPolygon?: number[][];
  lumenPolygon?: number[][];
  lumenBBox?: { x1: number; y1: number; x2: number; y2: number } | null;
  keyframes?: ReportEvidenceFrameInput[];
};

export type CurvatureMetrics = {
  mean: number;
  maximum: number;
  irregularity: number;
};

function imageDataUrl(value: string, mime = 'image/jpeg'): string {
  if (/^(data:|https?:|blob:|\/)/i.test(value)) return value;
  return `data:${mime};base64,${value}`;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Unable to load report evidence image'));
    image.src = imageDataUrl(src);
  });
}

function finitePoint(point: number[]): point is [number, number] {
  return point.length >= 2 && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]));
}

function cleanPolygon(points: number[][]): [number, number][] {
  return points.filter(finitePoint).map((point) => [Number(point[0]), Number(point[1])]);
}

function bounds(points: [number, number][], width: number, height: number) {
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  return {
    x1: Math.max(0, Math.min(width, Math.min(...xs))),
    y1: Math.max(0, Math.min(height, Math.min(...ys))),
    x2: Math.max(0, Math.min(width, Math.max(...xs))),
    y2: Math.max(0, Math.min(height, Math.max(...ys))),
  };
}

function drawPolygon(
  context: CanvasRenderingContext2D,
  points: [number, number][],
  transform: (point: [number, number]) => [number, number],
  fill: string | null,
  stroke: string,
  lineWidth = 3,
) {
  if (points.length < 3) return;
  context.beginPath();
  points.forEach((point, index) => {
    const [x, y] = transform(point);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.closePath();
  if (fill) {
    context.fillStyle = fill;
    context.fill();
  }
  context.strokeStyle = stroke;
  context.lineWidth = lineWidth;
  context.lineJoin = 'round';
  context.lineCap = 'round';
  context.stroke();
}

function tracePolygon(
  context: CanvasRenderingContext2D,
  points: [number, number][],
  transform: (point: [number, number]) => [number, number],
): boolean {
  if (points.length < 3) return false;
  context.beginPath();
  points.forEach((point, index) => {
    const [x, y] = transform(point);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.closePath();
  return true;
}

function drawOverlapHatch(
  context: CanvasRenderingContext2D,
  lesion: [number, number][],
  lumen: [number, number][],
  lumenBBox: ReportEvidenceImageInput['lumenBBox'],
  transform: (point: [number, number]) => [number, number],
  width: number,
  height: number,
) {
  const hasLumenPath = lumen.length >= 3
    ? tracePolygon(context, lumen, transform)
    : Boolean(lumenBBox);
  if (!hasLumenPath) return;
  if (lumen.length < 3 && lumenBBox) {
    const topLeft = transform([lumenBBox.x1, lumenBBox.y1]);
    const bottomRight = transform([lumenBBox.x2, lumenBBox.y2]);
    context.beginPath();
    context.rect(
      Math.min(topLeft[0], bottomRight[0]),
      Math.min(topLeft[1], bottomRight[1]),
      Math.abs(bottomRight[0] - topLeft[0]),
      Math.abs(bottomRight[1] - topLeft[1]),
    );
  }
  context.save();
  context.clip();
  if (!tracePolygon(context, lesion, transform)) {
    context.restore();
    return;
  }
  context.clip();
  // Soft wash only — no hatch / dashed guides on evidence stills.
  context.fillStyle = 'rgba(251, 191, 36, 0.08)';
  context.fillRect(0, 0, width, height);
  context.restore();
}

function drawContactBreakthroughCue(
  context: CanvasRenderingContext2D,
  lesionPoint: [number, number] | null | undefined,
  lumenPoint: [number, number] | null | undefined,
  transform: (point: [number, number]) => [number, number],
  label = '突破分析关键区（病灶→胃腔壁）',
) {
  if (!lesionPoint || !lumenPoint) return;
  const start = transform(lesionPoint);
  const end = transform(lumenPoint);
  const cx = (start[0] + end[0]) / 2;
  const cy = (start[1] + end[1]) / 2;
  const radius = Math.max(18, Math.min(48, Math.hypot(end[0] - start[0], end[1] - start[1]) * 0.9 + 18));
  const gradient = context.createRadialGradient(cx, cy, 2, cx, cy, radius);
  gradient.addColorStop(0, 'rgba(251, 191, 36, 0.30)');
  gradient.addColorStop(0.55, 'rgba(251, 191, 36, 0.10)');
  gradient.addColorStop(1, 'rgba(251, 191, 36, 0)');
  context.save();
  context.fillStyle = gradient;
  context.beginPath();
  context.arc(cx, cy, radius, 0, Math.PI * 2);
  context.fill();
  context.beginPath();
  context.arc(cx, cy, radius * 0.92, 0, Math.PI * 2);
  context.strokeStyle = 'rgba(253, 224, 71, 0.8)';
  context.lineWidth = 1.6;
  context.setLineDash([5, 4]);
  context.stroke();
  context.setLineDash([]);
  context.beginPath();
  context.moveTo(start[0], start[1]);
  context.lineTo(end[0], end[1]);
  context.strokeStyle = '#fbbf24';
  context.lineWidth = 2;
  context.stroke();
  for (const point of [start, end]) {
    context.beginPath();
    context.arc(point[0], point[1], 4, 0, Math.PI * 2);
    context.fillStyle = '#fbbf24';
    context.fill();
    context.strokeStyle = '#0f172a';
    context.lineWidth = 1;
    context.stroke();
  }
  context.font = '600 12px sans-serif';
  const labelWidth = context.measureText(label).width + 14;
  context.fillStyle = 'rgba(15, 23, 42, 0.72)';
  context.fillRect(cx - labelWidth / 2, cy - radius - 22, labelWidth, 20);
  context.fillStyle = '#fde68a';
  context.fillText(label, cx - labelWidth / 2 + 7, cy - radius - 8);
  context.restore();
}

function drawLabel(
  context: CanvasRenderingContext2D,
  text: string,
  width: number,
  height: number,
) {
  context.fillStyle = 'rgba(2, 6, 23, 0.78)';
  context.fillRect(0, 0, width, 32);
  context.fillStyle = '#f8fafc';
  context.font = '600 16px sans-serif';
  context.fillText(text, 12, 21);
  context.fillStyle = '#94a3b8';
  context.font = '12px sans-serif';
  context.fillText('证据图像来自当前分割轮廓', 12, Math.max(48, height - 12));
}

function fitSize(width: number, height: number, maxWidth = 1200) {
  const scale = Math.min(1, maxWidth / Math.max(1, width));
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
    scale,
  };
}

function toCanvas(
  image: HTMLImageElement,
  width: number,
  height: number,
): { canvas: HTMLCanvasElement; context: CanvasRenderingContext2D; scale: number } | null {
  const size = fitSize(width, height);
  const canvas = document.createElement('canvas');
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(image, 0, 0, size.width, size.height);
  return { canvas, context, scale: size.scale };
}

function curvatureAt(
  points: [number, number][],
  index: number,
): number {
  const count = points.length;
  const previous = points[(index - 1 + count) % count];
  const current = points[index];
  const next = points[(index + 1) % count];
  const a = [previous[0] - current[0], previous[1] - current[1]];
  const b = [next[0] - current[0], next[1] - current[1]];
  const denominator = Math.hypot(...a) * Math.hypot(...b);
  if (!denominator) return 0;
  const cosine = Math.max(-1, Math.min(1, (a[0] * b[0] + a[1] * b[1]) / denominator));
  return Math.PI - Math.acos(cosine);
}

export function computeContourCurvature(pointsInput: number[][]): CurvatureMetrics | null {
  const points = cleanPolygon(pointsInput);
  if (points.length < 3) return null;
  const values = points.map((_, index) => curvatureAt(points, index));
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const maximum = Math.max(...values);
  const perimeter = points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + Math.hypot(next[0] - point[0], next[1] - point[1]);
  }, 0);
  const area = Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0)) / 2;
  const irregularity = area > 0 ? (perimeter * perimeter) / (4 * Math.PI * area) : 0;
  return { mean, maximum, irregularity };
}

async function renderSegmentationImage(
  input: ReportEvidenceFrameInput,
  wallPolygon: number[][] = [],
  lumenPolygon: number[][] = [],
  lumenBBox: ReportEvidenceImageInput['lumenBBox'] = null,
): Promise<GcUsReportImage | null> {
  const image = await loadImage(input.frameDataUrl);
  // Prefer the decoded image size so 1/4 keyframe thumbs stay aligned with overlays.
  const sourceW = Math.max(1, image.naturalWidth || input.frameWidth);
  const sourceH = Math.max(1, image.naturalHeight || input.frameHeight);
  const sx = sourceW / Math.max(1, input.frameWidth);
  const sy = sourceH / Math.max(1, input.frameHeight);
  const rawMask = cleanPolygon(input.maskPolygon);
  const mask = input.normalizedMask
    ? rawMask.map(([x, y]) => [x * sourceW, y * sourceH] as [number, number])
    : rawMask.map(([x, y]) => [x * sx, y * sy] as [number, number]);
  if (mask.length < 3) return null;
  const result = toCanvas(image, sourceW, sourceH);
  if (!result) return null;
  const { canvas, context, scale } = result;
  const transform = ([x, y]: [number, number]): [number, number] => [x * scale, y * scale];
  const scalePoly = (points: number[][]) => cleanPolygon(points).map(([x, y]) => (
    input.normalizedMask
      ? [x * sourceW, y * sourceH] as [number, number]
      : [x * sx, y * sy] as [number, number]
  ));
  const scaledLumenBox = lumenBBox
    ? {
        x1: lumenBBox.x1 * sx,
        y1: lumenBBox.y1 * sy,
        x2: lumenBBox.x2 * sx,
        y2: lumenBBox.y2 * sy,
      }
    : null;
  drawPolygon(context, mask, transform, 'rgba(34, 211, 238, 0.12)', 'rgba(103, 232, 249, 0.70)', 1.5);
  drawPolygon(context, scalePoly(wallPolygon), transform, null, 'rgba(251, 146, 60, 0.65)', 1.35);
  const lumen = scalePoly(lumenPolygon);
  drawPolygon(context, lumen, transform, 'rgba(217, 70, 239, 0.08)', 'rgba(217, 70, 239, 0.60)', 1.35);
  if (scaledLumenBox) {
    context.strokeStyle = 'rgba(217, 70, 239, 0.55)';
    context.setLineDash([]);
    context.lineWidth = 1.25;
    context.strokeRect(
      scaledLumenBox.x1 * scale,
      scaledLumenBox.y1 * scale,
      (scaledLumenBox.x2 - scaledLumenBox.x1) * scale,
      (scaledLumenBox.y2 - scaledLumenBox.y1) * scale,
    );
  }
  const relation = computeLesionLumenGeometry(mask, lumen, scaledLumenBox);
  if (relation.relation === 'overlap' && (lumen.length >= 3 || scaledLumenBox)) {
    drawOverlapHatch(context, mask, lumen, scaledLumenBox, transform, canvas.width, canvas.height);
  }
  // Skip contact rings / connector dashes — evidence still shows lesion + lumen contours only.
  const label = input.frameTime == null
    ? (input.label || '当前关键帧, 病灶分割叠加')
    : `${input.label || '关键帧, 病灶分割叠加'}, t=${input.frameTime.toFixed(3)}s`;
  drawLabel(context, label, canvas.width, canvas.height);
  return {
    id: input.frameIndex == null ? 'segmentation-current' : `keyframe-${input.frameIndex}`,
    label: input.frameIndex == null
      ? '当前关键帧, 病灶分割'
      : `${input.label || `关键帧 ${input.frameIndex + 1}, 病灶分割`}`,
    url: canvas.toDataURL('image/jpeg', 0.88),
    kind: input.frameIndex == null ? 'overlay' : 'keyframe',
    caption: input.frameIndex == null
      ? '当前帧原始超声与实际病灶分割轮廓'
      : `t=${input.frameTime == null ? 'unknown' : input.frameTime.toFixed(3)}s 的实际病灶分割轮廓`,
    selected: true,
    frame_index: input.frameIndex ?? null,
    frame_time: input.frameTime ?? null,
    source_frame_id: input.sourceFrameId ?? null,
    source_video_url: input.sourceVideoUrl ?? null,
    image_width: input.frameWidth,
    image_height: input.frameHeight,
  };
}

async function renderRoiImage(input: ReportEvidenceFrameInput): Promise<GcUsReportImage | null> {
  const mask = cleanPolygon(input.maskPolygon);
  if (mask.length < 3) return null;
  const image = await loadImage(input.frameDataUrl);
  const sourceBounds = bounds(mask, input.frameWidth, input.frameHeight);
  const pad = Math.max(12, Math.round(Math.max(sourceBounds.x2 - sourceBounds.x1, sourceBounds.y2 - sourceBounds.y1) * 0.18));
  const x1 = Math.max(0, sourceBounds.x1 - pad);
  const y1 = Math.max(0, sourceBounds.y1 - pad);
  const x2 = Math.min(input.frameWidth, sourceBounds.x2 + pad);
  const y2 = Math.min(input.frameHeight, sourceBounds.y2 + pad);
  const size = fitSize(x2 - x1, y2 - y1, 900);
  const canvas = document.createElement('canvas');
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(image, x1, y1, x2 - x1, y2 - y1, 0, 0, canvas.width, canvas.height);
  const transform = ([x, y]: [number, number]): [number, number] => [
    (x - x1) * size.scale,
    (y - y1) * size.scale,
  ];
  drawPolygon(context, mask, transform, 'rgba(34, 211, 238, 0.20)', '#22d3ee', 4);
  drawLabel(context, '病灶 ROI, 来自实际分割轮廓', canvas.width, canvas.height);
  return {
    id: 'segmentation-roi',
    label: '病灶 ROI',
    url: canvas.toDataURL('image/jpeg', 0.88),
    kind: 'roi',
    caption: '按当前病灶分割轮廓裁剪的 ROI',
    selected: true,
  };
}

async function renderCurvatureImage(input: ReportEvidenceFrameInput): Promise<GcUsReportImage | null> {
  const mask = cleanPolygon(input.maskPolygon);
  if (mask.length < 3) return null;
  const image = await loadImage(input.frameDataUrl);
  const result = toCanvas(image, input.frameWidth, input.frameHeight);
  if (!result) return null;
  const { canvas, context, scale } = result;
  const values = mask.map((_, index) => curvatureAt(mask, index));
  const maximum = Math.max(...values, 1e-6);
  const transform = ([x, y]: [number, number]): [number, number] => [x * scale, y * scale];
  for (let index = 0; index < mask.length; index += 1) {
    const start = transform(mask[index]);
    const end = transform(mask[(index + 1) % mask.length]);
    const ratio = values[index] / maximum;
    context.strokeStyle = `hsl(${Math.round(210 - ratio * 190)} 90% 55%)`;
    context.lineWidth = 5;
    context.lineCap = 'round';
    context.beginPath();
    context.moveTo(start[0], start[1]);
    context.lineTo(end[0], end[1]);
    context.stroke();
  }
  context.fillStyle = 'rgba(2, 6, 23, 0.78)';
  context.fillRect(0, 0, canvas.width, 52);
  const metrics = computeContourCurvature(mask);
  context.fillStyle = '#f8fafc';
  context.font = '600 16px sans-serif';
  context.fillText('曲率/边界分析, 来自实际分割轮廓', 12, 21);
  context.fillStyle = '#cbd5e1';
  context.font = '12px sans-serif';
  context.fillText(
    metrics
      ? `平均转角 ${metrics.mean.toFixed(3)} rad, 最大转角 ${metrics.maximum.toFixed(3)} rad, 不规则度 ${metrics.irregularity.toFixed(2)}`
      : '曲率指标不可用',
    12,
    41,
  );
  return {
    id: 'segmentation-curvature',
    label: '曲率/边界分析',
    url: canvas.toDataURL('image/jpeg', 0.88),
    kind: 'curvature',
    caption: metrics
      ? `基于实际分割轮廓的曲率着色, 不规则度 ${metrics.irregularity.toFixed(2)}`
      : '基于实际分割轮廓的曲率着色',
    selected: true,
  };
}

export async function buildReportEvidenceImages(
  input: ReportEvidenceImageInput,
): Promise<GcUsReportImage[]> {
  if (typeof window === 'undefined') return [];
  const images: GcUsReportImage[] = [];
  const current = await renderSegmentationImage(
    input.current,
    input.wallPolygon,
    input.lumenPolygon,
    input.lumenBBox,
  ).catch(() => null);
  const roi = await renderRoiImage(input.current).catch(() => null);
  const curvature = await renderCurvatureImage(input.current).catch(() => null);
  if (current) images.push(current);
  if (roi) images.push(roi);
  if (curvature) images.push(curvature);

  for (const keyframe of (input.keyframes || []).slice(0, 6)) {
    const image = await renderSegmentationImage(keyframe).catch(() => null);
    if (image) images.push(image);
  }
  return images;
}

export function reportImageFromBase64(
  id: string,
  label: string,
  value: string,
  caption: string,
  kind: GcUsReportImage['kind'] = 'analysis',
): GcUsReportImage {
  return {
    id,
    label,
    url: imageDataUrl(value, 'image/png'),
    kind,
    caption,
    selected: true,
  };
}
