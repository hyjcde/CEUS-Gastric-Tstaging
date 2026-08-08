import { jsPDF } from "jspdf";
import type { Report } from "@/app/reports/report-data";

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
