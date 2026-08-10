import { jsPDF } from "jspdf";
import type { Report } from "@/app/reports/report-data";
import {
  buildGcUsTemplateReportText,
  resolveGcUsReportLocale,
  type GcUsReportLocale,
  type GcUsReportState,
} from "@/lib/gc-us-report-template";
import { exportTemplateReportToPDF } from "@/lib/template-report-export";

export function downloadReportPdf(report: Report) {
  const pdf = new jsPDF();
  const lines = [
    "Gastric Filling Ultrasound Intelligent Diagnosis",
    "",
    `Report ID: ${report.id}`,
    `Patient ID: ${report.patient}`,
    `Date: ${report.date}`,
    `Stage prediction: ${report.stage}`,
    `Status: ${report.status}`,
    "",
    "This report is an assistive clinical decision-support output.",
    "Final interpretation requires clinician review and correlation with the complete examination.",
  ];

  pdf.setFontSize(16);
  pdf.text(lines[0], 14, 20);
  pdf.setFontSize(11);
  pdf.text(lines.slice(2), 14, 34);
  pdf.save(`${report.id}.pdf`);
}

export async function downloadSavedTemplateReportPdf(
  reportId: string,
  filename?: string,
  revision?: number,
  locale: GcUsReportLocale = 'zh',
): Promise<void> {
  const query = new URLSearchParams({ report_id: reportId });
  if (Number.isFinite(revision)) query.set('revision', String(revision));
  const response = await fetch(`/api/reports/template?${query.toString()}`);
  const payload = await response.json().catch(() => null) as {
    ok?: boolean;
    report?: GcUsReportState | null;
  } | null;
  if (!response.ok || !payload?.ok || !payload.report) {
    throw new Error('Saved template report could not be loaded');
  }

  const reportState = payload.report;
  const prose = buildGcUsTemplateReportText(reportState, locale);
  const title = locale === 'en' ? 'Gastric Cancer Ultrasound Report' : '胃癌超声报告';
  const imageHeading = locale === 'en' ? 'Key images' : '关键图像';
  const outName = filename
    || (locale === 'en'
      ? `gastric_us_report_${reportId}_v${reportState.report.revision || 0}.pdf`
      : `胃充盈超声报告_${reportId}_v${reportState.report.revision || 0}.pdf`);

  const previewId = `saved-template-report-${reportId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const preview = document.createElement('article');
  preview.id = previewId;
  preview.style.position = 'absolute';
  preview.style.left = '-100000px';
  preview.style.top = '0';
  preview.style.width = '794px';
  preview.style.padding = '72px 76px';
  preview.style.background = '#ffffff';
  preview.style.color = '#000000';
  preview.style.fontFamily = '"Times New Roman", "SimSun", "宋体", serif';
  preview.style.fontSize = '13px';
  preview.style.lineHeight = '1.9';

  const titleEl = document.createElement('h1');
  titleEl.textContent = title;
  titleEl.style.margin = '0 0 24px';
  titleEl.style.textAlign = 'center';
  titleEl.style.fontSize = '24px';
  preview.append(titleEl);

  const body = document.createElement('pre');
  body.textContent = prose;
  body.style.whiteSpace = 'pre-wrap';
  body.style.font = 'inherit';
  body.style.margin = '0';
  preview.append(body);

  const images = reportState.report_images.filter((image) => image.selected !== false);
  if (images.length) {
    const imageHeadingEl = document.createElement('h2');
    imageHeadingEl.textContent = imageHeading;
    imageHeadingEl.style.margin = '28px 0 8px';
    imageHeadingEl.style.fontSize = '16px';
    preview.append(imageHeadingEl);
    for (const image of images) {
      const figure = document.createElement('figure');
      figure.style.margin = '0 0 16px';
      const imageElement = document.createElement('img');
      imageElement.src = image.url;
      imageElement.alt = image.label;
      imageElement.crossOrigin = 'anonymous';
      imageElement.style.display = 'block';
      imageElement.style.width = '100%';
      imageElement.style.maxHeight = '360px';
      imageElement.style.objectFit = 'contain';
      figure.append(imageElement);
      const caption = document.createElement('figcaption');
      caption.textContent = image.caption || image.label;
      caption.style.textAlign = 'center';
      caption.style.fontSize = '10px';
      figure.append(caption);
      preview.append(figure);
    }
  }

  document.body.append(preview);
  try {
    await exportTemplateReportToPDF(previewId, outName);
  } finally {
    preview.remove();
  }
}

export function localeFromUiLanguage(language: string | undefined): GcUsReportLocale {
  return resolveGcUsReportLocale(language !== 'en');
}
