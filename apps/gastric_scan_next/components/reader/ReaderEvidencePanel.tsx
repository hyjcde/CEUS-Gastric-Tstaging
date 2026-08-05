'use client';

import React from 'react';
import { BrainCircuit, ChevronRight, CircleAlert, Database, Dna, FileText, Loader2, ShieldCheck, X } from 'lucide-react';
import type { AgentAnalysisResponse, AgentBeliefAction, AgentBeliefState, AgentEvidenceItem } from '@/types';

type Props = {
  result: AgentAnalysisResponse | null;
  loading?: boolean;
  zh?: boolean;
  onRun?: () => void;
  onNextAction?: (actionType?: string) => void;
};

function valueText(value: unknown): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
function topStage(belief?: AgentBeliefState, fallback?: string): string {
  const stages = belief?.hypotheses
    .filter((item) => /^T[1-4]\+?$/.test(item.label))
    .sort((a, b) => Number(b.probability || 0) - Number(a.probability || 0));
  return stages?.[0]?.label || fallback || 'cTx';
}

function actionLabel(action: AgentBeliefAction | undefined, zh: boolean): string {
  if (!action) return zh ? '等待新的证据' : 'Waiting for new evidence';
  const labels: Record<string, [string, string]> = {
    inspect_conflict_frame: ['定位冲突帧', 'Inspect conflict frame'],
    inspect_next_frame: ['检查下一帧', 'Inspect next frame'],
    run_wall_evidence: ['补充胃壁证据', 'Run wall evidence'],
    run_dino_shadow_evidence: ['运行 DINO 影子证据', 'Run DINO shadow evidence'],
    request_doctor_confirmation: ['请求医生确认', 'Request physician confirmation'],
  };
  const pair = labels[action.action_type];
  return pair ? (zh ? pair[0] : pair[1]) : action.action_type;
}

function EvidenceRow({ item, zh }: { item: AgentEvidenceItem; zh: boolean }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/25 px-2.5 py-2">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className="truncate text-[10px] font-semibold text-slate-200">{item.feature}</span>
        <span className="shrink-0 rounded border border-white/10 px-1.5 py-0.5 text-[8px] text-slate-500">
          {item.source_type || (zh ? '未知来源' : 'unknown source')}
        </span>
      </div>
      <div className="mt-1 break-words text-[10px] leading-relaxed text-slate-400">{valueText(item.value)}</div>
      <div className="mt-1 flex flex-wrap gap-2 text-[8px] text-slate-600">
        {item.frame_id_or_time != null ? <span>frame={valueText(item.frame_id_or_time)}</span> : null}
        {item.model_version ? <span>model={valueText(item.model_version)}</span> : null}
        {item.quality_score != null ? <span>q={Number(item.quality_score).toFixed(2)}</span> : null}
      </div>
    </div>
  );
}
export function ReaderEvidencePanel({ result, loading = false, zh = true, onRun, onNextAction }: Props) {
  const [fullReportOpen, setFullReportOpen] = React.useState(false);
  const belief = result?.belief_state;
  const decision = result?.report?.clinical_decision;
  const dino = result?.tool_evidence?.dino;
  const dinoPayload = dino?.dino && typeof dino.dino === 'object'
    ? dino.dino as Record<string, unknown>
    : null;
  const dinoAvailable = Boolean(dino?.available || dinoPayload?.available);
  const evidence = (belief?.evidence || result?.evidence || []).slice(0, 8);
  const conflicts = [
    ...(belief?.conflicts || []),
    ...((result?.report?.conflicting_evidence || []).map((message) => ({ message }))),
    ...((decision?.conflicts || []).map((item) => item as Record<string, unknown>)),
  ].slice(0, 5);
  const nextAction = belief?.next_actions?.[0];

  return (
    <>
    <section className="flex min-h-0 flex-col border-t border-white/10 bg-[#0b0d10]">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <BrainCircuit size={14} className="shrink-0 text-cyan-300" />
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-slate-100">
              {zh ? '科研 Agent 证据状态' : 'Research Agent evidence state'}
            </div>
            <div className="truncate text-[9px] text-slate-500">
              {belief?.schema_version || (zh ? '尚未运行统一 Agent' : 'Unified Agent not run')}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {result ? (
            <button
              type="button"
              onClick={() => setFullReportOpen(true)}
              className="reader-btn border-white/15 text-slate-300"
            >
              <FileText size={11} />
              {zh ? '完整报告' : 'Full report'}
            </button>
          ) : null}
          {onRun ? (
            <button
              type="button"
              onClick={() => (onNextAction ? onNextAction(nextAction?.action_type) : onRun())}
              disabled={loading}
              className="reader-btn shrink-0 border-cyan-400/30 text-cyan-200"
            >
              {loading ? <Loader2 size={11} className="animate-spin" /> : <ChevronRight size={11} />}
              {loading
                ? (zh ? '分析中' : 'Running')
                : (nextAction ? actionLabel(nextAction, zh) : (zh ? '运行统一 Agent' : 'Run unified Agent'))}
            </button>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 space-y-2 overflow-y-auto p-3">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2">
            <div className="text-[9px] text-slate-500">{zh ? '当前阶段倾向' : 'Provisional stage'}</div>
            <div className="mt-1 text-xl font-black text-emerald-200">
              {topStage(belief, result?.report?.recommended_t_stage)}
            </div>
          </div>
          <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-2">
            <div className="text-[9px] text-slate-500">{zh ? '临床决策状态' : 'Decision status'}</div>
            <div className="mt-1 text-[11px] font-semibold text-amber-100">
              {decision?.status || (zh ? '待运行' : 'Not run')}
            </div>
            {decision?.requires_mdt ? (
              <div className="mt-1 text-[9px] text-rose-300">{zh ? '建议 MDT 复核' : 'MDT review suggested'}</div>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 text-[9px]">
          <span className="inline-flex items-center gap-1 rounded border border-cyan-400/20 bg-cyan-400/5 px-2 py-1 text-cyan-200">
            <Dna size={10} /> DINO {dinoAvailable ? 'shadow:ok' : (zh ? '待补' : 'pending')}
          </span>
          <span className="inline-flex items-center gap-1 rounded border border-white/10 bg-white/[0.03] px-2 py-1 text-slate-400">
            <ShieldCheck size={10} /> {belief?.evidence?.length || result?.evidence?.length || 0} {zh ? '条证据' : 'evidence'}
          </span>
          {conflicts.length ? (
            <span className="inline-flex items-center gap-1 rounded border border-rose-400/25 bg-rose-400/5 px-2 py-1 text-rose-200">
              <CircleAlert size={10} /> {conflicts.length} {zh ? '个冲突' : 'conflicts'}
            </span>
          ) : null}
        </div>

        <div className="rounded-lg border border-cyan-400/15 bg-cyan-400/[0.03] px-2.5 py-2 text-[10px] leading-relaxed text-cyan-100/80">
          <div className="font-semibold text-cyan-200">{zh ? '下一步主动取证' : 'Next active evidence action'}</div>
          <div className="mt-1">{actionLabel(nextAction, zh)}</div>
          {nextAction?.reason ? <div className="mt-1 text-[9px] text-slate-500">{nextAction.reason}</div> : null}
        </div>

        {decision?.recommendation ? (
          <div className="rounded-lg border border-amber-400/15 bg-amber-400/[0.03] px-2.5 py-2 text-[10px] leading-relaxed text-amber-50/80">
            <div className="font-semibold text-amber-200">{zh ? '临床决策建议' : 'Clinical decision support'}</div>
            <div className="mt-1">{decision.recommendation}</div>
          </div>
        ) : null}

        {conflicts.length ? (
          <div className="rounded-lg border border-rose-400/20 bg-rose-400/[0.04] px-2.5 py-2 text-[10px] leading-relaxed text-rose-100/85">
            <div className="font-semibold text-rose-200">{zh ? '需要复核的冲突' : 'Conflicts requiring review'}</div>
            {conflicts.map((item, index) => {
              const record = item as Record<string, unknown>;
              const code = record.code;
              const message = record.message;
              return (
                <div key={`${String(code || message || 'conflict')}-${index}`} className="mt-1">
                  · {String(message || code || (zh ? '未命名冲突' : 'Unnamed conflict'))}
                </div>
              );
            })}
          </div>
        ) : null}

        {evidence.length ? (
          <div className="space-y-1.5">
            <div className="text-[9px] font-semibold uppercase tracking-wide text-slate-500">
              {zh ? '可追溯证据' : 'Traceable evidence'}
            </div>
            {evidence.map((item, index) => <EvidenceRow key={`${item.evidence_id}-${index}`} item={item} zh={zh} />)}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-white/10 px-2.5 py-3 text-[10px] text-slate-600">
            {zh ? '运行统一 Agent 后，这里显示病例信念、DINO、七征象和跨模态证据。' : 'Run the unified Agent to populate case belief, DINO, seven-sign, and cross-modal evidence.'}
          </div>
        )}
      </div>
    </section>
    {fullReportOpen && result ? (
      <div className="fixed inset-0 z-[300000] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm">
        <div className="relative flex max-h-[92vh] w-[min(1180px,96vw)] flex-col overflow-hidden rounded-xl border border-white/15 bg-[#080b0f] shadow-2xl">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-black px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                <FileText size={15} />
                {zh ? '病例 Agent 多模态报告' : 'Case Agent multimodal report'}
              </div>
              <div className="mt-1 truncate text-[10px] text-slate-500">
                {result.session_id} · {result.traces?.length || 0} traces · {result.knowledge_context?.length || 0} knowledge snippets
              </div>
            </div>
            <button
              type="button"
              onClick={() => setFullReportOpen(false)}
              className="rounded-md border border-white/10 p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"
              aria-label={zh ? '关闭完整报告' : 'Close full report'}
            >
              <X size={15} />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="space-y-3">
                <div className="rounded-lg border border-emerald-300/20 bg-emerald-300/[0.04] p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.16em] text-emerald-200/70">{zh ? '综合建议' : 'Integrated recommendation'}</div>
                      <div className="mt-1 text-3xl font-black text-emerald-100">{result.report?.recommended_t_stage || 'cTx'}</div>
                      <div className="mt-1 text-[10px] text-emerald-100/70">{result.report?.confidence || 'uncertain'}</div>
                    </div>
                    <div className="max-w-[65%] text-[11px] leading-relaxed text-slate-300">
                      {result.report?.reasoning || (zh ? '等待报告推理文本。' : 'No report reasoning returned.')}
                    </div>
                  </div>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
                    <ShieldCheck size={13} />
                    {zh ? '多模态工具状态' : 'Multimodal tool status'}
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3">
                    {Object.entries(result.tool_evidence || {}).map(([key, tool]) => (
                      <div key={key} className="rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[10px]">
                        <div className="truncate text-slate-500">{key}</div>
                        <div className={`mt-0.5 ${tool?.available === false ? 'text-amber-200' : 'text-emerald-200'}`}>
                          {tool?.available === false ? 'unavailable' : tool ? 'available' : 'not run'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                {result.evidence?.length ? (
                  <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                    <div className="text-xs font-semibold text-slate-100">{zh ? '可追溯证据' : 'Traceable evidence'}</div>
                    <div className="mt-2 grid grid-cols-1 gap-1.5 md:grid-cols-2">
                      {result.evidence.slice(0, 12).map((item, index) => (
                        <div key={`${item.evidence_id}-${index}`} className="rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[10px]">
                          <div className="font-semibold text-slate-200">{item.feature}</div>
                          <div className="mt-0.5 text-slate-500">{valueText(item.value)}</div>
                          <div className="mt-0.5 text-[8px] text-slate-600">{valueText(item.source_type)} · {valueText(item.model_version || 'model')}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="space-y-3">
                <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
                    <FileText size={13} />
                    {zh ? '结构化报告草稿' : 'Structured report draft'}
                  </div>
                  {result.report?.dynamic_report_draft?.sections?.length ? (
                    <div className="mt-2 space-y-2">
                      {result.report.dynamic_report_draft.sections.map((section) => (
                        <div key={section.heading} className="rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[10px]">
                          <div className="font-semibold text-slate-200">{section.heading}</div>
                          <div className="mt-1 whitespace-pre-wrap leading-relaxed text-slate-400">{section.lines.join('\n')}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 text-[10px] text-slate-500">{zh ? '当前没有结构化报告草稿。' : 'No structured report draft returned.'}</div>
                  )}
                </div>
                <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
                    <Database size={13} />
                    {zh ? '知识检索与 Memory' : 'Knowledge retrieval and memory'}
                  </div>
                  <div className="mt-2 space-y-1.5 text-[10px]">
                    {result.knowledge_context?.slice(0, 4).map((item, index) => (
                      <div key={`${item.title}-${index}`} className="rounded border border-white/10 bg-white/[0.03] px-2 py-1.5">
                        <div className="font-semibold text-slate-200">{item.title}</div>
                        <div className="mt-0.5 line-clamp-3 text-slate-500">{item.content}</div>
                      </div>
                    ))}
                    <div className="rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-slate-400">
                      {zh ? 'Memory 候选：' : 'Memory candidates: '}
                      {result.report?.memory_update_candidates?.length || 0}
                      {' · '}
                      {zh ? '工具轨迹：' : 'Traces: '}
                      {result.traces?.length || 0}
                    </div>
                  </div>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                  <div className="text-xs font-semibold text-slate-100">{zh ? '相似病例' : 'Similar cases'}</div>
                  <div className="mt-2 space-y-1.5">
                    {result.similar_cases?.slice(0, 5).map((item, index) => (
                      <div key={`${item.patient_id}-${index}`} className="flex items-center justify-between gap-2 rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[10px]">
                        <span className="truncate text-slate-300">{item.patient_id}</span>
                        <span className="shrink-0 text-slate-500">{item.T_stage} · {Math.round(Number(item.similarity || 0) * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    ) : null}
    </>
  );
}
