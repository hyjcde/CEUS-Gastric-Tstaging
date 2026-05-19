export type GastricCohortYear = '2018' | '2019' | '2020_2023' | '2024' | '2025';
export type CohortYear = GastricCohortYear | 'gist';

export type DatasetType = 'original' | 'cropped';
export type TreatmentType = 'surgery' | 'nac';

/** 前端与 API 默认展示 crop_ui（去界面边框） */
export const DEFAULT_DATASET: DatasetType = 'cropped';

export function parseDatasetType(value: string | null | undefined): DatasetType {
  const raw = (value ?? DEFAULT_DATASET).trim().toLowerCase();
  if (raw === 'original') return 'original';
  if (raw === 'cropped' || raw === 'crop_ui' || raw === 'crop-ui') return 'cropped';
  return DEFAULT_DATASET;
}

export const GASTRIC_COHORT_YEARS: GastricCohortYear[] = ['2018', '2019', '2020_2023', '2024', '2025'];
export const ALL_COHORT_YEARS: CohortYear[] = [...GASTRIC_COHORT_YEARS, 'gist'];

export function parseCohortYear(value: string | null | undefined): CohortYear {
  const raw = (value ?? '2025').trim().toLowerCase();
  if (raw === 'gist') return 'gist';
  if (raw === '2018') return '2018';
  if (raw === '2019') return '2019';
  if (raw === '2020_2023' || raw === '2020-2023' || raw === '20-23' || raw === '2020' || raw === '2021' || raw === '2022' || raw === '2023') {
    return '2020_2023';
  }
  if (raw === '2024') return '2024';
  return '2025';
}

export function getCohortDisplayLabel(cohortYear: CohortYear): string {
  if (cohortYear === '2020_2023') return '20-23';
  if (cohortYear === 'gist') return 'GIST';
  return cohortYear;
}
