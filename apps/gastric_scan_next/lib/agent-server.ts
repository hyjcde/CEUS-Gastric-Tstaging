import fs from 'fs';
import path from 'path';
import {
  CohortYear,
  DatasetType,
  TreatmentType,
  PROJECT_ROOT,
  getBenignDatasetPaths,
  getDatasetPaths,
  getExternalDatasetPaths,
} from '@/lib/config';
import { Patient } from '@/types';

function decodeFilenameFromUrl(urlValue: string | undefined): string | null {
  if (!urlValue) return null;
  try {
    const parsed = new URL(urlValue, 'http://127.0.0.1');
    const lastSegment = parsed.pathname.split('/').pop();
    return lastSegment ? decodeURIComponent(lastSegment) : null;
  } catch {
    return null;
  }
}

function resolveExistingFile(dir: string, filename: string | null): string | null {
  if (!filename) return null;
  const resolved = path.join(dir, filename);
  return fs.existsSync(resolved) ? resolved : null;
}

export function getPatientDatasetPaths(
  patient: Patient,
  dataset: DatasetType,
  cohortYear: CohortYear,
  treatmentType: TreatmentType,
) {
  const queueId = patient.queue_id || '';
  if (queueId.startsWith('benign:')) {
    return getBenignDatasetPaths(dataset, queueId.slice('benign:'.length)) || getDatasetPaths(dataset, cohortYear, treatmentType);
  }
  if (queueId.startsWith('external:')) {
    return getExternalDatasetPaths(dataset, queueId.slice('external:'.length)) || getDatasetPaths(dataset, cohortYear, treatmentType);
  }
  return getDatasetPaths(dataset, cohortYear, treatmentType);
}

export function mapClinicalToAgentInput(patient: Patient) {
  const clinical = patient.clinical;
  return {
    age: clinical?.age ?? null,
    sex: clinical?.sex ?? '',
    location: clinical?.location ?? '',
    tumorSize: clinical?.tumorSize ?? { length: null, thickness: null },
    biomarkers: clinical?.biomarkers ?? {
      cea: null,
      ca199: null,
      cea_positive: false,
      ca199_positive: false,
    },
    differentiation: clinical?.differentiation ?? '',
    lauren: clinical?.lauren ?? '',
  };
}

export function mapReportToAgentInput(patient: Patient) {
  const report = patient.report;
  return {
    ultrasound_report: report?.ultrasound_report ?? '',
    ultrasound_findings: report?.ultrasound_findings ?? '',
    ultrasound_impression: report?.ultrasound_impression ?? '',
    ct_report: report?.ct_report ?? '',
    ct_findings: report?.ct_findings ?? '',
    ct_impression: report?.ct_impression ?? '',
    enhanced_ct_report: report?.enhanced_ct_report ?? '',
    endoscopy_report: report?.endoscopy_report ?? '',
    pathology_report: report?.pathology_report ?? '',
    report_source: report?.report_source ?? '',
  };
}

function listPatientImageFiles(
  patient: Patient,
  cohortYear: CohortYear,
  treatmentType: TreatmentType,
  dataset: DatasetType,
): string[] {
  const displayPaths = getPatientDatasetPaths(patient, dataset, cohortYear, treatmentType);
  const imageDir = displayPaths.images;
  if (!imageDir || !fs.existsSync(imageDir)) {
    return [];
  }
  const token = patient.patient_id;
  return fs
    .readdirSync(imageDir)
    .filter((file) => !file.startsWith('.') && /\.(jpg|jpeg)$/i.test(file))
    .filter((file) => file.includes(token))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
}

export function resolvePatientFramePaths(
  patient: Patient,
  cohortYear: CohortYear,
  treatmentType: TreatmentType,
  dataset: DatasetType,
  maxFrames = 3,
) {
  const originalPaths = getPatientDatasetPaths(patient, 'original', cohortYear, treatmentType);
  const croppedPaths = getPatientDatasetPaths(patient, 'cropped', cohortYear, treatmentType);
  const filenames = listPatientImageFiles(patient, cohortYear, treatmentType, dataset).slice(0, maxFrames);

  return filenames.map((imageFilename) => {
    const displayPaths = getPatientDatasetPaths(patient, dataset, cohortYear, treatmentType);
    const annotationFilename = imageFilename.replace(/\.(jpg|jpeg)$/i, '.json');
    const overlayFilename = imageFilename.replace(/\.(jpg|jpeg)$/i, '_overlay.jpg');
    return {
      image_path: resolveExistingFile(displayPaths.images, imageFilename),
      roi_path: resolveExistingFile(croppedPaths.roi, imageFilename),
      annotation_path: resolveExistingFile(originalPaths.annotations, annotationFilename),
      overlay_path: resolveExistingFile(originalPaths.overlays, overlayFilename),
    };
  }).filter((frame) => Boolean(frame.image_path));
}

export function resolvePatientAgentPaths(
  patient: Patient,
  cohortYear: CohortYear,
  treatmentType: TreatmentType,
  dataset: DatasetType,
) {
  const originalPaths = getPatientDatasetPaths(patient, 'original', cohortYear, treatmentType);
  const croppedPaths = getPatientDatasetPaths(patient, 'cropped', cohortYear, treatmentType);

  const imageFilename = decodeFilenameFromUrl(patient.image_url) ?? patient.id;
  const roiFilename = decodeFilenameFromUrl(patient.roi_url);
  const annotationFilename = decodeFilenameFromUrl(patient.json_url);
  const overlayFilename = decodeFilenameFromUrl(patient.overlay_url);

  const displayPaths = getPatientDatasetPaths(patient, dataset, cohortYear, treatmentType);
  const imagePath = resolveExistingFile(displayPaths.images, imageFilename);

  return {
    projectRoot: PROJECT_ROOT,
    image_path: imagePath,
    roi_path: resolveExistingFile(croppedPaths.roi, roiFilename ?? imageFilename),
    annotation_path: resolveExistingFile(originalPaths.annotations, annotationFilename),
    overlay_path: resolveExistingFile(originalPaths.overlays, overlayFilename),
  };
}
