'use client';

import React, { useMemo, useState } from 'react';
import {
  Brain, ChevronDown, ChevronUp, Clapperboard, Compass, ExternalLink,
  LayoutGrid, Pencil, ScanSearch, Sparkles,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { Patient } from '@/types';
import { getDirectionAnnotatorPath } from '@/lib/annotator-url';
import { getVideoAnnotatorUrl } from '@/lib/video-annotator-url';
import {
  buildHumanAssistUrl,
  buildReaderAppUrl,
  buildReadingAgentUrl,
  getReadingAgentBaseUrl,
} from '@/lib/reading-agent-url';

interface AssistHubProps {
  patient: Patient | null;
}

/** Additive discovery panel — does not replace Header buttons. */
export function AssistHub({ patient }: AssistHubProps) {
  const router = useRouter();
  const [open, setOpen] = useState(true);
  const [showResearch, setShowResearch] = useState(false);

  const base8767 = useMemo(() => getReadingAgentBaseUrl(), []);
  const hasPatient = Boolean(patient?.id);

  const openBoundary = () => {
    window.dispatchEvent(new CustomEvent('gastric:open-boundary-edit', { detail: { sam: true } }));
  };

  const focusAgent = () => {
    window.dispatchEvent(new CustomEvent('gastric:focus-agent'));
  };

  const openExternal = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="pointer-events-auto absolute top-3 left-3 z-30 w-[min(280px,calc(100%-1.5rem))]">
      <div className="rounded-xl border border-white/10 bg-black/75 shadow-xl backdrop-blur">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
          title="辅助中心（新增入口；顶栏按钮仍可用）"
        >
          <span className="inline-flex items-center gap-2 text-[11px] font-semibold text-cyan-200">
            <LayoutGrid size={13} />
            辅助中心
          </span>
          {open ? <ChevronUp size={13} className="text-gray-500" /> : <ChevronDown size={13} className="text-gray-500" />}
        </button>

        {open ? (
          <div className="space-y-1 border-t border-white/5 px-2 pb-2 pt-1">
            {!hasPatient ? (
              <div className="px-1 py-1.5 text-[10px] text-gray-500">
                先选左侧病例，再使用当前例辅助；顶栏按钮仍可随时打开各工具。
              </div>
            ) : (
              <div className="px-1 pb-1 text-[10px] text-gray-500 truncate" title={patient?.id_short || patient?.id}>
                当前：{patient?.id_short || patient?.patient_id || patient?.id}
              </div>
            )}

            <HubBtn
              icon={<ScanSearch size={12} />}
              label="阅片辅助 /reader"
              hint="SAM + 分层 + 报告"
              tone="emerald"
              disabled={!hasPatient}
              onClick={() => router.push(buildReaderAppUrl(patient))}
            />
            <HubBtn
              icon={<Pencil size={12} />}
              label="边界编辑 / SAM"
              hint="同页点选分割 + 精修"
              tone="cyan"
              disabled={!hasPatient}
              onClick={openBoundary}
            />
            <HubBtn
              icon={<Sparkles size={12} />}
              label="跑 Agent"
              hint="聚焦底部启动器"
              tone="sky"
              disabled={!hasPatient}
              onClick={focusAgent}
            />
            <HubBtn
              icon={<Compass size={12} />}
              label="人机互助 HTML"
              hint="direction_demo, 可回写"
              tone="orange"
              onClick={() => openExternal(buildHumanAssistUrl(patient))}
            />
            <HubBtn
              icon={<Brain size={12} />}
              label="方向标注"
              hint="/annotate"
              tone="amber"
              onClick={() => router.push(getDirectionAnnotatorPath())}
            />
            <HubBtn
              icon={<Clapperboard size={12} />}
              label="视频平台"
              hint="需 :3100"
              tone="violet"
              onClick={() => openExternal(getVideoAnnotatorUrl())}
            />
            <HubBtn
              icon={<ExternalLink size={12} />}
              label="HTML 阅片 Agent"
              hint="经典页回退"
              tone="emerald"
              onClick={() => openExternal(buildReadingAgentUrl(patient))}
            />

            <button
              type="button"
              onClick={() => setShowResearch((v) => !v)}
              className="mt-1 flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-[10px] text-gray-400 hover:bg-white/5 hover:text-gray-200"
            >
              <span>研究阅片（盲法，非诊断流）</span>
              {showResearch ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>
            {showResearch ? (
              <div className="space-y-1 pb-1">
                <HubBtn
                  icon={<ExternalLink size={12} />}
                  label="ai_assist 合并入口"
                  hint=":8767 hub"
                  tone="slate"
                  onClick={() => openExternal(`${base8767}/ai_assist.html`)}
                />
                <HubBtn
                  icon={<ExternalLink size={12} />}
                  label="task1 盲法"
                  hint="研究用"
                  tone="slate"
                  onClick={() => openExternal(`${base8767}/task1.html`)}
                />
                <HubBtn
                  icon={<ExternalLink size={12} />}
                  label="video_mask_demo"
                  hint="视频分层 demo"
                  tone="slate"
                  onClick={() => openExternal(`${base8767}/video_mask_demo.html`)}
                />
              </div>
            ) : null}
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
    emerald: 'text-emerald-300 hover:border-emerald-500/40 hover:bg-emerald-500/10',
    cyan: 'text-cyan-300 hover:border-cyan-500/40 hover:bg-cyan-500/10',
    sky: 'text-sky-300 hover:border-sky-500/40 hover:bg-sky-500/10',
    orange: 'text-orange-300 hover:border-orange-500/40 hover:bg-orange-500/10',
    amber: 'text-amber-300 hover:border-amber-500/40 hover:bg-amber-500/10',
    violet: 'text-violet-300 hover:border-violet-500/40 hover:bg-violet-500/10',
    slate: 'text-gray-300 hover:border-white/20 hover:bg-white/5',
  };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-lg border border-transparent px-2 py-1.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${toneCls[tone]}`}
    >
      <span className="shrink-0 opacity-90">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-semibold leading-tight">{label}</span>
        <span className="block text-[9px] text-gray-500">{hint}</span>
      </span>
    </button>
  );
}
