export type GastricCohortYear = '2018' | '2019' | '2020_2023' | '2024' | '2025';
export type ReaderStudyQueue = 'reader_v150';
export type CohortYear = GastricCohortYear | ReaderStudyQueue | 'gist';

export type DatasetType = 'original' | 'cropped';
export type TreatmentType = 'surgery' | 'nac';

export type ExternalCenterId =
  | 'putian_college'
  | 'putian_first'
  | 'fujian_tumor'
  | 'sanming_second'
  | 'dehua'
  | 'beijing_friendship'
  | 'foshan_first'
  | 'cnnc_504'
  | 'fujian_provincial';

export interface ExternalCenterOption {
  id: ExternalCenterId;
  label: string;
  folderName: string;
}

export const EXTERNAL_CENTER_OPTIONS: ExternalCenterOption[] = [
  { id: 'putian_college', label: '莆田学院附属医院', folderName: '莆田学院附属医院' },
  { id: 'putian_first', label: '莆田市第一医院', folderName: '莆田市第一医院' },
  { id: 'fujian_tumor', label: '福建省肿瘤医院', folderName: '福建省肿瘤医院' },
  { id: 'sanming_second', label: '三明市第二医院', folderName: '三明市第二医院' },
  { id: 'dehua', label: '福建省德化县医院', folderName: '福建省德化县医院' },
  { id: 'beijing_friendship', label: '北京友谊医院', folderName: '北京友谊医院' },
  { id: 'foshan_first', label: '佛山市第一人民医院', folderName: '佛山市第一人民医院' },
  { id: 'cnnc_504', label: '中核五〇四医院', folderName: '中核五〇四医院' },
  { id: 'fujian_provincial', label: '福建省立医院', folderName: '福建省立医院' },
];

export type BenignCenterId =
  | 'sanming_second'
  | 'cnnc_504'
  | 'ningde'
  | 'dehua'
  | 'fujian_tumor'
  | 'putian_college';

export interface BenignCenterOption {
  id: BenignCenterId;
  label: string;
  folderName: string;
}

export const BENIGN_CENTER_OPTIONS: BenignCenterOption[] = [
  { id: 'sanming_second', label: '三明市第二医院', folderName: '三明市第二医院' },
  { id: 'cnnc_504', label: '中核五〇四医院', folderName: '中核五〇四医院' },
  { id: 'ningde', label: '宁德市医院', folderName: '宁德市医院' },
  { id: 'dehua', label: '福建省德化县医院', folderName: '福建省德化县医院' },
  { id: 'fujian_tumor', label: '福建省肿瘤医院', folderName: '福建省肿瘤医院' },
  { id: 'putian_college', label: '莆田学院附属医院', folderName: '莆田学院附属医院' },
];

export type WorkbenchQueueId =
  | 'all'
  | 'internal:all'
  | `internal:${GastricCohortYear}`
  | 'external:all'
  | `external:${ExternalCenterId}`
  | 'benign:all'
  | `benign:${BenignCenterId}`
  | 'reader:reader_v150'
  | 'legacy:gist';

export interface WorkbenchQueueGroup {
  id: 'internal' | 'external' | 'benign' | 'special';
  label: string;
  children: Array<{ id: WorkbenchQueueId; label: string }>;
}

export const WORKBENCH_QUEUE_GROUPS: WorkbenchQueueGroup[] = [
  {
    id: 'internal',
    label: '内部数据',
    children: [
      { id: 'internal:all', label: '全部内部数据' },
      { id: 'internal:2018', label: '2018' },
      { id: 'internal:2019', label: '2019' },
      { id: 'internal:2020_2023', label: '2020-2023' },
      { id: 'internal:2024', label: '2024' },
      { id: 'internal:2025', label: '2025' },
    ],
  },
  {
    id: 'external',
    label: '外部数据',
    children: [
      { id: 'external:all', label: '全部外部中心' },
      ...EXTERNAL_CENTER_OPTIONS.map((center) => ({
        id: `external:${center.id}` as WorkbenchQueueId,
        label: center.label,
      })),
    ],
  },
  {
    id: 'benign',
    label: '良性队列',
    children: [
      { id: 'benign:all', label: '全部良性队列' },
      ...BENIGN_CENTER_OPTIONS.map((center) => ({
        id: `benign:${center.id}` as WorkbenchQueueId,
        label: center.label,
      })),
    ],
  },
  {
    id: 'special',
    label: '专项队列',
    children: [
      { id: 'reader:reader_v150', label: '阅片任务, 第一轮150例' },
      { id: 'legacy:gist', label: 'GIST历史队列' },
    ],
  },
];

/** 前端与 API 默认展示 crop_ui（去界面边框） */
export const DEFAULT_DATASET: DatasetType = 'cropped';
export const DEFAULT_WORKBENCH_QUEUE: WorkbenchQueueId = 'reader:reader_v150';

import type { Language } from '@/lib/i18n';

type QueueLanguage = Language;

const ENGLISH_CENTER_LABELS: Record<string, string> = {
  putian_college: 'Putian University Affiliated Hospital',
  putian_first: 'Putian First Hospital',
  fujian_tumor: 'Fujian Cancer Hospital',
  sanming_second: 'Sanming Second Hospital',
  dehua: 'Dehua County Hospital',
  beijing_friendship: 'Beijing Friendship Hospital',
  foshan_first: 'Foshan First People’s Hospital',
  cnnc_504: 'CNNC 504 Hospital',
  fujian_provincial: 'Fujian Provincial Hospital',
  ningde: 'Ningde Hospital',
};

export function parseDatasetType(value: string | null | undefined): DatasetType {
  const raw = (value ?? DEFAULT_DATASET).trim().toLowerCase();
  if (raw === 'original') return 'original';
  if (raw === 'cropped' || raw === 'crop_ui' || raw === 'crop-ui') return 'cropped';
  return DEFAULT_DATASET;
}

export const GASTRIC_COHORT_YEARS: GastricCohortYear[] = ['2018', '2019', '2020_2023', '2024', '2025'];
export const READER_STUDY_QUEUES: ReaderStudyQueue[] = ['reader_v150'];
export const ALL_COHORT_YEARS: CohortYear[] = [...GASTRIC_COHORT_YEARS, ...READER_STUDY_QUEUES, 'gist'];

export function parseWorkbenchQueueId(value: string | null | undefined): WorkbenchQueueId {
  const raw = (value ?? DEFAULT_WORKBENCH_QUEUE).trim();
  if (raw === 'all' || raw === 'internal:all' || raw === 'external:all' || raw === 'benign:all' || raw === 'reader:reader_v150' || raw === 'legacy:gist') {
    return raw;
  }
  if (raw.startsWith('internal:') && GASTRIC_COHORT_YEARS.includes(raw.slice('internal:'.length) as GastricCohortYear)) {
    return raw as WorkbenchQueueId;
  }
  if (raw.startsWith('external:') && EXTERNAL_CENTER_OPTIONS.some((center) => `external:${center.id}` === raw)) {
    return raw as WorkbenchQueueId;
  }
  if (raw.startsWith('benign:') && BENIGN_CENTER_OPTIONS.some((center) => `benign:${center.id}` === raw)) {
    return raw as WorkbenchQueueId;
  }
  return DEFAULT_WORKBENCH_QUEUE;
}

export function getExternalCenterById(id: string | null | undefined): ExternalCenterOption | undefined {
  return EXTERNAL_CENTER_OPTIONS.find((center) => center.id === id);
}

export function getBenignCenterById(id: string | null | undefined): BenignCenterOption | undefined {
  return BENIGN_CENTER_OPTIONS.find((center) => center.id === id);
}

export function getQueueDisplayLabel(queueId: WorkbenchQueueId, language: QueueLanguage = 'zh'): string {
  if (language === 'en') {
    if (queueId === 'all') return 'All T-staging data';
    if (queueId === 'internal:all') return 'Internal data · All years';
    if (queueId.startsWith('internal:')) {
      return `Internal data · ${getCohortDisplayLabel(queueId.slice('internal:'.length) as GastricCohortYear)}`;
    }
    if (queueId === 'external:all') return 'External data · All centers';
    if (queueId.startsWith('external:')) {
      const centerId = queueId.slice('external:'.length);
      return `External data · ${ENGLISH_CENTER_LABELS[centerId] || 'Center'}`;
    }
    if (queueId === 'benign:all') return 'Benign cohort · All centers';
    if (queueId.startsWith('benign:')) {
      const centerId = queueId.slice('benign:'.length);
      return `Benign cohort · ${ENGLISH_CENTER_LABELS[centerId] || 'Center'}`;
    }
    if (queueId === 'legacy:gist') return 'GIST historical cohort';
    return 'Reader task · Round 1 · 150 cases';
  }

  if (queueId === 'all') return '全部 T 分期数据';
  if (queueId === 'internal:all') return '内部数据, 全部年份';
  if (queueId.startsWith('internal:')) {
    return `内部数据, ${getCohortDisplayLabel(queueId.slice('internal:'.length) as GastricCohortYear)}`;
  }
  if (queueId === 'external:all') return '外部数据, 全部中心';
  if (queueId.startsWith('external:')) {
    return `外部数据, ${getExternalCenterById(queueId.slice('external:'.length))?.label || '中心'}`;
  }
  if (queueId === 'benign:all') return '良性队列, 全部中心';
  if (queueId.startsWith('benign:')) {
    return `良性队列, ${BENIGN_CENTER_OPTIONS.find((center) => center.id === queueId.slice('benign:'.length))?.label || '中心'}`;
  }
  if (queueId === 'legacy:gist') return 'GIST历史队列';
  return '阅片任务, 第一轮150例';
}

export function getQueueGroupDisplayLabel(
  groupId: WorkbenchQueueGroup['id'],
  language: QueueLanguage = 'zh',
): string {
  if (language === 'en') {
    if (groupId === 'internal') return 'Internal data';
    if (groupId === 'external') return 'External data';
    if (groupId === 'benign') return 'Benign cohorts';
    return 'Study queues';
  }
  return WORKBENCH_QUEUE_GROUPS.find((group) => group.id === groupId)?.label || groupId;
}

export function getQueueOptionDisplayLabel(
  queueId: WorkbenchQueueId,
  language: QueueLanguage = 'zh',
): string {
  if (language !== 'en') {
    if (queueId === 'all') return '全部 T 分期数据';
    if (queueId === 'internal:all') return '全部内部数据';
    if (queueId.startsWith('internal:')) return getCohortDisplayLabel(queueId.slice('internal:'.length) as GastricCohortYear);
    if (queueId === 'external:all') return '全部外部中心';
    if (queueId.startsWith('external:')) {
      return getExternalCenterById(queueId.slice('external:'.length))?.label || '中心';
    }
    if (queueId === 'benign:all') return '全部良性队列';
    if (queueId.startsWith('benign:')) {
      return getBenignCenterById(queueId.slice('benign:'.length))?.label || '中心';
    }
    if (queueId === 'legacy:gist') return 'GIST历史队列';
    return '阅片任务, 第一轮150例';
  }

  if (queueId === 'all') return 'All T-staging data';
  if (queueId === 'internal:all') return 'All internal data';
  if (queueId.startsWith('internal:')) return getCohortDisplayLabel(queueId.slice('internal:'.length) as GastricCohortYear);
  if (queueId === 'external:all') return 'All external centers';
  if (queueId.startsWith('external:')) {
    return ENGLISH_CENTER_LABELS[queueId.slice('external:'.length)] || 'Center';
  }
  if (queueId === 'benign:all') return 'All benign cohorts';
  if (queueId.startsWith('benign:')) {
    return ENGLISH_CENTER_LABELS[queueId.slice('benign:'.length)] || 'Center';
  }
  if (queueId === 'legacy:gist') return 'GIST historical cohort';
  return 'Reader task · Round 1 · 150 cases';
}

export function queueToCohortYear(queueId: WorkbenchQueueId): CohortYear {
  if (queueId === 'reader:reader_v150') return 'reader_v150';
  if (queueId === 'legacy:gist') return 'gist';
  if (queueId.startsWith('internal:') && queueId !== 'internal:all') {
    return queueId.slice('internal:'.length) as GastricCohortYear;
  }
  return '2025';
}

export function isInternalQueue(queueId: WorkbenchQueueId): boolean {
  return queueId === 'all' || queueId === 'internal:all' || queueId.startsWith('internal:');
}

export function isExternalQueue(queueId: WorkbenchQueueId): boolean {
  return queueId === 'all' || queueId === 'external:all' || queueId.startsWith('external:');
}

export function isBenignQueue(queueId: WorkbenchQueueId): boolean {
  return queueId === 'benign:all' || queueId.startsWith('benign:');
}

export function parseCohortYear(value: string | null | undefined): CohortYear {
  const raw = (value ?? '2025').trim().toLowerCase();
  if (raw === 'gist') return 'gist';
  if (raw === 'reader_v150' || raw === 'reader-v150' || raw === 'round1_150') return 'reader_v150';
  if (raw === '2018') return '2018';
  if (raw === '2019') return '2019';
  if (raw === '2020_2023' || raw === '2020-2023' || raw === '20-23' || raw === '2020' || raw === '2021' || raw === '2022' || raw === '2023') {
    return '2020_2023';
  }
  if (raw === '2024') return '2024';
  return '2025';
}

export function getCohortDisplayLabel(cohortYear: CohortYear): string {
  if (cohortYear === 'reader_v150') return '第一轮150';
  if (cohortYear === '2020_2023') return '20-23';
  if (cohortYear === 'gist') return 'GIST';
  return cohortYear;
}
