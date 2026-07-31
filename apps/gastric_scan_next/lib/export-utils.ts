import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { ConceptState, Patient } from '@/types';
import { DiagnosisResult } from './diagnosis';

/**
 * 导出诊断报告为 PDF
 */
export async function exportReportToPDF(
  elementId: string,
  filename: string = `report_${Date.now()}.pdf`
): Promise<void> {
  const element = document.getElementById(elementId);
  if (!element) {
    throw new Error('Report element not found');
  }

  try {
    // 使用 html2canvas 将元素转换为图片
    const canvas = await html2canvas(element, {
      scale: 2, // 提高清晰度
      useCORS: true,
      logging: false,
      backgroundColor: '#0b0b0d',
    });

    const imgData = canvas.toDataURL('image/png');
    
    // 创建 PDF（A4 尺寸）
    const pdf = new jsPDF('p', 'mm', 'a4');
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = pdf.internal.pageSize.getHeight();
    
    // 计算图片尺寸以适应 PDF
    const imgWidth = canvas.width;
    const imgHeight = canvas.height;
    const ratio = Math.min(pdfWidth / (imgWidth * 0.264583), pdfHeight / (imgHeight * 0.264583));
    const imgWidthMM = imgWidth * 0.264583 * ratio;
    const imgHeightMM = imgHeight * 0.264583 * ratio;
    
    // 居中放置图片
    const xOffset = (pdfWidth - imgWidthMM) / 2;
    const yOffset = (pdfHeight - imgHeightMM) / 2;
    
    pdf.addImage(imgData, 'PNG', xOffset, yOffset, imgWidthMM, imgHeightMM);
    
    // 如果内容超过一页，添加新页
    if (imgHeightMM > pdfHeight) {
      const remainingHeight = imgHeightMM - pdfHeight;
      const pages = Math.ceil(remainingHeight / pdfHeight);
      
      for (let i = 1; i <= pages; i++) {
        pdf.addPage();
        const yPos = -pdfHeight * i + yOffset;
        pdf.addImage(imgData, 'PNG', xOffset, yPos, imgWidthMM, imgHeightMM);
      }
    }
    
    pdf.save(filename);
  } catch (error) {
    console.error('Failed to export PDF:', error);
    throw error;
  }
}

/**
 * 导出诊断数据为 CSV
 */
export function exportDataToCSV(
  patients: Array<{
    patient: Patient;
    conceptState: ConceptState;
    diagnosis: DiagnosisResult;
  }>,
  filename: string = `diagnosis_data_${Date.now()}.csv`
): void {
  // CSV 表头
  const headers = [
    'Patient ID',
    'Patient ID Short',
    'T-Stage',
    'N-Stage',
    'Confidence (Overall)',
    'Confidence (T)',
    'Confidence (N)',
    'T-Score',
    'N-Score',
    'Prob T4',
    'Prob T3',
    'Prob T2',
    'Prob N3',
    'Prob N2',
    'Prob N1',
    'Prob N0',
    'Ki-67 (C1)',
    'CPS (C2)',
    'PD-1 (C3)',
    'FoxP3 (C4)',
    'CD3 (C5)',
    'CD4 (C6)',
    'CD8 (C7)',
    'Differentiation',
    'Lauren Type',
    'Vascular Invasion',
    'Neural Invasion',
    'Is T4',
    'Has Metastasis',
    'High Risk',
    'Age',
    'Sex',
    'Tumor Size (Length)',
    'Tumor Size (Thickness)',
    'Location',
    'CEA',
    'CA19-9',
    'Differentiation',
    'Lauren',
    'Source',
    'Frame Count',
    'Has Annotation',
    'Has Overlay',
    'Has ROI',
  ];

  // 构建 CSV 行
  const rows = patients.map(({ patient, conceptState, diagnosis }) => {
    return [
      patient.id,
      patient.id_short,
      diagnosis.tStage,
      diagnosis.nStage,
      diagnosis.confidence.overall,
      diagnosis.confidence.t,
      diagnosis.confidence.n,
      diagnosis.scores.t,
      diagnosis.scores.n,
      diagnosis.probabilities.t4,
      diagnosis.probabilities.t3,
      diagnosis.probabilities.t2,
      diagnosis.probabilities.n3,
      diagnosis.probabilities.n2,
      diagnosis.probabilities.n1,
      diagnosis.probabilities.n0,
      conceptState.c1,
      conceptState.c2,
      conceptState.c3,
      conceptState.c4,
      conceptState.c5,
      conceptState.c6,
      conceptState.c7,
      conceptState.differentiation,
      conceptState.lauren,
      conceptState.vascularInvasion,
      conceptState.neuralInvasion,
      diagnosis.flags.isT4 ? 'Yes' : 'No',
      diagnosis.flags.hasMetastasis ? 'Yes' : 'No',
      diagnosis.flags.highRisk ? 'Yes' : 'No',
      patient.clinical?.age ?? '',
      patient.clinical?.sex ?? '',
      patient.clinical?.tumorSize?.length ?? '',
      patient.clinical?.tumorSize?.thickness ?? '',
      patient.clinical?.location ?? '',
      patient.clinical?.biomarkers?.cea ?? '',
      patient.clinical?.biomarkers?.ca199 ?? '',
      patient.clinical?.differentiation ?? '',
      patient.clinical?.lauren ?? '',
      patient.source_label ?? '',
      patient.frame_count ?? '',
      patient.segmentation?.has_annotation ? 'Yes' : 'No',
      patient.segmentation?.has_overlay ? 'Yes' : 'No',
      patient.segmentation?.has_roi ? 'Yes' : 'No',
    ];
  });

  // 转义 CSV 字段（处理逗号、引号、换行）
  const escapeCSV = (value: unknown): string => {
    if (value === null || value === undefined) return '';
    const str = String(value);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  // 构建 CSV 内容
  const csvContent = [
    headers.map(escapeCSV).join(','),
    ...rows.map(row => row.map(escapeCSV).join(','))
  ].join('\n');

  // 创建 Blob 并下载
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * 导出单个患者的诊断数据为 CSV
 */
export function exportSinglePatientToCSV(
  patient: Patient,
  conceptState: ConceptState,
  diagnosis: DiagnosisResult,
  filename?: string
): void {
  exportDataToCSV([{ patient, conceptState, diagnosis }], filename || `patient_${patient.id}_${Date.now()}.csv`);
}

