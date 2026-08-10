'use client';

import React, { useState } from 'react';
import {
  Brain, ChevronDown, ChevronUp, LayoutGrid, ScanSearch, Sparkles,
} from 'lucide-react';
import type { Patient } from '@/types';
import { getDirectionAnnotatorPath } from '@/lib/annotator-url';
import { navigateTo } from '@/lib/navigation';
import { buildReaderAppUrl } from '@/lib/reading-agent-url';
import { useSettings } from '@/contexts/SettingsContext';

interface AssistHubProps {
  patient: Patient | null;
}

/** Additive discovery panel — does not replace Header buttons. */
export function AssistHub({ patient }: AssistHubProps) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const [open, setOpen] = useState(false);

  const hasPatient = Boolean(patient?.id);

  const focusAgent = () => {
    window.dispatchEvent(new CustomEvent('gastric:open-full-report'));
  };

  return (
    <div
      className="pointer-events-auto absolute left-3 z-30 w-[min(280px,calc(100%-1.5rem))]"
      style={{ top: '7rem' }}
    >
      <div className="rounded-xl border border-white/10 bg-black/75 shadow-xl backdrop-blur">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
          title={zh ? '辅助中心（新增入口；顶栏按钮仍可用）' : 'Assist hub (extra entry; header buttons still work)'}
        >
          <span className="inline-flex items-center gap-2 text-[11px] font-semibold text-cyan-200">
            <LayoutGrid size={13} />
            {zh ? '辅助中心' : 'Assist hub'}
          </span>
          {open ? <ChevronUp size={13} className="text-gray-500" /> : <ChevronDown size={13} className="text-gray-500" />}
        </button>

        {open ? (
          <div className="space-y-1 border-t border-white/5 px-2 pb-2 pt-1">
            {!hasPatient ? (
              <div className="px-1 py-1.5 text-[10px] text-gray-500">
                {zh
                  ? '先选左侧病例，再使用当前例辅助；顶栏按钮仍可随时打开各工具。'
                  : 'Select a case on the left first. Header buttons remain available anytime.'}
              </div>
            ) : (
              <div className="px-1 pb-1 text-[10px] text-gray-500 truncate" title={patient?.id_short || patient?.id}>
                {zh ? '当前：' : 'Current: '}{patient?.id_short || patient?.patient_id || patient?.id}
              </div>
            )}

            <HubBtn
              icon={<ScanSearch size={12} />}
              label={zh ? '阅片辅助 /reader' : 'Reader assist /reader'}
              hint={zh ? '系统分析 + 分层 + 报告' : 'Analysis + layers + report'}
              tone="emerald"
              disabled={!hasPatient}
              onClick={() => navigateTo(buildReaderAppUrl(patient))}
            />
            <HubBtn
              icon={<Sparkles size={12} />}
              label={zh ? '辅助分析' : 'Assisted analysis'}
              hint={zh ? '打开完整报告中的分析' : 'Open analysis in the full report'}
              tone="sky"
              disabled={!hasPatient}
              onClick={focusAgent}
            />
            <HubBtn
              icon={<Brain size={12} />}
              label={zh ? '方向标注' : 'Direction annotation'}
              hint="/annotate"
              tone="amber"
              onClick={() => navigateTo(getDirectionAnnotatorPath())}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function HubBtn({
  icon,
  label,
  hint,
  tone,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  hint: string;
  tone: 'emerald' | 'cyan' | 'sky' | 'orange' | 'amber' | 'violet' | 'slate';
  onClick: () => void;
  disabled?: boolean;
}) {
  const toneCls: Record<string, string> = {
    emerald: 'border-emerald-500/35 bg-emerald-500/15 text-emerald-200 hover:border-emerald-400/50 hover:bg-emerald-500/25',
    cyan: 'border-cyan-500/35 bg-cyan-500/15 text-cyan-200 hover:border-cyan-400/50 hover:bg-cyan-500/25',
    sky: 'border-sky-500/35 bg-sky-500/15 text-sky-200 hover:border-sky-400/50 hover:bg-sky-500/25',
    orange: 'border-orange-500/35 bg-orange-500/15 text-orange-200 hover:border-orange-400/50 hover:bg-orange-500/25',
    amber: 'border-amber-500/35 bg-amber-500/15 text-amber-200 hover:border-amber-400/50 hover:bg-amber-500/25',
    violet: 'border-violet-500/35 bg-violet-500/15 text-violet-200 hover:border-violet-400/50 hover:bg-violet-500/25',
    slate: 'border-white/15 bg-white/[0.06] text-gray-200 hover:border-white/25 hover:bg-white/10',
  };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-lg border px-2 py-1.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${toneCls[tone]}`}
    >
      <span className="shrink-0 opacity-90">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-semibold leading-tight">{label}</span>
        <span className="block text-[9px] opacity-70">{hint}</span>
      </span>
    </button>
  );
}
