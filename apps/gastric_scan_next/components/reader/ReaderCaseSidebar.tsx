'use client';

import React from 'react';
import type { ReaderCohort } from '@/lib/reader/types';
import { useSettings } from '@/contexts/SettingsContext';

type CaseSummary = {
  case_id: string;
  patient_id?: string;
  display_id?: string;
  study_mode?: string;
  reference_pt?: string;
  reference_lesion_nature?: string;
  frame_count?: number;
};

type Props = {
  cohort: ReaderCohort;
  onCohortChange: (c: ReaderCohort) => void;
  cases: CaseSummary[];
  selectedCaseId: string | null;
  onSelectCase: (caseId: string) => void;
  loading?: boolean;
};

export function ReaderCaseSidebar({
  cohort,
  onCohortChange,
  cases,
  selectedCaseId,
  onSelectCase,
  loading,
}: Props) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const cohorts: { id: ReaderCohort; label: string }[] = [
    { id: 'all', label: zh ? '全部' : 'All' },
    { id: 'benign_malignancy', label: zh ? '良恶性' : 'B/M' },
    { id: 't_staging', label: zh ? 'T分期' : 'T-stage' },
  ];

  return (
    <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-white/10 bg-[#0c0d0f]">
      <div className="border-b border-white/10 p-3">
        <div className="text-xs font-semibold text-gray-200">{zh ? '病例库' : 'Case library'}</div>
        <p className="mt-1 text-[10px] leading-relaxed text-gray-500">
          {zh
            ? '阅片包 150 例：良恶性 50 + T 分期 100。点击/框选生成 mask 与报告。'
            : 'Reader pack 150 cases: 50 B/M + 100 T-staging. Click or box to create a mask and report.'}
        </p>
        <div className="mt-2 flex flex-wrap gap-1">
          {cohorts.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => onCohortChange(c.id)}
              className={`rounded px-2 py-0.5 text-[10px] font-semibold transition-colors ${
                cohort === c.id
                  ? 'bg-emerald-600/90 text-white'
                  : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-200'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="mt-2 text-[10px] text-gray-500">
          {loading
            ? (zh ? '加载中…' : 'Loading…')
            : (zh ? `${cases.length} 例` : `${cases.length} cases`)}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {cases.map((item) => {
          const active = item.case_id === selectedCaseId;
          const tag =
            item.study_mode === 'benign_malignancy'
              ? item.reference_lesion_nature === 'malignant'
                ? (zh ? '恶性' : 'Malignant')
                : (zh ? '良性' : 'Benign')
              : item.reference_pt || 'T?';
          return (
            <button
              key={item.case_id}
              type="button"
              onClick={() => onSelectCase(item.case_id)}
              className={`mb-1 w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                active
                  ? 'border-emerald-500/40 bg-emerald-500/10'
                  : 'border-white/5 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-gray-100">{item.case_id}</span>
                <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-gray-400">{tag}</span>
              </div>
              {item.display_id ? (
                <div className="mt-0.5 text-[10px] text-gray-500">{item.display_id}</div>
              ) : null}
            </button>
          );
        })}
      </div>
    </aside>
  );
}

export type { CaseSummary };
