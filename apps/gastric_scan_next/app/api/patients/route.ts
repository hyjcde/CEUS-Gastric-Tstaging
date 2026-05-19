import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { DatasetType, CohortYear, TreatmentType, getClinicalDataPath, getDatasetPaths } from '@/lib/config';
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
  roiFilename?: string;
}

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
  if (!clinical) return undefined;
  return {
    differentiation: String(clinical.differentiation ?? ''),
    lauren: String(clinical.lauren_type ?? ''),
  };
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
      concept_features: (clinical.concept_features as ConceptFeatures | undefined) ?? buildConceptFeatures(clinical),
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
      summary: 'Run Agent Workbench analysis to load mask4ch T-staging probabilities (clinical22 + lumen/wall evidence).',
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
  const zMatch = base.match(/(Z\d{7,})/i);
  if (zMatch) {
    return zMatch[1].toUpperCase();
  }

  const numericMatches = base.match(/\d{6,}/g);
  if (!numericMatches?.length) {
    return base;
  }
  return numericMatches[numericMatches.length - 1];
}

function buildCurrentDatasetLabel(cohortYear: CohortYear, treatmentType: TreatmentType): string {
  if (cohortYear === '2025') {
    return treatmentType === 'nac' ? 'internal-2025-nac' : 'internal-2025-surgery';
  }
  if (cohortYear === '2024') {
    return treatmentType === 'nac' ? 'internal-2024-nac' : 'internal-2024-surgery';
  }
  return 'legacy-gist';
}

function readJpgFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter((file) => !file.startsWith('.') && /\.(jpg|jpeg)$/i.test(file))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
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
  return clinicalData[patientId] ?? clinicalData[patientId.replace(/^0+/, '')] ?? clinicalData[patientId.toUpperCase()];
}

function buildCurrentPatients(cohortYear: Exclude<CohortYear, 'gist'>, treatmentType: TreatmentType, dataset: DatasetType): Patient[] {
  if (treatmentType === 'nac') {
    return [];
  }

  const originalPaths = getDatasetPaths('original', cohortYear, treatmentType);
  const croppedPaths = getDatasetPaths('cropped', cohortYear, treatmentType);
  const imageFiles = readJpgFiles(originalPaths.images);
  const clinicalData = readClinicalDataMap(cohortYear, treatmentType);

  const grouped = new Map<string, CurrentDatasetAssets[]>();

  for (const imageFilename of imageFiles) {
    const patientId = extractPatientId(imageFilename);
    const annotationFilename = maybeAnnotationFilename(imageFilename);
    const overlayFilename = maybeOverlayFilename(imageFilename);
    const roiFilename = imageFilename;

    const item: CurrentDatasetAssets = {
      imageFilename,
      annotationFilename: fs.existsSync(path.join(originalPaths.annotations, annotationFilename)) ? annotationFilename : undefined,
      overlayFilename: fs.existsSync(path.join(originalPaths.overlays, overlayFilename)) ? overlayFilename : undefined,
      roiFilename: fs.existsSync(path.join(croppedPaths.roi, roiFilename)) ? roiFilename : undefined,
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
      const imageFilename = dataset === 'cropped' && asset.roiFilename ? asset.roiFilename : asset.imageFilename;
      const primaryImageType = dataset === 'cropped' && asset.roiFilename ? 'roi' : 'images';

      const info: PatientInfo = {
        patient_id: patientId,
        dataset: sourceLabel,
        dataset_type: dataset,
        num_images: sortedAssets.length,
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
        group: 'Surgery',
        phase: cohortYear,
        source_label: sourceLabel,
        frame_count: sortedAssets.length,
        image_url: `/api/images/${dataset}/${primaryImageType}/${encodeURIComponent(imageFilename)}?cohort=${cohortYear}&treatment=${treatmentType}`,
        overlay_url: hasOverlay ? `/api/images/original/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        overlay_transparent_url: hasOverlay ? `/api/images/original/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        roi_url: hasRoi ? `/api/images/cropped/roi/${encodeURIComponent(asset.roiFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        json_url: hasAnnotation ? `/api/images/original/annotations/${encodeURIComponent(asset.annotationFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
        segmentation: {
          source: sourceLabel,
          has_annotation: hasAnnotation,
          has_overlay: hasOverlay,
          has_roi: hasRoi,
          annotation_count: hasAnnotation ? 1 : 0,
          frame_count: sortedAssets.length,
          roi_url: hasRoi ? `/api/images/cropped/roi/${encodeURIComponent(asset.roiFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
          annotation_url: hasAnnotation ? `/api/images/original/annotations/${encodeURIComponent(asset.annotationFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
          overlay_url: hasOverlay ? `/api/images/original/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
          overlay_transparent_url: hasOverlay ? `/api/images/original/overlays/${encodeURIComponent(asset.overlayFilename!)}?cohort=${cohortYear}&treatment=${treatmentType}` : '',
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
      frame_count: 1,
      image_url: `/api/images/${dataset}/images/${encodedFilename}?cohort=gist&treatment=surgery`,
      overlay_url: `/api/images/original/overlays/${encodeURIComponent(overlayFilename)}?cohort=gist&treatment=surgery`,
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

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const datasetParam = searchParams.get('dataset');
    const cohortYearParam = searchParams.get('cohort') || '2025';
    const treatmentTypeParam = searchParams.get('treatment') || 'surgery';
    const dataset: DatasetType = datasetParam === 'cropped' ? 'cropped' : 'original';
    const cohortYear: CohortYear = cohortYearParam === 'gist' ? 'gist' : (cohortYearParam === '2024' ? '2024' : '2025');
    const treatmentType: TreatmentType = treatmentTypeParam === 'nac' ? 'nac' : 'surgery';

    if (cohortYear === 'gist') {
      return NextResponse.json(buildLegacyGistPatients(dataset));
    }

    return NextResponse.json(buildCurrentPatients(cohortYear, treatmentType, dataset));
  } catch (error) {
    console.error("Error reading patients:", error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
