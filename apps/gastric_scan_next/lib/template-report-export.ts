import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

const IMAGE_PLACEHOLDER = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"><rect width="640" height="360" fill="#f3f4f6"/><path d="M80 280l120-120 90 90 70-70 200 100" fill="none" stroke="#9ca3af" stroke-width="8"/><text x="320" y="190" text-anchor="middle" font-family="sans-serif" font-size="24" fill="#6b7280">图像暂不可用</text></svg>',
)}`;

function safeFilename(value: string): string {
  const normalized = value
    .replace(/[\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, '_')
    .trim();
  if (!normalized) return 'gastric_ultrasound_report.pdf';
  return normalized.toLowerCase().endsWith('.pdf') ? normalized : `${normalized}.pdf`;
}

function parseCssNumber(value: string, percentageScale = 1): number | null {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'none') return 0;
  const parsed = Number.parseFloat(normalized);
  if (!Number.isFinite(parsed)) return null;
  return normalized.endsWith('%') ? (parsed / 100) * percentageScale : parsed;
}

function parseCssHue(value: string): number | null {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'none') return 0;
  const parsed = Number.parseFloat(normalized);
  if (!Number.isFinite(parsed)) return null;
  if (normalized.endsWith('turn')) return parsed * 360;
  if (normalized.endsWith('rad')) return (parsed * 180) / Math.PI;
  if (normalized.endsWith('grad')) return parsed * 0.9;
  return parsed;
}

function oklchToRgb(value: string): string | null {
  const [channelText, alphaText] = value.trim().split(/\s*\/\s*/, 2);
  const channels = channelText.split(/[\s,]+/).filter(Boolean);
  if (channels.length < 3) return null;

  const lightness = parseCssNumber(channels[0]);
  const chroma = parseCssNumber(channels[1], 0.4);
  const hue = parseCssHue(channels[2]);
  const alpha = alphaText == null ? 1 : parseCssNumber(alphaText);
  if (
    lightness == null
    || chroma == null
    || hue == null
    || alpha == null
  ) {
    return null;
  }

  const hueRadians = (hue * Math.PI) / 180;
  const a = chroma * Math.cos(hueRadians);
  const b = chroma * Math.sin(hueRadians);
  const l = lightness + 0.3963377774 * a + 0.2158037573 * b;
  const m = lightness - 0.1055613458 * a - 0.0638541728 * b;
  const s = lightness - 0.0894841775 * a - 1.291485548 * b;
  const l3 = l ** 3;
  const m3 = m ** 3;
  const s3 = s ** 3;
  const linearRed = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3;
  const linearGreen = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3;
  const linearBlue = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3;
  const toByte = (channel: number) => {
    const encoded = channel <= 0.0031308
      ? 12.92 * channel
      : 1.055 * (Math.max(0, channel) ** (1 / 2.4)) - 0.055;
    return Math.round(Math.min(1, Math.max(0, encoded)) * 255);
  };
  const red = toByte(linearRed);
  const green = toByte(linearGreen);
  const blue = toByte(linearBlue);
  const normalizedAlpha = Math.min(1, Math.max(0, alpha));
  return normalizedAlpha < 1
    ? `rgba(${red}, ${green}, ${blue}, ${normalizedAlpha})`
    : `rgb(${red}, ${green}, ${blue})`;
}

function replaceUnsupportedCssColors(value: string): string {
  return value.replace(/\b(oklch|oklab|lab|lch)\(([^()]*)\)/gi, (match, functionName: string, channels: string) => {
    if (functionName.toLowerCase() === 'oklch') {
      return oklchToRgb(channels) || 'rgb(0, 0, 0)';
    }
    return 'rgb(0, 0, 0)';
  });
}

function normalizeCloneColors(clonedDocument: Document): void {
  const clonedWindow = clonedDocument.defaultView;
  if (!clonedWindow) return;

  for (const element of clonedDocument.querySelectorAll('*')) {
    const computedStyle = clonedWindow.getComputedStyle(element);
    const properties = Array.from(
      { length: computedStyle.length },
      (_, index) => computedStyle.item(index),
    ).filter((property): property is string => Boolean(property));
    const inlineStyle = (element as HTMLElement).style;
    for (const property of properties) {
      const value = computedStyle.getPropertyValue(property);
      if (!/\b(?:oklch|oklab|lab|lch)\(/i.test(value)) continue;
      inlineStyle.setProperty(property, replaceUnsupportedCssColors(value));
    }
  }
}

async function waitForImages(element: HTMLElement): Promise<void> {
  const images = Array.from(element.querySelectorAll('img'));
  await Promise.all(images.map(async (image) => {
    if (!image.complete) {
      await new Promise<void>((resolve) => {
        const finish = () => {
          image.removeEventListener('load', finish);
          image.removeEventListener('error', finish);
          resolve();
        };
        image.addEventListener('load', finish, { once: true });
        image.addEventListener('error', finish, { once: true });
        window.setTimeout(finish, 8000);
      });
    }
    if (typeof image.decode === 'function') {
      await image.decode().catch(() => undefined);
    }
  }));
}

function safePageBoundary(
  element: HTMLElement,
  offset: number,
  proposedHeight: number,
  canvasScale: number,
): number {
  const rootRect = element.getBoundingClientRect();
  const proposedBoundary = offset + proposedHeight;
  const blocks = Array.from(element.querySelectorAll('header, section, figure, footer, h1, h2, h3'));
  let boundary = proposedBoundary;
  for (const block of blocks) {
    const rect = (block as HTMLElement).getBoundingClientRect();
    const top = Math.max(0, Math.round((rect.top - rootRect.top) * canvasScale));
    const bottom = Math.round((rect.bottom - rootRect.top) * canvasScale);
    if (top > offset + 48 && top < proposedBoundary && bottom > proposedBoundary) {
      boundary = Math.min(boundary, top - 12);
    }
  }
  return boundary - offset > 160 ? boundary - offset : proposedHeight;
}

/**
 * Export the visible A4 template preview as a multi-page PDF.
 *
 * The supplied DOCX contains Chinese glyphs and no editable Word controls.
 * Rasterizing the already-rendered preview keeps Chinese text, embedded
 * ultrasound images, and the template layout together without requiring a
 * server-side Office installation.
 */
export async function exportTemplateReportToPDF(
  elementId: string,
  filename: string,
): Promise<void> {
  const element = document.getElementById(elementId);
  if (!element) throw new Error('Template report preview not found');

  await waitForImages(element);
  const canvasScale = Math.max(1, (element.getBoundingClientRect().width
    ? (window.devicePixelRatio || 1)
    : 1));
  const canvas = await html2canvas(element, {
    backgroundColor: '#ffffff',
    logging: false,
    scale: Math.min(2, canvasScale),
    useCORS: true,
    allowTaint: false,
    onclone: (clonedDocument) => {
      normalizeCloneColors(clonedDocument);
      clonedDocument.querySelectorAll('img').forEach((node) => {
        const image = node as HTMLImageElement;
        image.crossOrigin = 'anonymous';
        if (image.complete && image.naturalWidth === 0) image.src = IMAGE_PLACEHOLDER;
        image.addEventListener('error', () => {
          image.src = IMAGE_PLACEHOLDER;
        }, { once: true });
      });
    },
  });
  const pdf = new jsPDF('p', 'mm', 'a4');
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const pixelsPerMillimeter = canvas.width / pageWidth;
  const pageHeightPixels = Math.max(1, Math.floor(pageHeight * pixelsPerMillimeter));

  let offset = 0;
  let pageIndex = 0;
  while (offset < canvas.height) {
    const proposedHeight = Math.min(pageHeightPixels, canvas.height - offset);
    const sliceHeight = safePageBoundary(
      element,
      offset,
      proposedHeight,
      canvas.width / Math.max(1, element.getBoundingClientRect().width),
    );
    const pageCanvas = document.createElement('canvas');
    pageCanvas.width = canvas.width;
    pageCanvas.height = sliceHeight;
    const context = pageCanvas.getContext('2d');
    if (!context) throw new Error('Unable to create PDF canvas');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, pageCanvas.width, pageCanvas.height);
    context.drawImage(
      canvas,
      0,
      offset,
      canvas.width,
      sliceHeight,
      0,
      0,
      pageCanvas.width,
      pageCanvas.height,
    );

    if (pageIndex > 0) pdf.addPage();
    pdf.addImage(
      pageCanvas.toDataURL('image/jpeg', 0.95),
      'JPEG',
      0,
      0,
      pageWidth,
      sliceHeight / pixelsPerMillimeter,
      undefined,
      'FAST',
    );
    offset += sliceHeight;
    pageIndex += 1;
  }

  pdf.setProperties({
    title: '胃充盈超声检查报告',
    subject: 'Template-based gastric filling ultrasound report',
    author: 'Gastric Scan Next',
  });
  pdf.save(safeFilename(filename));
}
