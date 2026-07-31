'use client';

import React from 'react';
import { Copy, Loader2 } from 'lucide-react';
import type { SamReport } from '@/lib/reader/types';
import { WallFeatureAnalysisCard } from '@/components/WallFeatureAnalysisCard';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';

type Props = {
  report: SamReport | null;
  loading?: boolean;
  samScore?: number | null;
  maskPolygon: number[][] | null;
  frameSize: { width: number; height: number } | null;
  frameDataUrl?: string | null;
  layerPick?: { x: number; y: number } | null;
  onLayerResult?: (r: LayerAnalyzeResult | null) => void;
  onCopy?: () => void;
};

const STAGES = ['T1', 'T2', 'T3', 'T4+'];

function topStage(dist?: Record<string, number>): string {
  if (!dist) return '—';
  let best = STAGES[0];
  let bestV = -1;
  for (const s of STAGES) {
    const v = dist[s] ?? 0;
    if (v > bestV) {
      bestV = v;
      best = s;
    }
  }
  return best;
}

function pickNarrative(report: SamReport | null): string {
  if (!report) return '';
  return report.llm_report?.narrative || report.summary || '';
}

export function ReaderReportPanel({
  report,
  loading,
  samScore,
  maskPolygon,
  frameSize,
  frameDataUrl,
  layerPick,
  onLayerResult,
  onCopy,
}: Props) {
  const stage = report?.recommended_stage || topStage(report?.stage_distribution);
  const conf = report?.calibrated_confidence ?? 0;
  const llmError = report?.llm_report?.error;
  const narrative = pickNarrative(report);

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col border-l border-white/10 bg-[#0c0d0f]">
      <div className="border-b border-white/10 p-3">
        <div className="text-xs font-semibold text-gray-200">Agent 报告</div>
        <div className="mt-2 rounded-xl border border-white/10 bg-gradient-to-br from-emerald-950/40 to-black p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-500">推荐分期</div>
              <div className="text-3xl font-bold text-emerald-300">{loading ? '…' : stage}</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-gray-500">置信</div>
              <div className={`text-sm font-semibold ${conf >= 0.72 ? 'text-emerald-300' : 'text-amber-300'}`}>
                {loading ? '生成中' : `${Math.round(conf * 100)}%`}
              </div>
              {samScore != null ? (
                <div className="mt-1 text-[10px] text-gray-500">分割 {Math.round(samScore * 100)}%</div>
              ) : null}
            </div>
          </div>
          <div className="mt-2 min-h-[72px] text-[11px] leading-relaxed text-gray-300">
            {loading ? (
              <span className="inline-flex items-center gap-2 text-gray-400">
                <Loader2 size={12} className="animate-spin" /> 正在撰写 T 分期文字报告…
              </span>
            ) : llmError && !narrative ? (
              <span className="text-red-300">报告生成失败：{llmError}</span>
            ) : narrative ? (
              narrative.split(/\n+/).map((p, i) => <p key={i} className={i ? 'mt-2' : ''}>{p}</p>)
            ) : (
              <span className="text-gray-500">完成分割后点击「生成文字报告」，或分割后自动更新。</span>
            )}
          </div>
          {narrative && onCopy ? (
            <button type="button" onClick={onCopy} className="reader-btn mt-2 w-full justify-center">
              <Copy size={12} /> 复制报告
            </button>
          ) : null}
        </div>
      </div>

      {report?.stage_distribution ? (
        <div className="border-b border-white/10 p-3">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">分期概率</div>
          <div className="space-y-1.5">
            {STAGES.map((s) => {
              const v = report.stage_distribution?.[s] ?? 0;
              return (
                <div key={s} className="flex items-center gap-2 text-[10px]">
                  <span className="w-8 text-gray-400">{s}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded bg-white/5">
                    <div className="h-full rounded bg-emerald-500/70" style={{ width: `${Math.round(v * 100)}%` }} />
                  </div>
                  <span className="w-8 text-right text-gray-400">{Math.round(v * 100)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        <WallFeatureAnalysisCard
          zh
          lesionPolygon={maskPolygon || []}
          wallPolygon={[]}
          frameSize={frameSize}
          frameDataUrl={frameDataUrl}
          pick={layerPick}
          onResult={onLayerResult}
        />

        {report?.toolchain?.length ? (
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">分析链路</div>
            <div className="space-y-1">
              {report.toolchain.map((step, i) => (
                <div key={step.id || i} className="rounded border border-white/5 bg-white/[0.02] px-2 py-1.5 text-[10px]">
                  <div className="font-medium text-gray-200">{step.title}</div>
                  <div className="text-gray-500">{step.detail}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {report?.evidence?.length ? (
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">证据</div>
            <div className="space-y-1.5">
              {report.evidence.map((ev, i) => (
                <div key={i} className="rounded border border-white/5 bg-white/[0.02] px-2 py-1.5 text-[10px]">
                  <div className="font-medium text-gray-300">{ev.title}</div>
                  <div className="text-gray-500">{ev.detail}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {report?.similar_cases?.length ? (
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">相似病例</div>
            <div className="space-y-1">
              {report.similar_cases.map((sc, i) => (
                <div key={sc.case_id || i} className="flex items-center justify-between rounded border border-white/5 px-2 py-1 text-[10px]">
                  <span className="text-gray-300">{sc.case_id}</span>
                  <span className="text-gray-500">{sc.stage} · {Math.round((sc.score || 0) * 100)}%</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
