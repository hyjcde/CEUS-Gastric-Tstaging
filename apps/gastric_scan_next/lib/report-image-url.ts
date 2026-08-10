import type { GcUsReportImage } from '@/lib/gc-us-report-template';

/** URLs that browsers can render in a report preview without filesystem or script schemes. */
export function isRenderableReportImageUrl(url: unknown): url is string {
  if (typeof url !== 'string') return false;
  const value = url.trim();
  if (!value) return false;
  if (/^(javascript|file|vbscript):/i.test(value)) return false;
  if (/^data:image\/[a-z0-9.+-]+(;|,)/i.test(value)) return true;
  if (/^blob:/i.test(value)) return true;
  if (/^https?:\/\//i.test(value)) return true;
  if (/^\/(?:api|_next|images|public)\//i.test(value)) return true;
  return false;
}

export function normalizeReportImageUrl(url: string): string {
  return url.trim();
}

export function sanitizeReportImages(images: GcUsReportImage[] | null | undefined): GcUsReportImage[] {
  const seen = new Set<string>();
  const out: GcUsReportImage[] = [];
  for (const image of images || []) {
    if (!image?.id || !isRenderableReportImageUrl(image.url)) continue;
    if (seen.has(image.id)) continue;
    seen.add(image.id);
    out.push({
      ...image,
      url: normalizeReportImageUrl(image.url),
    });
  }
  return out;
}

/** Prefer stable canvas data URLs and current-frame overlays over remote artifacts. */
export function preferReliableReportImages(images: GcUsReportImage[]): GcUsReportImage[] {
  const score = (image: GcUsReportImage): number => {
    const url = image.url || '';
    if (url.startsWith('data:image/')) return 0;
    if (url.startsWith('blob:')) return 1;
    if (/segmentation|overlay|roi|reader-current|keyframe/i.test(`${image.id} ${image.label}`)) return 2;
    if (url.startsWith('/api/agent/artifacts/')) return 3;
    if (url.startsWith('/api/')) return 4;
    return 5;
  };
  return [...images].sort((a, b) => score(a) - score(b));
}
