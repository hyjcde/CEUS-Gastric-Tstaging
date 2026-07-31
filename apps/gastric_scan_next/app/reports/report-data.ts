import type { Language } from '@/lib/i18n';

export type ReportStatus = 'Finalized' | 'Reviewed' | 'Draft';

export interface Report {
  id: string;
  patient: string;
  date: string;
  stage: string;
  status: ReportStatus;
}

export const statusFilters = ['All', 'Finalized', 'Reviewed', 'Draft'] as const;
export type StatusFilter = (typeof statusFilters)[number];

export const reportData: Report[] = [
  { id: 'RPT-2023-089', patient: '1MC_1424711', date: '2023-11-19', stage: 'T4a', status: 'Finalized' },
  { id: 'RPT-2023-088', patient: '1MC_1410481', date: '2023-11-18', stage: 'T3', status: 'Draft' },
  { id: 'RPT-2023-087', patient: '1MC_1427500', date: '2023-11-18', stage: 'T2', status: 'Finalized' },
  { id: 'RPT-2023-086', patient: '1MC_1452405', date: '2023-11-17', stage: 'T4a', status: 'Finalized' },
  { id: 'RPT-2023-085', patient: '1MC_1430748', date: '2023-11-17', stage: 'T3', status: 'Reviewed' },
];

export const stageBadgeClass = (stage: string) => {
  if (stage.startsWith('T4')) {
    return 'bg-red-500/10 text-red-400 border-red-500/30';
  }
  if (stage.startsWith('T3')) {
    return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
  }
  return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
};

export const statusDotClass = (status: StatusFilter | ReportStatus) => {
  if (status === 'Finalized') return 'bg-blue-500';
  if (status === 'Reviewed') return 'bg-amber-500';
  if (status === 'Draft') return 'bg-gray-500';
  return 'bg-white/30';
};

const baseCounts: Record<ReportStatus, number> = {
  Finalized: 0,
  Reviewed: 0,
  Draft: 0
};

reportData.forEach(report => {
  baseCounts[report.status] += 1;
});

export const statusCounts: Record<StatusFilter, number> = {
  All: reportData.length,
  Finalized: baseCounts.Finalized,
  Reviewed: baseCounts.Reviewed,
  Draft: baseCounts.Draft
};

export const getStatusLabel = (status: StatusFilter | ReportStatus, language: Language) => {
  if (status === 'All') {
    return language === 'zh' ? '全部' : 'All';
  }
  if (status === 'Finalized') {
    return language === 'zh' ? '已完成' : 'Finalized';
  }
  if (status === 'Reviewed') {
    return language === 'zh' ? '待审核' : 'Reviewed';
  }
  return language === 'zh' ? '草稿' : 'Draft';
};

