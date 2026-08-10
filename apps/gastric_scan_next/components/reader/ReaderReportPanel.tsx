'use client';

import React, { useState } from 'react';
import { ChevronDown, Copy, Loader2 } from 'lucide-react';
import type { PrecomputedSimilarCases, ReaderDoctorAction, SamReport } from '@/lib/reader/types';
import { WallFeatureAnalysisCard } from '@/components/WallFeatureAnalysisCard';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import { GcUsEvidencePanel } from '@/components/GcUsEvidencePanel';
import { SpectralFeaturePanel } from '@/components/SpectralFeaturePanel';
import { buildGcUsReport, type GcUsReportState } from '@/lib/gc-us-report-template';
import type { AgentAnalysisResponse } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';

type Props = {
  report: SamReport | null;
  loading?: boolean;
  samScore?: number | null;
  maskPolygon: number[][] | null;
  frameSize: { width: number; height: number } | null;
  frameDataUrl?: string | null;
  layerPick?: { x: number; y: number } | null;
  layerResult?: LayerAnalyzeResult | null;
  caseId?: string | null;
  frameId?: string | null;
  frameTime?: number | null;
  clinical?: Record<string, unknown>;
  onLayerResult?: (r: LayerAnalyzeResult | null) => void;
  onEvidenceStateChange?: (state: GcUsReportState) => void;
  gcUsReport?: GcUsReportState | null;
  unifiedResult?: AgentAnalysisResponse | null;
  precomputedSimilar?: PrecomputedSimilarCases | null;
  onCopy?: () => void;
  onDoctorAction?: (action: ReaderDoctorAction) => void;
};

const STAGES = ['T1', 'T2', 'T3', 'T4+'];
const EMPTY_CLINICAL: Record<string, unknown> = {};
const EMPTY_POLYGON: number[][] = [];

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
  return report.template_prose || report.llm_report?.narrative || report.summary || '';
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null;
}

function clinicalNumber(value: unknown, fallback?: unknown): number | null {
  const direct = Number(value);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const alternate = Number(fallback);
  return Number.isFinite(alternate) && alternate > 0 ? alternate : null;
}

function clinicalMeasurementMm(
  clinical: Record<string, unknown>,
  mmKeys: string[],
  cmKeys: string[],
  nestedKey: 'length' | 'thickness',
): number | null {
  const records = [
    clinical,
    asRecord(clinical.measurements),
    asRecord(clinical.measurement),
  ].filter((value): value is Record<string, unknown> => Boolean(value));
  for (const record of records) {
    for (const key of mmKeys) {
      const value = clinicalNumber(record[key]);
      if (value != null) return value;
    }
    for (const key of cmKeys) {
      const value = clinicalNumber(record[key]);
      if (value != null) return value * 10;
    }
  }
  const nested = asRecord(clinical.tumorSize);
  const value = clinicalNumber(nested?.[nestedKey]);
  return value == null ? null : value * 10;
}

function clinicalLabValue(value: unknown, positive: unknown, zh = true): string {
  const number = clinicalNumber(value);
  if (number != null) return String(number);
  if (positive === true || positive === 1 || positive === '1') return zh ? '阳性' : 'positive';
  return zh ? '未提供' : 'n/a';
}

export function ReaderReportPanel({
  report,
  loading,
  samScore,
  maskPolygon,
  frameSize,
  frameDataUrl,
  layerPick,
  layerResult = null,
  caseId,
  frameId,
  frameTime,
  clinical = EMPTY_CLINICAL,
  onLayerResult,
  onEvidenceStateChange,
  gcUsReport = null,
  unifiedResult = null,
  precomputedSimilar = null,
  onCopy,
  onDoctorAction,
}: Props) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const tx = (a: string, b: string) => (zh ? a : b);
  const [moreOpen, setMoreOpen] = useState(false);
  const reportTemplateState = report?.structured && typeof report.structured === 'object'
    ? report.structured as unknown as GcUsReportState
    : null;
  const templateState = gcUsReport || reportTemplateState;
  const templateReport = templateState
    ? buildGcUsReport(
        templateState,
        templateState.reference_stage.requested_band || templateState.reference_stage.band,
        zh ? 'zh' : 'en',
      )
    : null;
  const unifiedReport = unifiedResult?.report;
  // Single clinical display stage: gated contour display first; conflicts or missing wall/lumen evidence force cTx.
  const gatedAssist = unifiedReport?.assist_display_stage
    || unifiedReport?.contour_diagnosis?.display_stage
    || null;
  const contourDiagnosis = unifiedReport?.contour_diagnosis || null;
  const hasEvidenceConflict = Boolean(
    (templateReport?.conflicts?.length || 0) > 0
    || (unifiedReport?.conflicting_evidence?.length || 0) > 0,
  );
  const evidenceReady = Boolean(
    contourDiagnosis?.lesion_confirmed
    && (contourDiagnosis?.lumen_mask_type === 'sam31_polygon' || contourDiagnosis?.lumen_mask_type === 'confirmed_mask'),
  );
  const stage = hasEvidenceConflict || !evidenceReady
    ? 'cTx'
    : (gatedAssist && !/^c?tx$/i.test(String(gatedAssist))
      ? gatedAssist
      : null)
      || (templateReport?.stage && templateReport.stage !== 'uncertain' ? templateReport.stage : null)
      || report?.recommended_stage
      || topStage(report?.stage_distribution)
      || 'cTx';
  const conf = unifiedReport
    ? (unifiedReport.confidence === 'high' ? 0.85 : unifiedReport.confidence === 'low' ? 0.35 : 0.6)
    : (report?.calibrated_confidence ?? 0);
  const llmError = report?.llm_report?.error;
  const narrative = unifiedReport?.dynamic_report_draft?.full_text
    || templateReport?.prose
    || pickNarrative(report);
  const [doctorStage, setDoctorStage] = useState('');
  const [reason, setReason] = useState('');
  const selectedStage = doctorStage || (STAGES.includes(stage) ? stage : '');
  const biomarkers = asRecord(clinical.biomarkers);
  const clinicalLocation = typeof clinical.location === 'string' && clinical.location.trim()
    ? clinical.location
    : tx('暂无来源', 'No source');
  const clinicalLength = clinicalMeasurementMm(
    clinical,
    ['tumor_size_mm', 'length_mm', 'tumorSizeMm', 'tumor_length_mm', 'long_diameter_mm', 'maximum_diameter_mm'],
    ['length_cm', 'tumor_size_cm', 'tumor_length_cm', 'long_diameter_cm', 'maximum_diameter_cm'],
    'length',
  );
  const clinicalThickness = clinicalMeasurementMm(
    clinical,
    ['tumor_thickness_mm', 'thickness_mm', 'tumorThicknessMm', 'tumor_depth_mm', 'maximum_thickness_mm'],
    ['thickness_cm', 'tumor_thickness_cm', 'tumor_depth_cm', 'maximum_thickness_cm'],
    'thickness',
  );
  const clinicalHasData = Object.keys(clinical).length > 0;

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col border-l border-white/10 bg-[#0c0d0f]">
      <div className="border-b border-white/10 p-3">
          <div className="flex items-center justify-between gap-2 text-xs font-semibold text-gray-200">
            <span>{tx("Agent 报告", "Agent report")}</span>
            {unifiedResult ? <span className="rounded border border-cyan-400/25 bg-cyan-400/5 px-1.5 py-0.5 text-[8px] text-cyan-200">Unified</span> : null}
          </div>
        <div className="mt-2 rounded-xl border border-white/10 bg-gradient-to-br from-emerald-950/40 to-black p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-500">{tx("临床展示分期（待确认）", "Clinical display stage (pending)")}</div>
              <div className="text-3xl font-bold text-emerald-300">{loading ? '…' : stage}</div>
              {hasEvidenceConflict ? (
                <div className="mt-0.5 text-[9px] text-amber-300">
                  {tx('存在征象冲突，已降为 cTx', 'Sign conflicts detected; downgraded to cTx')}
                </div>
              ) : !evidenceReady ? (
                <div className="mt-0.5 text-[9px] text-slate-500">
                  {tx('病灶/胃腔轮廓未确认，保持 cTx', 'Lesion/lumen contours unconfirmed; stays cTx')}
                </div>
              ) : null}
            </div>
            <div className="text-right">
              <div className="text-[10px] text-gray-500">{tx("置信", "Confidence")}</div>
              <div className={`text-sm font-semibold ${conf >= 0.72 ? 'text-emerald-300' : 'text-amber-300'}`}>
                {loading ? tx('生成中', 'Generating') : `${Math.round(conf * 100)}%`}
              </div>
              {maskPolygon?.length ? (
                <div className="mt-1 text-[10px] text-cyan-300">
                  {tx('Mask 已生成', 'Mask ready')}{samScore != null && samScore > 0 ? ` · ${Math.round(samScore * 100)}%` : tx(' · 分数不可用', ' · score unavailable')}
                </div>
              ) : samScore != null ? (
                <div className="mt-1 text-[10px] text-gray-500">{tx("分割", "Seg")} {Math.round(samScore * 100)}%</div>
              ) : null}
            </div>
          </div>
          <div className="mt-2 min-h-[72px] text-[11px] leading-relaxed text-gray-300">
            {loading ? (
              <span className="inline-flex items-center gap-2 text-gray-400">
                <Loader2 size={12} className="animate-spin" /> {tx('正在撰写 T 分期文字报告…', 'Writing T-stage report…')}
              </span>
            ) : llmError && !narrative ? (
              <span className="text-red-300">{tx("报告生成失败：", "Report failed: ")}{llmError}</span>
            ) : narrative ? (
              narrative.split(/\n+/).map((p, i) => <p key={i} className={i ? 'mt-2' : ''}>{p}</p>)
            ) : (
              <span className="text-gray-500">{tx("完成分割后点击「生成文字报告」，或分割后自动更新。", "After segmentation, click Generate report or wait for auto-update.")}</span>
            )}
          </div>
          {narrative && onCopy ? (
            <button type="button" onClick={onCopy} className="reader-btn mt-2 w-full justify-center">
              <Copy size={12} /> {tx("复制报告", "Copy report")}
            </button>
          ) : null}
          {report && onDoctorAction ? (
            <div className="mt-3 border-t border-white/10 pt-3">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                {tx("医生最终判断", "Physician final judgment")}
              </div>
              <select
                value={selectedStage}
                onChange={(event) => setDoctorStage(event.target.value)}
                className="w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-gray-200"
              >
                <option value="">{tx("暂不确定", "Uncertain")}</option>
                {STAGES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={tx("可选：修改、拒绝或证据不足原因", "Optional: reason for modify / reject / insufficient evidence")}
                className="mt-2 min-h-12 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-gray-200 placeholder:text-gray-600"
              />
              <div className="mt-2 grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  disabled={!evidenceReady || hasEvidenceConflict || /^c?tx$/i.test(String(stage))}
                  title={!evidenceReady || hasEvidenceConflict || /^c?tx$/i.test(String(stage))
                    ? tx('证据不足或存在冲突时不能直接采纳；请先复核并记录判断', 'Cannot accept when evidence is insufficient or conflicting; review and record judgment first')
                    : undefined}
                  className="reader-btn justify-center border-emerald-500/30 text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
                  onClick={() => onDoctorAction({
                    action_type: 'accept',
                    final_t_stage: selectedStage || undefined,
                    reason: reason || undefined,
                  })}
                >
                  {tx("采纳 AI", "Accept AI")}
                </button>
                <button
                  type="button"
                  className="reader-btn justify-center border-amber-500/30 text-amber-300"
                  onClick={() => onDoctorAction({
                    action_type: 'modify',
                    final_t_stage: selectedStage || undefined,
                    reason: reason || undefined,
                  })}
                >
                  {tx("修改确认", "Modify & confirm")}
                </button>
                <button
                  type="button"
                  className="reader-btn justify-center border-red-500/30 text-red-300"
                  onClick={() => onDoctorAction({
                    action_type: 'reject',
                    final_t_stage: selectedStage || undefined,
                    reason: reason || undefined,
                  })}
                >
                  {tx("拒绝 AI", "Reject AI")}
                </button>
                <button
                  type="button"
                  className="reader-btn justify-center border-sky-500/30 text-sky-300"
                  onClick={() => onDoctorAction({
                    action_type: 'request_more_evidence',
                    final_t_stage: selectedStage || undefined,
                    reason: reason || tx('证据不足', 'Insufficient evidence'),
                  })}
                >
                  {tx("证据不足", "Need more evidence")}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {report?.stage_distribution ? (
        <div className="border-b border-white/10 p-3">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">{tx("分期概率", "Stage probabilities")}</div>
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
        <section className="rounded-xl border border-cyan-400/20 bg-cyan-400/[0.04] p-3 text-[11px] text-gray-200">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-cyan-100">{tx("临床辅助资料", "Clinical auxiliaries")}</span>
            <span className="text-[9px] text-cyan-200/70">{tx("仅供医生参考，不参与自动分期", "Physician reference only; not used for auto staging")}</span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] text-gray-500">{tx("病灶部位", "Lesion site")}</div>
              <div className="mt-0.5 truncate text-gray-200">{clinicalHasData ? clinicalLocation : tx('暂无来源', 'No source')}</div>
            </div>
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] text-gray-500">{tx("肿瘤长径", "Max length")}</div>
              <div className="mt-0.5 font-mono text-gray-200">{clinicalLength != null ? `${clinicalLength} mm` : tx('未评估', 'Not assessed')}</div>
            </div>
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] text-gray-500">{tx("肿瘤厚度", "Max thickness")}</div>
              <div className="mt-0.5 font-mono text-gray-200">{clinicalThickness != null ? `${clinicalThickness} mm` : tx('未评估', 'Not assessed')}</div>
            </div>
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] text-gray-500">CEA</div>
              <div className="mt-0.5 font-mono text-gray-200">
                {clinicalLabValue(clinical.cea, biomarkers?.cea_positive, zh)}
              </div>
            </div>
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] text-gray-500">CA19-9</div>
              <div className="mt-0.5 font-mono text-gray-200">
                {clinicalLabValue(clinical.ca199, biomarkers?.ca199_positive, zh)}
              </div>
            </div>
          </div>
        </section>
        <WallFeatureAnalysisCard
          zh={zh}
          lesionPolygon={maskPolygon || EMPTY_POLYGON}
          wallPolygon={[]}
          frameSize={frameSize}
          frameDataUrl={frameDataUrl}
          pick={layerPick}
          onResult={onLayerResult}
        />

        <GcUsEvidencePanel
          zh={zh}
          caseId={caseId}
          frameId={frameId}
          frameTime={frameTime}
          clinical={clinical}
          lesionPolygon={maskPolygon || []}
          frameSize={frameSize}
          layerResult={layerResult}
          productStage={report?.recommended_stage || null}
          initialState={templateState}
          onStateChange={onEvidenceStateChange}
        />

        {report?.toolchain?.length ? (
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">{tx("分析链路", "Analysis chain")}</div>
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
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">{tx("证据", "Evidence")}</div>
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
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">{tx("相似病例", "Similar cases")}</div>
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

        <section className="rounded-xl border border-white/5 bg-white/[0.015]">
          <button
            type="button"
            onClick={() => setMoreOpen((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-300"
          >
            <span>{tx('更多分析（相似病例, 频谱形态）', 'More analysis (similar cases, spectral features)')}</span>
            <ChevronDown size={12} className={`transition-transform ${moreOpen ? 'rotate-180' : ''}`} />
          </button>
          {moreOpen ? (
            <div className="space-y-3 border-t border-white/5 p-3">
              <div>
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold text-gray-400">
                    {tx('相似病例（预计算）', 'Similar cases (precomputed)')}
                  </span>
                  {precomputedSimilar?.available ? (
                    <span className="rounded border border-white/10 px-1.5 py-0.5 text-[8px] text-gray-500">
                      {tx('仅按临床资料匹配', 'Clinical-profile match only')}
                    </span>
                  ) : null}
                </div>
                {precomputedSimilar?.available && precomputedSimilar.similar_cases?.length ? (
                  <div className="space-y-1">
                    {precomputedSimilar.similar_cases.map((sc, i) => (
                      <div key={sc.patient_id || i} className="flex items-center justify-between rounded border border-white/5 px-2 py-1 text-[10px]">
                        <span className="text-gray-300">
                          #{sc.rank ?? i + 1} {sc.patient_id}
                          <span className="ml-1 text-gray-600">{sc.data_source}</span>
                        </span>
                        <span className="text-gray-500">{sc.T_stage || '—'}, {Math.round((sc.similarity || 0) * 100)}%</span>
                      </div>
                    ))}
                    <div className="text-[9px] leading-relaxed text-gray-600">
                      {tx(
                        '来自院内训练集回顾性病例, 病理分期仅供参考; 运行辅助分析后可获得基于影像特征的实时检索',
                        'Retrospective in-house training cases; pathology stages are reference only. Run AI analysis for image-feature-based live retrieval',
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="rounded border border-dashed border-white/10 px-2 py-2 text-[10px] text-gray-600">
                    {tx(
                      '本例暂无预计算相似病例, 运行辅助分析后可查看实时检索结果',
                      'No precomputed similar cases for this case; run AI analysis for live retrieval',
                    )}
                  </div>
                )}
              </div>
              <SpectralFeaturePanel analysis={unifiedResult} zh={zh} />
            </div>
          ) : null}
        </section>
      </div>
    </aside>
  );
}
