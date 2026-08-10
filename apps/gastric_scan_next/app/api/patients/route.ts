import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import {
  DatasetType,
  CohortYear,
  TreatmentType,
  getBenignDatasetPaths,
  getClinicalDataPath,
  getDatasetPaths,
  getExternalDatasetPaths,
  parseCohortYear,
  parseDatasetType,
} from '@/lib/config';
import {
  BENIGN_CENTER_OPTIONS,
  EXTERNAL_CENTER_OPTIONS,
  GASTRIC_COHORT_YEARS,
  getExternalCenterById,
  parseWorkbenchQueueId,
  WorkbenchQueueId,
} from '@/lib/cohort';
import { getVideosForPatient } from '@/lib/video-index';
import { loadReaderCasesBundle } from '@/lib/reader/cases-server';
import { readerMediaUrl } from '@/lib/reader/media-url';
import { resolveResearchReader } from '@/lib/reader/study-auth';
import { READER_ROUND2_FREEZE_ID, READER_ROUND2_ORDER_SEED } from '@/lib/reader/study-contract';
import { sortReaderRound2Patients } from '@/lib/reader/round2-order';
import { clinicalFromReaderUsTable } from '@/lib/reader/us-clinical-server';
import { enrichConceptFeaturesFromClinical } from '@/lib/concept-extract';
import { AgentReport, ClinicalData, ConceptFeatures, Patient, PatientReportData } from '@/types';

interface PatientAsset {
  filename: string;
  frame: number;
  path: string;
}

interface PatientInfo {
  patient_id: string;
  dataset: string;
  dataset_type: string;
  label_bm?: string;
  T_stage?: string;
  T_label?: number | null;
  num_images: number;
  num_annotations?: number;
  num_overlays?: number;
  num_roi?: number;
  images: PatientAsset[];
  annotations?: PatientAsset[];
  overlays?: PatientAsset[];
  roi?: PatientAsset[];
  clinical_info?: Record<string, unknown>;
}

interface CurrentDatasetAssets {
  imageFilename: string;
  annotationFilename?: string;
  overlayFilename?: string;
  overlayDataset?: DatasetType;
  cropUiFilename?: string;
  roiFilename?: string;
}

interface PatientPageOptions {
  offset?: number;
  limit?: number;
}

interface PatientQueueSource {
  count: number;
  build: (offset: number, limit: number) => Patient[];
}

const imageFileCache = new Map<string, string[]>();

function normalizePatientId(patientId: string): string {
  if (!patientId) return '';
  if (patientId.startsWith('Z')) return patientId;
  return patientId.replace(/^0+/, '') || patientId;
}

function parseNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const cleaned = String(value).replace(/[^\d.]/g, '');
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseBooleanMarker(value: unknown): boolean {
  const normalized = String(value ?? '').trim().toLowerCase();
  return ['1', 'true', 'yes', 'positive', '+', '阳性', '＞正常'].some(token => normalized.includes(token));
}

function normalizeSex(value: unknown): string {
  const raw = String(value ?? '').trim();
  if (!raw) return 'N/A';
  if (raw === '男' || raw.toLowerCase() === 'male') return 'Male';
  if (raw === '女' || raw.toLowerCase() === 'female') return 'Female';
  return raw;
}

function firstTextValue(clinical: Record<string, unknown> | undefined, keys: string[]): string | undefined {
  if (!clinical) return undefined;
  for (const key of keys) {
    const value = clinical[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function toPublicReport(clinical: Record<string, unknown> | undefined): PatientReportData | undefined {
  if (!clinical) return undefined;
  const report: PatientReportData = {
    ultrasound_report: firstTextValue(clinical, [
      'ultrasound_report',
      'us_report',
      '超声报告',
      '胃超声报告',
      'report_text',
    ]),
    ultrasound_findings: firstTextValue(clinical, [
      'ultrasound_findings',
      'us_findings',
      'findings',
      '超声所见',
      '影像所见',
    ]),
    ultrasound_impression: firstTextValue(clinical, [
      'ultrasound_impression',
      'us_impression',
      'impression',
      '超声提示',
      '影像诊断',
    ]),
    ct_report: firstTextValue(clinical, [
      'ct_report',
      'ct_findings',
      'ct_impression',
      'enhanced_ct_report',
      '增强CT报告',
      'CT报告',
      'CT所见',
      'CT提示',
    ]),
    ct_findings: firstTextValue(clinical, [
      'ct_findings',
      'enhanced_ct_findings',
      '增强CT所见',
      'CT所见',
    ]),
    ct_impression: firstTextValue(clinical, [
      'ct_impression',
      'enhanced_ct_impression',
      '增强CT提示',
      'CT提示',
    ]),
    enhanced_ct_report: firstTextValue(clinical, [
      'enhanced_ct_report',
      'enhanced_ct',
      '增强CT报告',
    ]),
    endoscopy_report: firstTextValue(clinical, [
      'endoscopy_report',
      'gastroscopy_report',
      '胃镜报告',
      '内镜报告',
    ]),
    pathology_report: firstTextValue(clinical, [
      'pathology_report',
      '病理报告',
      'pathology_text',
    ]),
    report_source: firstTextValue(clinical, ['report_source', 'source_file', 'table_source']),
  };

  return Object.values(report).some(Boolean) ? report : undefined;
}

function buildConceptFeatures(clinical: Record<string, unknown> | undefined): ConceptFeatures | undefined {
  return enrichConceptFeaturesFromClinical(clinical);
}

function toPublicClinical(clinical: Record<string, unknown> | undefined): ClinicalData | undefined {
  if (!clinical) return undefined;

  return {
    age: parseNullableNumber(clinical.age),
    sex: normalizeSex(clinical.sex),
    tumorSize: {
      length: parseNullableNumber(clinical.tumor_length_cm),
      thickness: parseNullableNumber(clinical.tumor_thickness_cm),
    },
    location: String(clinical.tumor_location ?? ''),
    biomarkers: {
      cea: parseNullableNumber(clinical.CEA_value),
      ca199: parseNullableNumber(clinical.CA199_value),
      cea_positive: parseBooleanMarker(clinical.CEA_status),
      ca199_positive: parseBooleanMarker(clinical.CA199_status),
    },
    differentiation: String(clinical.differentiation ?? ''),
    lauren: String(clinical.lauren_type ?? ''),
    concept_features: buildConceptFeatures(clinical),
  };
}

function normalizeCurrentClinical(clinical: Record<string, unknown> | undefined): ClinicalData | undefined {
  if (!clinical) return undefined;

  if ('tumorSize' in clinical || 'biomarkers' in clinical) {
    const tumorSize = clinical.tumorSize as Record<string, unknown> | undefined;
    const biomarkers = clinical.biomarkers as Record<string, unknown> | undefined;
    const pathology = clinical.pathology as Record<string, unknown> | undefined;

    return {
      age: parseNullableNumber(clinical.age),
      sex: normalizeSex(clinical.sex),
      tumorSize: {
        length: parseNullableNumber(tumorSize?.length),
        thickness: parseNullableNumber(tumorSize?.thickness),
      },
      location: String(clinical.location ?? ''),
      biomarkers: {
        cea: parseNullableNumber(biomarkers?.cea),
        ca199: parseNullableNumber(biomarkers?.ca199),
        cea_positive: Boolean(biomarkers?.cea_positive),
        ca199_positive: Boolean(biomarkers?.ca199_positive),
      },
      differentiation: String(pathology?.differentiation ?? clinical.differentiation ?? ''),
      lauren: String(pathology?.lauren ?? clinical.lauren ?? ''),
      concept_features: enrichConceptFeaturesFromClinical(clinical),
    };
  }

  return toPublicClinical(clinical);
}

function buildAgentReport(info: PatientInfo, annotationAvailable: boolean, overlayAvailable: boolean, roiAvailable: boolean): AgentReport {
  const segmentationStatus = annotationAvailable || overlayAvailable || roiAvailable
    ? (annotationAvailable && overlayAvailable && roiAvailable ? 'available' : 'partial')
    : 'missing';

  return {
    schema_version: '0.1.0',
    case_token: `local-${info.patient_id}`,
    data_source: info.dataset,
    frame_count: info.num_images,
    report_status: 'draft',
    image_quality: {
      status: 'pending',
      summary: 'Quality tool not connected yet. Use original image and ROI availability as provisional cues.',
    },
    segmentation: {
      status: segmentationStatus,
      summary: annotationAvailable
        ? 'Manual annotation available for this frame.'
        : overlayAvailable
          ? 'Overlay available without direct annotation payload.'
          : roiAvailable
            ? 'ROI crop available but no annotation payload exposed.'
            : 'No segmentation evidence asset was found for this frame.',
    },
    classification: {
      status: 'pending',
      summary: 'Run Agent Workbench analysis to load acc_boost2 T-staging probabilities (mask4ch + clinical22 + lumen/wall evidence).',
    },
    similar_case_support: {
      status: 'pending',
      summary: 'Similar-case retrieval runs inside Agent Workbench after analysis.',
    },
    manual_review_recommended: !annotationAvailable || !roiAvailable,
  };
}

function extractPatientId(filename: string): string {
  const base = filename.replace(/\.[^.]+$/i, '');
  const zMatch = base.match(/(Z\d{5,})/i);
  if (zMatch) {
    return zMatch[1].toUpperCase();
  }

  // 2018/2019/2020_2023/2024: ...__patientId-frameIndex
  const frameMatch = base.match(/_(\d+)-(\d+)$/);
  if (frameMatch) {
    return frameMatch[1];
  }

  const numericMatches = base.match(/\d{6,}/g);
  if (numericMatches?.length) {
    return numericMatches[numericMatches.length - 1];
  }
  return base;
}

function buildCurrentDatasetLabel(cohortYear: CohortYear, treatmentType: TreatmentType): string {
  if (cohortYear === 'gist') return 'legacy-gist';
  const treatmentSuffix = treatmentType === 'nac' ? 'nac' : 'surgery';
  return `internal-${cohortYear}-${treatmentSuffix}`;
}

function readImageFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  const cached = imageFileCache.get(dir);
  if (cached) return cached;
  const files = fs.readdirSync(dir)
    .filter((file) => !file.startsWith('.') && /\.(jpg|jpeg|png|webp)$/i.test(file))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
  imageFileCache.set(dir, files);
  return files;
}

function maybeOverlayFilename(filename: string): string {
  return filename.replace(/\.(jpg|jpeg)$/i, '_overlay.jpg');
}

function maybeAnnotationFilename(filename: string): string {
  return filename.replace(/\.(jpg|jpeg)$/i, '.json');
}

function readClinicalDataMap(cohortYear: CohortYear, treatmentType: TreatmentType): Record<string, Record<string, unknown>> {
  const clinicalDataPath = getClinicalDataPath(cohortYear, treatmentType);
  if (!clinicalDataPath || !fs.existsSync(clinicalDataPath)) {
    return {};
  }

  return JSON.parse(fs.readFileSync(clinicalDataPath, 'utf-8')) as Record<string, Record<string, unknown>>;
}

function getClinicalEntryForPatient(
  clinicalData: Record<string, Record<string, unknown>>,
  patientId: string,
): Record<string, unknown> | undefined {
  const candidates = new Set([
    patientId,
    patientId.replace(/^0+/, ''),
    patientId.padStart(7, '0'),
    patientId.toUpperCase(),
    `0${patientId.replace(/^0+/, '')}`,
  ]);

  for (const key of candidates) {
    if (clinicalData[key]) return clinicalData[key];
  }
  return undefined;
}

function buildCurrentPatients(
  cohortYear: Exclude<CohortYear, 'gist'>,
  treatmentType: TreatmentType,
  dataset: DatasetType,
  page?: PatientPageOptions,
): Patient[] {
  const clinicalDataPath = getClinicalDataPath(cohortYear, treatmentType);
  if (treatmentType === 'nac' && !fs.existsSync(clinicalDataPath)) {
    return [];
  }

  const originalPaths = getDatasetPaths('original', cohortYear, treatmentType);
  const croppedPaths = getDatasetPaths('cropped', cohortYear, treatmentType);
  const displayPaths = getDatasetPaths(dataset, cohortYear, treatmentType);
  const imageFiles = readImageFiles(displayPaths.images);
  const offset = Math.max(0, page?.offset || 0);
  const limit = Math.max(1, page?.limit || imageFiles.length || 1);
  const selectedImageFiles = page ? imageFiles.slice(offset, offset + limit) : imageFiles;
  const clinicalData = readClinicalDataMap(cohortYear, treatmentType);

  const grouped = new Map<string, CurrentDatasetAssets[]>();
  const frameCounts = page
    ? imageFiles.reduce((counts, filename) => {
        const patientId = extractPatientId(filename);
        counts.set(patientId, (counts.get(patientId) || 0) + 1);
        return counts;
      }, new Map<string, number>())
    : null;

  for (const imageFilename of selectedImageFiles) {
    const patientId = extractPatientId(imageFilename);
    const annotationFilename = maybeAnnotationFilename(imageFilename);
    const overlayFilename = maybeOverlayFilename(imageFilename);
    const displayOverlayExists = fs.existsSync(path.join(displayPaths.overlays, overlayFilename));
    const originalOverlayExists = fs.existsSync(path.join(originalPaths.overlays, overlayFilename));

    const item: CurrentDatasetAssets = {
      imageFilename,
      annotationFilename: fs.existsSync(path.join(originalPaths.annotations, annotationFilename)) ? annotationFilename : undefined,
      overlayFilename: displayOverlayExists || originalOverlayExists ? overlayFilename : undefined,
      overlayDataset: displayOverlayExists ? dataset : (originalOverlayExists ? 'original' : undefined),
      cropUiFilename: fs.existsSync(path.join(croppedPaths.images, imageFilename)) ? imageFilename : undefined,
      roiFilename: fs.existsSync(path.join(croppedPaths.roi, imageFilename)) ? imageFilename : undefined,
    };

    const patientAssets = grouped.get(patientId) ?? [];
    patientAssets.push(item);
    grouped.set(patientId, patientAssets);
  }

  const sourceLabel = buildCurrentDatasetLabel(cohortYear, treatmentType);
  const patients: Patient[] = [];

  for (const [patientId, assets] of grouped.entries()) {
    const rawClinical = getClinicalEntryForPatient(clinicalData, patientId);
    const clinical = normalizeCurrentClinical(rawClinical);
    const report = toPublicReport(rawClinical);
    const sortedAssets = assets.sort((a, b) => a.imageFilename.localeCompare(b.imageFilename, undefined, { numeric: true, sensitivity: 'base' }));

    for (const asset of sortedAssets) {
      const hasAnnotation = Boolean(asset.annotationFilename);
      const hasOverlay = Boolean(asset.overlayFilename);
      const hasRoi = Boolean(asset.roiFilename);
      if (dataset === 'cropped' && !asset.cropUiFilename) continue;
      const imageFilename = dataset === 'cropped' ? asset.cropUiFilename! : asset.imageFilename;

      const info: PatientInfo = {
        patient_id: patientId,
        dataset: sourceLabel,
        dataset_type: dataset,
        num_images: frameCounts?.get(patientId) ?? sortedAssets.length,
        num_annotations: hasAnnotation ? 1 : 0,
        num_overlays: hasOverlay ? 1 : 0,
        num_roi: hasRoi ? 1 : 0,
        images: [],
        annotations: [],
        overlays: [],
        roi: [],
        clinical_info: clinical as unknown as Record<string, unknown> | undefined,
      };

      patients.push({
        id: asset.imageFilename,
        id_short: asset.imageFilename.replace(/\.(jpg|jpeg)$/i, ''),
        patient_id: normalizePatientId(patientId),
        group: treatmentType === 'nac' ? 'NAC' : 'Surgery',
        phase: cohortYear,
        source_label: sourceLabel,
        queue_id: `internal:${cohortYear}`,
        center_id: 'internal_xh',
        center_label: '福建医科大学附属协和医院',
        frame_count: frameCounts?.get(patientId) ?? sortedAssets.length,
        image_url: `/api/images/${dataset}/images/${encodeURIComponent(imageFilename)}?cohort=${cohortYear}&treatment=${treatmentType}`,
        overlay_url: hasOverlay ? `/api/images/${asset.overlayDataset || 'original'}/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        overlay_transparent_url: hasOverlay ? `/api/images/${asset.overlayDataset || 'original'}/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        roi_url: hasRoi ? `/api/images/cropped/roi/${encodeURIComponent(asset.roiFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        json_url: hasAnnotation ? `/api/images/original/annotations/${encodeURIComponent(asset.annotationFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        video_urls: getVideosForPatient(normalizePatientId(patientId)),
        segmentation: {
          source: sourceLabel,
          has_annotation: hasAnnotation,
          has_overlay: hasOverlay,
          has_roi: hasRoi,
          annotation_count: hasAnnotation ? 1 : 0,
          frame_count: sortedAssets.length,
          roi_url: hasRoi ? `/api/images/cropped/roi/${encodeURIComponent(asset.roiFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
          annotation_url: hasAnnotation ? `/api/images/original/annotations/${encodeURIComponent(asset.annotationFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
          overlay_url: hasOverlay ? `/api/images/${asset.overlayDataset || 'original'}/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
          overlay_transparent_url: hasOverlay ? `/api/images/${asset.overlayDataset || 'original'}/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        },
        agent_report: buildAgentReport(info, hasAnnotation, hasOverlay, hasRoi),
        clinical,
        report,
      });
    }
  }

  patients.sort((a, b) => {
    const hasClinicalA = !!a.clinical;
    const hasClinicalB = !!b.clinical;
    if (hasClinicalA && !hasClinicalB) return -1;
    if (!hasClinicalA && hasClinicalB) return 1;
    return a.id.localeCompare(b.id, undefined, { numeric: true, sensitivity: 'base' });
  });

  return patients;
}

function extractExternalPatientId(filename: string): string {
  const base = filename.replace(/\.[^.]+$/i, '');
  const token = base.split('__').pop() || base;
  const parenthesizedFrame = token.match(/^(.*?)-_\(\d+\)$/);
  if (parenthesizedFrame?.[1]) return parenthesizedFrame[1];
  const numberedFrame = token.match(/^(.*?)-\d+$/);
  return numberedFrame?.[1] || token;
}

function buildCenterPatients(
  centerId: string,
  centerLabel: string,
  paths: { images: string; overlays: string; annotations: string; roi: string },
  queueNamespace: 'external' | 'benign',
  group: string,
  phase: string,
  dataset: DatasetType,
  page?: PatientPageOptions,
): Patient[] {
  const imageFiles = readImageFiles(paths.images);
  const offset = Math.max(0, page?.offset || 0);
  const limit = Math.max(1, page?.limit || imageFiles.length || 1);
  const selectedImageFiles = page ? imageFiles.slice(offset, offset + limit) : imageFiles;
  const grouped = new Map<string, string[]>();
  const frameCounts = page
    ? imageFiles.reduce((counts, filename) => {
        const patientId = extractExternalPatientId(filename);
        counts.set(patientId, (counts.get(patientId) || 0) + 1);
        return counts;
      }, new Map<string, number>())
    : null;
  for (const imageFilename of selectedImageFiles) {
    const patientId = extractExternalPatientId(imageFilename);
    const patientAssets = grouped.get(patientId) ?? [];
    patientAssets.push(imageFilename);
    grouped.set(patientId, patientAssets);
  }

  const queueId = `${queueNamespace}:${centerId}`;
  const sourceLabel = `${queueNamespace}-${centerId}`;
  const patients: Patient[] = [];

  for (const [patientId, assets] of grouped.entries()) {
    const sortedAssets = assets.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
    for (const imageFilename of sortedAssets) {
      const annotationFilename = maybeAnnotationFilename(imageFilename);
      const overlayFilename = maybeOverlayFilename(imageFilename);
      const hasAnnotation = fs.existsSync(path.join(paths.annotations, annotationFilename));
      const hasOverlay = fs.existsSync(path.join(paths.overlays, overlayFilename));
      const hasRoi = fs.existsSync(path.join(paths.roi, imageFilename));
      const encodedFilename = encodeURIComponent(imageFilename);
      const queueQuery = `queue=${encodeURIComponent(queueId)}&treatment=surgery`;
      const info: PatientInfo = {
        patient_id: patientId,
        dataset: sourceLabel,
        dataset_type: dataset,
        num_images: frameCounts?.get(patientId) ?? sortedAssets.length,
        num_annotations: hasAnnotation ? 1 : 0,
        num_overlays: hasOverlay ? 1 : 0,
        num_roi: hasRoi ? 1 : 0,
        images: [],
        annotations: [],
        overlays: [],
        roi: [],
      };

      patients.push({
        id: `${queueNamespace}:${centerId}::${imageFilename}`,
        id_short: imageFilename.replace(/\.(jpg|jpeg|png|webp)$/i, ''),
        patient_id: normalizePatientId(patientId),
        group,
        phase,
        source_label: centerLabel,
        queue_id: queueId,
        center_id: centerId,
        center_label: centerLabel,
        frame_count: frameCounts?.get(patientId) ?? sortedAssets.length,
        image_url: `/api/images/${dataset}/images/${encodedFilename}?${queueQuery}`,
        overlay_url: hasOverlay ? `/api/images/${dataset}/overlays/${encodeURIComponent(overlayFilename)}?${queueQuery}` : '',
        overlay_transparent_url: hasOverlay ? `/api/images/${dataset}/overlays/${encodeURIComponent(overlayFilename)}?${queueQuery}` : '',
        roi_url: hasRoi ? `/api/images/cropped/roi/${encodedFilename}?${queueQuery}` : '',
        json_url: hasAnnotation ? `/api/images/original/annotations/${encodeURIComponent(annotationFilename)}?${queueQuery}` : '',
        video_urls: getVideosForPatient(normalizePatientId(patientId)),
        segmentation: {
          source: sourceLabel,
          has_annotation: hasAnnotation,
          has_overlay: hasOverlay,
          has_roi: hasRoi,
          annotation_count: hasAnnotation ? 1 : 0,
          frame_count: frameCounts?.get(patientId) ?? sortedAssets.length,
          roi_url: hasRoi ? `/api/images/cropped/roi/${encodedFilename}?${queueQuery}` : '',
          annotation_url: hasAnnotation ? `/api/images/original/annotations/${encodeURIComponent(annotationFilename)}?${queueQuery}` : '',
          overlay_url: hasOverlay ? `/api/images/${dataset}/overlays/${encodeURIComponent(overlayFilename)}?${queueQuery}` : '',
          overlay_transparent_url: hasOverlay ? `/api/images/${dataset}/overlays/${encodeURIComponent(overlayFilename)}?${queueQuery}` : '',
        },
        agent_report: buildAgentReport(info, hasAnnotation, hasOverlay, hasRoi),
      });
    }
  }

  return patients.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true, sensitivity: 'base' }));
}

function buildExternalPatients(
  centerId: string,
  dataset: DatasetType,
  page?: PatientPageOptions,
): Patient[] {
  const center = getExternalCenterById(centerId);
  const paths = getExternalDatasetPaths(dataset, centerId);
  if (!center || !paths) return [];
  return buildCenterPatients(center.id, center.label, paths, 'external', 'Surgery', 'external', dataset, page);
}

function buildBenignPatients(
  centerId: string,
  dataset: DatasetType,
  page?: PatientPageOptions,
): Patient[] {
  const center = BENIGN_CENTER_OPTIONS.find((item) => item.id === centerId);
  const paths = getBenignDatasetPaths(dataset, centerId);
  if (!center || !paths) return [];
  return buildCenterPatients(center.id, center.label, paths, 'benign', 'Benign', 'benign', dataset, page);
}

function buildLegacyGistPatients(dataset: DatasetType): Patient[] {
  const paths = getDatasetPaths(dataset, 'gist', 'surgery');
  const clinicalDataPath = getClinicalDataPath('gist', 'surgery');
  if (!paths.images || !fs.existsSync(paths.images)) return [];

  let clinicalData: Record<string, unknown> = {};
  if (clinicalDataPath && fs.existsSync(clinicalDataPath)) {
    clinicalData = JSON.parse(fs.readFileSync(clinicalDataPath, 'utf-8')) as Record<string, unknown>;
  }

  const files = fs.readdirSync(paths.images).filter(file => file.toLowerCase().endsWith('.jpg') && file.startsWith('GIST_'));
  return files.map((filename) => {
    const encodedFilename = encodeURIComponent(filename);
    const jsonFilename = filename.replace(/\.jpg$/i, '.json');
    const overlayFilename = filename.replace(/\.jpg$/i, '_overlay.jpg');
    const patientId = filename.split('_')[2] || filename.replace(/\.jpg$/i, '');
    const clinicalEntry = clinicalData[patientId] as Record<string, unknown> | undefined;
    const report = toPublicReport(clinicalEntry);
    const clinical = clinicalEntry
      ? {
          age: parseNullableNumber(clinicalEntry.age),
          sex: normalizeSex(clinicalEntry.sex),
          tumorSize: { length: null, thickness: null },
          location: 'GIST',
          biomarkers: {
            cea: null,
            ca199: null,
            cea_positive: false,
            ca199_positive: false,
          },
        }
      : undefined;

    return {
      id: filename,
      id_short: filename.replace(/\.jpg$/i, ''),
      patient_id: patientId,
      group: 'Surgery',
      phase: 'gist',
      source_label: 'legacy-gist',
      queue_id: 'legacy:gist',
      frame_count: 1,
      image_url: `/api/images/${dataset}/images/${encodedFilename}?cohort=gist&treatment=surgery`,
      overlay_url: `/api/images/${dataset}/overlays/${encodeURIComponent(overlayFilename)}?cohort=gist&treatment=surgery`,
      overlay_transparent_url: '',
      roi_url: '',
      json_url: `/api/images/original/annotations/${encodeURIComponent(jsonFilename)}?cohort=gist&treatment=surgery`,
      segmentation: {
        source: 'legacy-gist',
        has_annotation: fs.existsSync(path.join(paths.annotations, jsonFilename)),
        has_overlay: fs.existsSync(path.join(paths.overlays, overlayFilename)),
        has_roi: false,
        annotation_count: 0,
        frame_count: 1,
      },
      agent_report: {
        schema_version: '0.1.0',
        case_token: `legacy-gist-${patientId}`,
        data_source: 'legacy-gist',
        frame_count: 1,
        report_status: 'draft',
        image_quality: { status: 'pending', summary: 'Legacy GIST demo case.' },
        segmentation: { status: 'partial', summary: 'Legacy GIST assets are mounted through the archived viewer path.' },
        classification: { status: 'placeholder', summary: 'Agent classifier not wired for legacy GIST cases.' },
        similar_case_support: { status: 'pending', summary: 'Case-memory retrieval is pending.' },
        manual_review_recommended: true,
      },
      clinical,
      report,
    };
  });
}

function redactResearchPatient(patient: Patient): Patient {
  return {
    ...patient,
    clinical: patient.clinical
      ? {
          ...patient.clinical,
          differentiation: '',
          lauren: '',
        }
      : undefined,
    report: patient.report
      ? {
          ...patient.report,
          pathology_report: undefined,
        }
      : undefined,
  };
}

function buildReaderStudyV150Patients(readerId?: string): { patients: Patient[]; orderApplied: boolean } {
  const bundle = loadReaderCasesBundle();
  const patients: Patient[] = (bundle.cases || [])
    .filter((item) => item.has_video !== false)
    .map((item) => {
      const frames = (item.frames || []).filter((frame) => Boolean(frame.video_rel));
      const videoUrls = frames.map((frame, index) => ({
        url: readerMediaUrl(frame.video_rel || ''),
        filename: `${item.case_id}_${index + 1}.mp4`,
        treatment: 'reader_study' as const,
        water_filled: false,
      }));
      const clinical = clinicalFromReaderUsTable(item);
      return {
        id: item.case_id,
        id_short: item.display_id || item.case_id,
        patient_id: item.case_id,
        group: 'Reader Baseline',
        phase: 'reader_v150',
        frame_count: frames.length,
        source_label: 'reader_study_v150_round1',
        queue_id: 'reader:reader_v150',
        study_mode: item.study_mode === 'benign_malignancy' ? 'benign_malignancy' : 't_staging',
        image_url: '',
        overlay_url: '',
        overlay_transparent_url: '',
        roi_url: '',
        json_url: '',
        video_urls: videoUrls,
        segmentation: {
          source: 'reader_study_v150_round1',
          has_annotation: false,
          has_overlay: false,
          has_roi: false,
          annotation_count: 0,
          frame_count: frames.length,
        },
        agent_report: {
          schema_version: 'reader_study_v150',
          case_token: `reader-v150-${item.case_id}`,
          data_source: 'reader_study_v150_round1',
          frame_count: frames.length,
          report_status: 'draft',
          image_quality: { status: 'pending', summary: 'Use the interactive Reader video workflow.' },
          segmentation: { status: 'missing', summary: 'Segmentation is created interactively in Reader.' },
          classification: { status: 'pending', summary: 'Do not run the year-cohort Agent path for this queue.' },
          similar_case_support: { status: 'pending', summary: 'Reference queue; launch Reader Agent for analysis.' },
          manual_review_recommended: true,
        },
        clinical,
      };
    });
  const sorted = sortReaderRound2Patients(patients, readerId);
  return { patients: sorted.patients, orderApplied: sorted.orderApplied };
}

function mergeUniquePatients(patients: Patient[]): Patient[] {
  const seen = new Set<string>();
  return patients.map((patient) => {
    if (!seen.has(patient.id)) {
      seen.add(patient.id);
      return patient;
    }
    const nextId = `${patient.queue_id || patient.phase}::${patient.id}`;
    seen.add(nextId);
    return { ...patient, id: nextId };
  });
}

function createInternalQueueSource(
  year: Exclude<CohortYear, 'gist' | 'reader_v150'>,
  treatmentType: TreatmentType,
  dataset: DatasetType,
): PatientQueueSource {
  const paths = getDatasetPaths(dataset, year, treatmentType);
  const count = readImageFiles(paths.images).length;
  return {
    count,
    build: (offset, limit) => buildCurrentPatients(year, treatmentType, dataset, { offset, limit }),
  };
}

function createExternalQueueSource(centerId: string, dataset: DatasetType): PatientQueueSource {
  const paths = getExternalDatasetPaths(dataset, centerId);
  const count = paths ? readImageFiles(paths.images).length : 0;
  return {
    count,
    build: (offset, limit) => buildExternalPatients(centerId, dataset, { offset, limit }),
  };
}

function createBenignQueueSource(centerId: string, dataset: DatasetType): PatientQueueSource {
  const paths = getBenignDatasetPaths(dataset, centerId);
  const count = paths ? readImageFiles(paths.images).length : 0;
  return {
    count,
    build: (offset, limit) => buildBenignPatients(centerId, dataset, { offset, limit }),
  };
}

function getQueueSources(
  queueId: WorkbenchQueueId,
  treatmentType: TreatmentType,
  dataset: DatasetType,
): PatientQueueSource[] {
  const internalSources = GASTRIC_COHORT_YEARS.map((year) => (
    createInternalQueueSource(year, treatmentType, dataset)
  ));
  const externalSources = EXTERNAL_CENTER_OPTIONS.map((center) => (
    createExternalQueueSource(center.id, dataset)
  ));
  const benignSources = BENIGN_CENTER_OPTIONS.map((center) => (
    createBenignQueueSource(center.id, dataset)
  ));

  if (queueId === 'all') {
    return treatmentType === 'surgery'
      ? [...internalSources, ...externalSources]
      : internalSources;
  }
  if (queueId === 'internal:all') return internalSources;
  if (queueId === 'external:all') {
    return treatmentType === 'surgery' ? externalSources : [];
  }
  if (queueId === 'benign:all') return benignSources;
  if (queueId.startsWith('internal:')) {
    const year = queueId.slice('internal:'.length) as Exclude<CohortYear, 'gist' | 'reader_v150'>;
    return treatmentType === 'surgery' || treatmentType === 'nac'
      ? [createInternalQueueSource(year, treatmentType, dataset)]
      : [];
  }
  if (queueId.startsWith('external:')) {
    const centerId = queueId.slice('external:'.length);
    return treatmentType === 'surgery' ? [createExternalQueueSource(centerId, dataset)] : [];
  }
  if (queueId.startsWith('benign:')) {
    const centerId = queueId.slice('benign:'.length);
    return [createBenignQueueSource(centerId, dataset)];
  }
  return [];
}

function buildQueuePatientsPage(
  queueId: WorkbenchQueueId,
  treatmentType: TreatmentType,
  dataset: DatasetType,
  offset: number,
  limit: number,
  readerId?: string,
): { items: Patient[]; total: number; orderApplied: boolean } {
  if (queueId === 'reader:reader_v150') {
    if (treatmentType !== 'surgery') {
      return { items: [], total: 0, orderApplied: false };
    }
    const built = buildReaderStudyV150Patients(readerId);
    return {
      items: built.patients.slice(offset, offset + limit),
      total: built.patients.length,
      orderApplied: built.orderApplied,
    };
  }
  if (queueId === 'legacy:gist') {
    const all = treatmentType === 'surgery' ? buildLegacyGistPatients(dataset) : [];
    return { items: all.slice(offset, offset + limit), total: all.length, orderApplied: false };
  }

  const sources = getQueueSources(queueId, treatmentType, dataset);
  const total = sources.reduce((sum, source) => sum + source.count, 0);
  let skip = Math.max(0, offset);
  let remaining = Math.max(1, limit);
  const items: Patient[] = [];

  for (const source of sources) {
    if (skip >= source.count) {
      skip -= source.count;
      continue;
    }
    const localLimit = Math.min(remaining, source.count - skip);
    items.push(...source.build(skip, localLimit));
    remaining -= localLimit;
    skip = 0;
    if (remaining <= 0) break;
  }

  return { items: mergeUniquePatients(items), total, orderApplied: false };
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const publicReaderOnly = process.env.NEXT_PUBLIC_READER_ONLY === '1';
    const datasetParam = searchParams.get('dataset');
    const cohortYearParam = searchParams.get('cohort') || '2025';
    const treatmentTypeParam = searchParams.get('treatment') || 'surgery';
    const queueParam = searchParams.get('queue');
    const environment = searchParams.get('environment') || 'staging';
    const requestedReaderId = searchParams.get('reader_id') || '';
    const dataset = parseDatasetType(datasetParam);
    const treatmentType: TreatmentType = treatmentTypeParam === 'nac' ? 'nac' : 'surgery';
    let readerId = requestedReaderId || undefined;

    if (environment === 'research') {
      const auth = resolveResearchReader(request.headers, requestedReaderId);
      if (!auth.ok) {
        return NextResponse.json(
          { ok: false, error: auth.message, code: `research_auth_${auth.code}` },
          { status: auth.code === 'invalid_identity' ? 403 : 401 },
        );
      }
      readerId = auth.readerId;
      const queueId = 'reader:reader_v150';
      if (queueParam && parseWorkbenchQueueId(queueParam) !== queueId) {
        return NextResponse.json(
          {
            ok: false,
            error: 'research environment only allows queue=reader:reader_v150',
            code: 'research_queue_locked',
          },
          { status: 422 },
        );
      }
      if (treatmentType !== 'surgery') {
        return NextResponse.json(
          {
            ok: false,
            error: 'research environment only allows surgery treatment queue',
            code: 'research_treatment_locked',
          },
          { status: 422 },
        );
      }
      const rawOffset = Number.parseInt(searchParams.get('offset') || '0', 10);
      const rawLimit = Number.parseInt(searchParams.get('limit') || '80', 10);
      const offset = Number.isFinite(rawOffset) ? Math.max(0, rawOffset) : 0;
      const limit = Number.isFinite(rawLimit) ? Math.min(200, Math.max(1, rawLimit)) : 80;
      const page = buildQueuePatientsPage(queueId, treatmentType, dataset, offset, limit, readerId);
      if (!page.orderApplied) {
        return NextResponse.json(
          {
            ok: false,
            error: `No frozen Round2 case order for reader ${readerId}`,
            code: 'research_order_missing',
          },
          { status: 422 },
        );
      }
      return NextResponse.json({
        items: page.items.map(redactResearchPatient),
        total: page.total,
        offset,
        limit,
        has_more: offset + page.items.length < page.total,
        study_contract: {
          freeze_id: READER_ROUND2_FREEZE_ID,
          order_seed: READER_ROUND2_ORDER_SEED,
          order_applied: true,
          environment: 'research',
          pathology_hidden: true,
          queue_id: queueId,
          authenticated_reader_id: readerId,
        },
      });
    }

    if (queueParam || publicReaderOnly) {
      const queueId = publicReaderOnly
        ? 'reader:reader_v150'
        : parseWorkbenchQueueId(queueParam);
      const rawOffset = Number.parseInt(searchParams.get('offset') || '0', 10);
      const rawLimit = Number.parseInt(searchParams.get('limit') || '80', 10);
      const offset = Number.isFinite(rawOffset) ? Math.max(0, rawOffset) : 0;
      const limit = Number.isFinite(rawLimit) ? Math.min(200, Math.max(1, rawLimit)) : 80;
      const page = buildQueuePatientsPage(queueId, treatmentType, dataset, offset, limit, readerId);
      return NextResponse.json({
        items: page.items,
        total: page.total,
        offset,
        limit,
        has_more: offset + page.items.length < page.total,
        study_contract: queueId === 'reader:reader_v150'
          ? {
              freeze_id: READER_ROUND2_FREEZE_ID,
              order_seed: READER_ROUND2_ORDER_SEED,
              order_applied: page.orderApplied,
              environment,
            }
          : undefined,
      });
    }

    if (publicReaderOnly || cohortYearParam === 'reader_v150' || cohortYearParam === 'reader-v150') {
      return NextResponse.json(buildReaderStudyV150Patients(readerId).patients);
    }
    const cohortYear = parseCohortYear(cohortYearParam);

    if (cohortYear === 'gist') {
      return NextResponse.json(buildLegacyGistPatients(dataset));
    }

    return NextResponse.json(buildCurrentPatients(cohortYear, treatmentType, dataset));
  } catch (error) {
    console.error("Error reading patients:", error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
