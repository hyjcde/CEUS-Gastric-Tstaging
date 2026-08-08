import fs from 'fs';
import path from 'path';
import {
  CohortYear,
  GastricCohortYear,
  DatasetType,
  TreatmentType,
  getBenignCenterById,
  getExternalCenterById,
} from '@/lib/cohort';

export type { CohortYear, GastricCohortYear, ReaderStudyQueue, DatasetType, TreatmentType } from '@/lib/cohort';
export {
  ALL_COHORT_YEARS,
  GASTRIC_COHORT_YEARS,
  READER_STUDY_QUEUES,
  DEFAULT_DATASET,
  getCohortDisplayLabel,
  parseCohortYear,
  parseDatasetType,
} from '@/lib/cohort';

const PROJECT_ROOT_ENV_KEYS = [
  'GASTRIC_ROOT',
  'GASTRIC_TSTAGING_ROOT',
  'GASTRIC_PROJECT_ROOT',
] as const;

function resolveExistingPath(...candidates: Array<string | undefined>): string | null {
  for (const candidate of candidates) {
    if (!candidate) continue;
    const resolved = path.resolve(candidate);
    if (fs.existsSync(resolved)) {
      return resolved;
    }
  }
  return null;
}

function findProjectRoot(startDir: string): string {
  const envRoot = resolveExistingPath(...PROJECT_ROOT_ENV_KEYS.map((key) => process.env[key]));
  if (envRoot) {
    return envRoot;
  }

  let current = path.resolve(startDir);
  while (true) {
    if (fs.existsSync(path.join(current, 'dataset')) && fs.existsSync(path.join(current, 'apps'))) {
      return current;
    }

    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }

  return path.resolve(startDir, '..', '..');
}

export const APP_ROOT = process.cwd();
export const PROJECT_ROOT = findProjectRoot(APP_ROOT);
export const CURRENT_DATASET_ROOT = resolveExistingPath(process.env.GASTRIC_DATASET_ROOT, path.join(PROJECT_ROOT, 'dataset')) || path.join(PROJECT_ROOT, 'dataset');
export const CURRENT_INTERNAL_ROOT = path.join(CURRENT_DATASET_ROOT, 'internal');
export const TRAINING_2018_2024_ROOT = path.join(CURRENT_INTERNAL_ROOT, 'training_2018_2024');
export const CURRENT_2025_ROOT = path.join(CURRENT_INTERNAL_ROOT, 'prospective_2025', '2025');
export const CURRENT_2024_ROOT = path.join(TRAINING_2018_2024_ROOT, '2024');
export const CURRENT_2020_2023_ROOT = path.join(TRAINING_2018_2024_ROOT, '2020_2023');
export const CURRENT_2019_ROOT = path.join(TRAINING_2018_2024_ROOT, '2019');
export const CURRENT_2018_ROOT = path.join(TRAINING_2018_2024_ROOT, '2018');

// Legacy dataset roots kept as optional fallback for older GIST demos.
export const LEGACY_DATASET_ORIGINAL_ROOT = resolveExistingPath(
  process.env.GASTRIC_LEGACY_2025_ORIGINAL_ROOT,
  path.join(PROJECT_ROOT, 'Gastric_Cancer_Dataset_2025'),
  path.resolve(APP_ROOT, '../../Gastric_Cancer_Dataset_2025'),
) || path.join(PROJECT_ROOT, 'Gastric_Cancer_Dataset_2025');
export const LEGACY_DATASET_CROPPED_ROOT = resolveExistingPath(
  process.env.GASTRIC_LEGACY_2025_CROPPED_ROOT,
  path.join(PROJECT_ROOT, 'Gastric_Cancer_Dataset_2025_Cropped'),
  path.resolve(APP_ROOT, '../../Gastric_Cancer_Dataset_2025_Cropped'),
) || path.join(PROJECT_ROOT, 'Gastric_Cancer_Dataset_2025_Cropped');
export const LEGACY_DATASET_2019_CROPPED_ROOT = resolveExistingPath(
  process.env.GASTRIC_LEGACY_GIST_CROPPED_ROOT,
  path.join(PROJECT_ROOT, 'GIST_Dataset_2025_Cropped'),
  path.resolve(APP_ROOT, '../../GIST_Dataset_2025_Cropped'),
) || path.join(PROJECT_ROOT, 'GIST_Dataset_2025_Cropped');
export const LEGACY_DATASET_2024_CROPPED_ROOT = resolveExistingPath(
  process.env.GASTRIC_LEGACY_2024_CROPPED_ROOT,
  path.join(PROJECT_ROOT, 'Gastric_Cancer_Dataset_2024_Cropped'),
  path.resolve(APP_ROOT, '../../Gastric_Cancer_Dataset_2024_Cropped'),
) || path.join(PROJECT_ROOT, 'Gastric_Cancer_Dataset_2024_Cropped');
export const LEGACY_DATASET_2019_ROOT = resolveExistingPath(
  process.env.GASTRIC_LEGACY_GIST_ROOT,
  path.join(PROJECT_ROOT, 'GIST_Dataset_2025'),
  path.resolve(APP_ROOT, '../../GIST_Dataset_2025'),
) || path.join(PROJECT_ROOT, 'GIST_Dataset_2025');

function getCurrentCohortRoot(cohortYear: GastricCohortYear): string {
  switch (cohortYear) {
    case '2018':
      return CURRENT_2018_ROOT;
    case '2019':
      return CURRENT_2019_ROOT;
    case '2020_2023':
      return CURRENT_2020_2023_ROOT;
    case '2024':
      return CURRENT_2024_ROOT;
    default:
      return CURRENT_2025_ROOT;
  }
}

export function getDatasetPaths(dataset: DatasetType, cohortYear: CohortYear = '2025', treatmentType: TreatmentType = 'surgery') {
  if (cohortYear === 'reader_v150') return getDatasetPaths(dataset, '2025', treatmentType);
  if (cohortYear !== 'gist') {
    const cohortRoot = getCurrentCohortRoot(cohortYear);
    const originalRoot = path.join(cohortRoot, 'original');
    const cropUiRoot = path.join(cohortRoot, 'crop_ui');
    const cropRoiRoot = path.join(cohortRoot, 'crop_roi');

    return {
      root: dataset === 'cropped' ? cropUiRoot : originalRoot,
      // cropped 模式展示 crop_ui（去界面边框）；crop_roi 仅作紧框 ROI 预览
      images: dataset === 'cropped' ? path.join(cropUiRoot, 'images') : path.join(originalRoot, 'images'),
      cropUi: path.join(cropUiRoot, 'images'),
      overlays: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'overlays'),
      overlaysTransparent: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'overlays'),
      annotations: path.join(originalRoot, 'annotations'),
      roi: path.join(cropRoiRoot, 'images'),
    };
  }

  const root = dataset === 'cropped'
    ? LEGACY_DATASET_2019_CROPPED_ROOT
    : LEGACY_DATASET_2019_ROOT;
  return {
    root,
    images: path.join(root, 'images'),
    overlays: path.join(root, 'overlays'),
    overlaysTransparent: path.join(root, 'lymph_node_analysis'),
    annotations: path.join(root, 'annotations'),
    roi: path.join(root, 'images'),
  };
}

export function getExternalDatasetPaths(dataset: DatasetType, centerId: string) {
  const center = getExternalCenterById(centerId);
  if (!center) return null;

  const centerRoot = path.join(CURRENT_DATASET_ROOT, 'external', center.folderName);
  const originalRoot = path.join(centerRoot, 'original');
  const cropUiRoot = path.join(centerRoot, 'crop_ui');
  const cropRoiRoot = path.join(centerRoot, 'crop_roi');

  return {
    root: dataset === 'cropped' ? cropUiRoot : originalRoot,
    images: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'images'),
    overlays: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'overlays'),
    overlaysTransparent: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'overlays'),
    annotations: path.join(originalRoot, 'annotations'),
    roi: path.join(cropRoiRoot, 'images'),
  };
}

export function getBenignDatasetPaths(dataset: DatasetType, centerId: string) {
  const center = getBenignCenterById(centerId);
  if (!center) return null;

  const centerRoot = path.join(CURRENT_DATASET_ROOT, 'gastritis_external', 'processed_images', center.folderName);
  const originalRoot = path.join(centerRoot, 'original');
  const cropUiRoot = path.join(centerRoot, 'crop_ui');
  const cropRoiRoot = path.join(centerRoot, 'crop_roi');

  return {
    root: dataset === 'cropped' ? cropUiRoot : originalRoot,
    images: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'images'),
    overlays: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'overlays'),
    overlaysTransparent: path.join(dataset === 'cropped' ? cropUiRoot : originalRoot, 'overlays'),
    annotations: path.join(originalRoot, 'annotations'),
    roi: path.join(cropRoiRoot, 'images'),
  };
}

export function getClinicalDataPath(cohortYear: CohortYear = '2025', treatmentType: TreatmentType = 'surgery'): string {
  if (cohortYear === 'reader_v150') return getClinicalDataPath('2025', treatmentType);
  if (cohortYear === 'gist') {
    return path.join(APP_ROOT, 'data', 'clinical_data_gist.json');
  }

  const suffix = treatmentType === 'nac' ? '_nac' : '';
  const yearToken = cohortYear === '2020_2023' ? '2020_2023' : cohortYear;

  const candidates = [
    path.join(APP_ROOT, 'data', `clinical_data_${yearToken}_ultimate.json`),
    path.join(APP_ROOT, 'data', `clinical_data_${yearToken}_super.json`),
    path.join(APP_ROOT, 'data', `clinical_data_${yearToken}_enhanced.json`),
    path.join(APP_ROOT, 'data', `clinical_data_${yearToken}${suffix}.json`),
    cohortYear === '2025' ? path.join(APP_ROOT, 'data', 'clinical_data_ultimate.json') : null,
    cohortYear === '2025' ? path.join(APP_ROOT, 'data', 'clinical_data.json') : null,
    path.join(APP_ROOT, 'data', `clinical_data${suffix}.json`),
  ].filter((candidate): candidate is string => Boolean(candidate));

  return resolveExistingPath(...candidates) || candidates[candidates.length - 1];
}

const DICOM_DIR_CANDIDATES: Partial<Record<CohortYear, string[]>> = {
  '2024': [
    path.join(PROJECT_ROOT, 'data', '2024年胃癌直接手术', 'DICOM1+NII1', 'DICOM1'),
    path.join(PROJECT_ROOT, 'archive', '2024年胃癌直接手术', 'DICOM1+NII1', 'DICOM1'),
  ],
  '2019': [
    path.join(PROJECT_ROOT, 'data', '2019年直接手术', 'DICOM'),
  ],
};

export function getDicomDir(cohortYear: CohortYear): string | null {
  const candidates = DICOM_DIR_CANDIDATES[cohortYear];
  if (!candidates) return null;
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}
