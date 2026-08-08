'use client';

import React from 'react';
import type { ReaderCohort } from '@/lib/reader/types';

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

const COHORTS: { id: ReaderCohort; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'benign_malignancy', label: '良恶性' },
  { id: 't_staging', label: 'T分期' },
];

export function ReaderCaseSidebar({
  cohort,
  onCohortChange,
  cases,
  selectedCaseId,
  onSelectCase,
  loading,
}: Props) {
  return (
    <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-white/10 bg-[#0c0d0f]">
      <div className="border-b border-white/10 p-3">
        <div className="text-xs font-semibold text-gray-200">病例库</div>
        <p className="mt-1 text-[10px] leading-relaxed text-gray-500">
          阅片包 150 例：良恶性 50 + T 分期 100。点击/框选生成 mask 与报告。
        </p>
        <div className="mt-2 flex flex-wrap gap-1">
          {COHORTS.map((c) => (
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
          {loading ? '加载中…' : `${cases.length} 例`}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {cases.map((item) => {
          const active = item.case_id === selectedCaseId;
          const tag =
            item.study_mode === 'benign_malignancy'
              ? item.reference_lesion_nature === 'malignant'
                ? '恶性'
                : '良性'
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
