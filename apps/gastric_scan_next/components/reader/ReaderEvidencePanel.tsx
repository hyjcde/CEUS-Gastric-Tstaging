'use client';

import React from 'react';
import { BrainCircuit, ChevronRight, CircleAlert, Database, Dna, FileText, Loader2, ShieldCheck, X } from 'lucide-react';
import type { AgentAnalysisResponse, AgentBeliefAction, AgentEvidenceItem, AgentStep, ContourDiagnosis } from '@/types';

type Props = {
  result: AgentAnalysisResponse | null;
  loading?: boolean;
  zh?: boolean;
  onRun?: () => void;
  onNextAction?: (actionType?: string) => void;
  onOpenFullReport?: () => void;
};

const LOADING_STEPS = [
  { id: 'validate', zh: '校验病灶与胃腔轮廓', en: 'Validate lesion and lumen contours' },
  { id: 'frames', zh: '采集当前帧与邻近帧', en: 'Capture current and neighboring frames' },
  { id: 'wall', zh: '汇总壁层 / 边界证据', en: 'Aggregate wall and boundary evidence' },
  { id: 't23', zh: '对照 T2 / T3 依据', en: 'Compare T2 vs T3 evidence' },
  { id: 'review', zh: '生成可复核建议', en: 'Draft reviewable recommendation' },
] as const;

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
function answerLabel(value: unknown): string | null {
  const raw = String(value || '').trim();
  const stage = raw.toUpperCase().match(/\bT([1-4])(\+)?\b/);
  if (stage) return `T${stage[1]}${stage[2] || ''}`;
  if (/^(benign|良性)$/i.test(raw)) return 'benign';
  if (/^(malignant|恶性)$/i.test(raw)) return 'malignant';
  return null;
}

function answerText(value: string | null, zh: boolean): string {
  if (value === 'benign') return zh ? '良性' : 'Benign';
  if (value === 'malignant') return zh ? '恶性' : 'Malignant';
  return value || (zh ? '待生成' : 'Pending');
}

function stageSummary(result: AgentAnalysisResponse | null): {
  stage: string | null;
  confidence: number | null;
  researchStage?: string | null;
} {
  const hypotheses = (result?.belief_state?.hypotheses || [])
    .map((item) => ({
      stage: answerLabel(item.label),
      probability: typeof item.probability === 'number' && Number.isFinite(item.probability)
        ? item.probability
        : null,
    }))
    .filter((item): item is { stage: string; probability: number } => (
      Boolean(item.stage) && item.probability != null
    ))
    .sort((a, b) => b.probability - a.probability);
  const classification = result?.tool_evidence?.classification;
  const classificationStage = answerLabel(classification?.top1_stage);
  const classificationConfidence = typeof classification?.top1_prob === 'number'
    && Number.isFinite(classification.top1_prob)
    ? classification.top1_prob
    : null;
  const evidence = result?.belief_state?.evidence || result?.evidence || [];
  const binaryEvidence = evidence
    .filter((item) => item.source_type === 'binary_gate')
    .map((item) => ({
      label: item.feature === 'p_benign' ? 'benign' : item.feature === 'p_malignant' ? 'malignant' : null,
      confidence: typeof item.confidence === 'number'
        ? item.confidence
        : typeof item.value === 'number' ? item.value : null,
    }))
    .filter((item): item is { label: string; confidence: number } => (
      Boolean(item.label) && item.confidence != null && Number.isFinite(item.confidence)
    ))
    .sort((a, b) => b.confidence - a.confidence);
  const answer = answerLabel(
    result?.report?.assist_display_stage
    || result?.report?.contour_diagnosis?.display_stage
    || 'cTx',
  );
  const researchAnswer = answerLabel(result?.report?.recommended_t_stage);
  const binaryConfidence = binaryEvidence.find((item) => item.label === researchAnswer || item.label === answer)?.confidence
    ?? binaryEvidence[0]?.confidence
    ?? null;
  const top = hypotheses?.[0];
  // Doctor-facing summary uses gated display; classifier/belief remains in confidence only.
  return {
    stage: answer || 'cTx',
    confidence: classificationConfidence ?? top?.probability ?? binaryConfidence,
    researchStage: top?.stage || classificationStage || researchAnswer,
  };
}

function actionLabel(action: AgentBeliefAction | undefined, zh: boolean): string {
  if (!action) return zh ? '等待新的证据' : 'Waiting for new evidence';
  const labels: Record<string, [string, string]> = {
    inspect_conflict_frame: ['定位冲突帧', 'Inspect conflict frame'],
    inspect_next_frame: ['检查下一帧', 'Inspect next frame'],
    run_wall_evidence: ['补充胃壁证据', 'Run wall evidence'],
    run_dino_shadow_evidence: ['补充区域特征证据', 'Add region-feature evidence'],
    request_doctor_confirmation: ['请求医生确认', 'Request physician confirmation'],
  };
  const pair = labels[action.action_type];
  return pair ? (zh ? pair[0] : pair[1]) : action.action_type;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function signField(
  result: AgentAnalysisResponse | null,
  key: string,
): { value: string; status: string; source: string } | null {
  const signs = asRecord(result?.tool_evidence?.gc_us_signs);
  const nested = asRecord(signs?.signs) || signs;
  const field = asRecord(nested?.[key]);
  if (!field) return null;
  const value = field.value == null || field.value === '' ? '' : String(field.value);
  if (!value) return null;
  return {
    value,
    status: String(field.status || 'suggested'),
    source: String(field.source || field.evidence_role || 'assist'),
  };
}

function buildT23Card(result: AgentAnalysisResponse | null, zh: boolean): {
  lean: string;
  t2: string[];
  t3: string[];
  caveats: string[];
} {
  const layer = signField(result, 'layer_structure');
  const serosa = signField(result, 'serosa_change');
  const boundary = signField(result, 'boundary');
  const morphology = signField(result, 'morphology');
  const growth = signField(result, 'growth_pattern');
  const pack = result?.report?.report_pack;
  const matrix = pack?.evidence_matrix || [];
  const conflicts = [
    ...(result?.report?.conflicting_evidence || []),
    ...(result?.report?.uncertainty_flags || []),
  ].map((item) => String(item));

  const t2: string[] = [];
  const t3: string[] = [];
  const caveats: string[] = [];

  if (layer) {
    const text = `${zh ? '胃壁层次' : 'Wall layers'}: ${layer.value}`;
    if (/浆膜下|subserosa|T3/i.test(layer.value)) t3.push(text);
    else if (/固有肌|muscularis|T2/i.test(layer.value)) t2.push(text);
    else caveats.push(text);
  } else {
    caveats.push(zh ? '尚无经确认的壁层层次结论' : 'No confirmed wall-layer conclusion yet');
  }

  if (serosa) {
    const text = `${zh ? '浆膜改变' : 'Serosal change'}: ${serosa.value}`;
    if (/中断|破坏|侵犯|突破|interrupted|invad/i.test(serosa.value)) t3.push(text);
    else if (/完整|未见|intact|absent/i.test(serosa.value)) t2.push(text);
    else caveats.push(text);
  }

  if (boundary) {
    const text = `${zh ? '边界' : 'Boundary'}: ${boundary.value}`;
    if (/不清|浸润|irregular|infiltr/i.test(boundary.value)) t3.push(text);
    else t2.push(text);
  }
  if (morphology) {
    const text = `${zh ? '形态' : 'Morphology'}: ${morphology.value}`;
    if (/不规则|溃疡|irregular|ulcer/i.test(morphology.value)) t3.push(text);
    else t2.push(text);
  }
  if (growth) {
    const text = `${zh ? '生长方式' : 'Growth'}: ${growth.value}`;
    if (/浸润|外生|infiltr|exophyt/i.test(growth.value)) t3.push(text);
    else t2.push(text);
  }

  for (const item of matrix.slice(0, 8)) {
    const label = String(item.label || item.id || '');
    const value = valueText(item.value);
    const line = `${label}: ${value}`;
    const supports = (item.supports || []).map((entry) => String(entry).toUpperCase());
    const refutes = (item.refutes || []).map((entry) => String(entry).toUpperCase());
    if (supports.some((entry) => entry.includes('T3')) || /T3|浆膜下|subserosa/i.test(`${label} ${value}`)) {
      t3.push(line);
    } else if (supports.some((entry) => entry.includes('T2')) || /T2|固有肌|muscularis/i.test(`${label} ${value}`)) {
      t2.push(line);
    }
    if (refutes.length || item.status === 'conflict' || item.status === 'uncertain') {
      caveats.push(line);
    }
  }

  caveats.push(...conflicts.slice(0, 4));
  if (!t2.length && !t3.length) {
    caveats.push(
      zh
        ? '当前多为几何/边界代理，不能单独区分 T2 与 T3；请结合多切面复核'
        : 'Mostly geometric/boundary proxies; cannot distinguish T2 vs T3 alone — review multiple planes',
    );
  }

  const stage = answerLabel(
    result?.report?.assist_display_stage
    || result?.report?.contour_diagnosis?.display_stage
    || 'cTx',
  ) || stageSummary(result).stage;
  const lean = stage === 'T2' || stage === 'T3' || stage === 'T3+'
    ? stage
    : (t3.length > t2.length ? 'T3?' : t2.length > t3.length ? 'T2?' : (zh ? '待复核' : 'Review'));

  const uniq = (items: string[]) => Array.from(new Set(items.filter(Boolean))).slice(0, 5);
  return { lean, t2: uniq(t2), t3: uniq(t3), caveats: uniq(caveats) };
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

function formatMetricValue(value: unknown, unit?: string): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const abs = Math.abs(value);
    const text = abs >= 10 ? value.toFixed(1) : abs >= 1 ? value.toFixed(2) : value.toFixed(3);
    return unit ? `${text} ${unit}` : text;
  }
  return valueText(value);
}

function BoundaryExplainabilityCard({
  result,
  zh,
  compact = false,
}: {
  result: AgentAnalysisResponse | null;
  zh: boolean;
  compact?: boolean;
}) {
  const pack = result?.report?.report_pack;
  const contour = result?.report?.contour_diagnosis || null;
  const boundary = pack?.charts?.boundary_geometry || [];
  const wall = pack?.charts?.wall_geometry || [];
  const matrix = (pack?.evidence_matrix || []).filter((item) => {
    const domain = String(item.domain || '').toLowerCase();
    const label = String(item.label || item.id || '').toLowerCase();
    return /boundary|wall|morph|几何|边界|壁|接触|突破|curv|irregular/.test(`${domain} ${label}`);
  }).slice(0, compact ? 4 : 8);
  const boundarySign = signField(result, 'boundary');
  const layerSign = signField(result, 'layer_structure');
  const serosaSign = signField(result, 'serosa_change');
  if (!result) return null;

  return (
    <div className={`rounded-lg border border-amber-300/25 bg-amber-400/[0.05] ${compact ? 'px-2.5 py-2' : 'p-3'}`}>
      <div className="flex items-center justify-between gap-2">
        <div className={`${compact ? 'text-[9px]' : 'text-xs'} font-semibold text-amber-100`}>
          {zh ? '边界评分与可解释性' : 'Boundary scores and explainability'}
        </div>
        <span className="rounded border border-amber-300/30 px-1.5 py-0.5 font-mono text-[9px] text-amber-100/80">
          {contour?.geometry_relation || (zh ? '几何代理' : 'geometry proxy')}
        </span>
      </div>
      <div className="mt-1.5 text-[9px] leading-relaxed text-amber-50/75">
        {zh
          ? '突破胃壁的关键区是病灶与胃腔壁的接触带，不是整片重叠填色。下列评分为轮廓/几何代理，需结合壁层层次与多切面复核。'
          : 'Breakthrough analysis focuses on the lesion-to-lumen-wall contact band, not the full overlap wash. Scores below are contour/geometry proxies and require wall-layer and multiplane review.'}
      </div>

      {(boundarySign || layerSign || serosaSign) ? (
        <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-3">
          {boundarySign ? (
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-[9px]">
              <div className="text-slate-500">{zh ? '边界征象' : 'Boundary sign'}</div>
              <div className="mt-0.5 text-slate-200">{boundarySign.value}</div>
            </div>
          ) : null}
          {layerSign ? (
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-[9px]">
              <div className="text-slate-500">{zh ? '壁层层次' : 'Wall layers'}</div>
              <div className="mt-0.5 text-slate-200">{layerSign.value}</div>
            </div>
          ) : null}
          {serosaSign ? (
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-[9px]">
              <div className="text-slate-500">{zh ? '浆膜改变' : 'Serosa'}</div>
              <div className="mt-0.5 text-slate-200">{serosaSign.value}</div>
            </div>
          ) : null}
        </div>
      ) : null}

      {(boundary.length || wall.length) ? (
        <div className={`mt-2 grid gap-2 ${compact ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'}`}>
          {boundary.length ? (
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] font-semibold text-slate-300">{zh ? '边界几何评分' : 'Boundary geometry scores'}</div>
              <div className="mt-1 space-y-1">
                {boundary.slice(0, compact ? 4 : 6).map((metric) => (
                  <div key={metric.id} className="flex items-start justify-between gap-2 text-[9px]">
                    <span className="min-w-0 text-slate-400">
                      {metric.label}
                      {metric.note ? <span className="ml-1 text-slate-600">({metric.note})</span> : null}
                    </span>
                    <span className="shrink-0 font-mono text-amber-100">{formatMetricValue(metric.value, metric.unit)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {wall.length ? (
            <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <div className="text-[9px] font-semibold text-slate-300">{zh ? '接触/壁层几何代理' : 'Contact / wall geometry proxy'}</div>
              <div className="mt-1 space-y-1">
                {wall.slice(0, compact ? 4 : 6).map((metric) => (
                  <div key={metric.id} className="flex items-start justify-between gap-2 text-[9px]">
                    <span className="min-w-0 text-slate-400">
                      {metric.label}
                      {metric.note ? <span className="ml-1 text-slate-600">({metric.note})</span> : null}
                    </span>
                    <span className="shrink-0 font-mono text-amber-100">{formatMetricValue(metric.value, metric.unit)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="mt-2 text-[9px] text-slate-500">
          {zh ? '生成辅助意见后将显示边界不规则度、接触弧比例、向外距离等评分。' : 'Boundary irregularity, contact-arc ratio, and outward-depth scores appear after Assist runs.'}
        </div>
      )}

      {matrix.length ? (
        <div className="mt-2 rounded border border-white/10 bg-black/20 px-2 py-1.5">
          <div className="text-[9px] font-semibold text-slate-300">{zh ? '可解释证据条目' : 'Explainable evidence rows'}</div>
          <div className="mt-1 space-y-1">
            {matrix.map((item) => (
              <div key={String(item.id || item.label)} className="text-[9px] leading-relaxed text-slate-400">
                · {String(item.label || item.id)}: {valueText(item.value)}
                {item.status ? <span className="ml-1 text-slate-600">[{String(item.status)}]</span> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {contour?.summary ? (
        <div className="mt-2 text-[9px] leading-relaxed text-slate-400">{contour.summary}</div>
      ) : null}
    </div>
  );
}

function ContourDiagnosisCard({
  contour,
  loading,
  zh,
}: {
  contour?: ContourDiagnosis | null;
  loading: boolean;
  zh: boolean;
}) {
  if (loading && !contour) {
    return (
      <div className="rounded-lg border border-lime-300/25 bg-lime-400/[0.05] px-2.5 py-2">
        <div className="text-[9px] font-semibold uppercase tracking-wide text-lime-100">
          {zh ? '轮廓锚定诊断' : 'Contour-anchored diagnosis'}
        </div>
        <div className="mt-1 text-[10px] text-slate-400">
          {zh ? '正在基于已确认病灶与胃腔轮廓汇总证据…' : 'Aggregating evidence from confirmed lesion and lumen contours…'}
        </div>
      </div>
    );
  }
  if (!contour) return null;
  const display = contour.display_stage || 'cTx';
  const provisional = contour.provisional_stage || contour.classifier_stage || 'cTx';
  const lumenLabel = contour.lumen_mask_type === 'sam31_polygon' || contour.lumen_mask_type === 'confirmed_mask'
    ? (zh ? '胃腔轮廓已确认' : 'Lumen contour confirmed')
    : contour.lumen_mask_type === 'bbox_proxy'
      ? (zh ? '胃腔仅框代理' : 'Lumen box proxy only')
      : (zh ? '胃腔未确认' : 'Lumen missing');
  return (
    <div className="rounded-lg border border-lime-300/30 bg-lime-400/[0.06] px-2.5 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[9px] font-semibold uppercase tracking-wide text-lime-100">
          {zh ? '轮廓锚定诊断' : 'Contour-anchored diagnosis'}
        </div>
        <span className="rounded border border-lime-300/30 px-1.5 py-0.5 font-mono text-[9px] text-lime-50">
          {display}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[9px]">
        <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-slate-300">
          {contour.lesion_confirmed ? (zh ? '病灶轮廓已确认' : 'Lesion contour confirmed') : (zh ? '病灶未确认' : 'Lesion missing')}
        </div>
        <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-slate-300">
          {lumenLabel}
        </div>
        <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-slate-300">
          {zh ? '分类器倾向' : 'Classifier'} {provisional}
        </div>
        <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-slate-300">
          {contour.wall_is_proxy
            ? (zh ? '壁层=几何代理' : 'Wall = geometry proxy')
            : (zh ? '壁层证据已强化' : 'Wall evidence strengthened')}
          {contour.penetration_risk ? ` / ${contour.penetration_risk}` : ''}
        </div>
      </div>
      {contour.summary ? (
        <div className="mt-2 text-[10px] leading-relaxed text-slate-300">{contour.summary}</div>
      ) : null}
      {contour.status === 'contour_ready_t23_indeterminate' ? (
        <div className="mt-1.5 text-[9px] leading-relaxed text-amber-200/90">
          {zh
            ? '已具备双轮廓，但尚无经确认壁层/浆膜；T2/T3 不定，请结合壁层层次与多切面复核。'
            : 'Dual contours ready, but layer/serosa not confirmed; T2/T3 indeterminate — review wall layers and multiple planes.'}
        </div>
      ) : null}
    </div>
  );
}

function AnalysisProcess({
  loading,
  steps,
  zh,
  compact = false,
}: {
  loading: boolean;
  steps: AgentStep[];
  zh: boolean;
  compact?: boolean;
}) {
  const stepCount = steps.length || LOADING_STEPS.length;
  const doneCount = steps.length
    ? steps.filter((step) => /complete|done|success|ok|finish/i.test(step.status)).length
    : 0;
  const activeStep = loading
    ? (steps.length ? steps[steps.length - 1] : null)
    : null;
  const activeLabel = activeStep
    ? `${activeStep.order}. ${activeStep.title}`
    : (loading ? (zh ? LOADING_STEPS[0].zh : LOADING_STEPS[0].en) : null);
  const progressPct = loading
    ? Math.max(8, Math.round(((doneCount + 0.5) / Math.max(1, stepCount)) * 100))
    : (steps.length ? Math.round((doneCount / Math.max(1, stepCount)) * 100) : 0);
  const bar = (
    <div className="mt-2">
      <div className="flex items-center justify-between gap-2 text-[9px] text-slate-500">
        <span>{loading ? (zh ? '正在分析' : 'Analyzing') : (zh ? '已完成' : 'Completed')}</span>
        <span className="font-mono">{progressPct}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-900">
        <div
          className={`h-full rounded-full transition-all duration-500 ${loading ? 'animate-pulse bg-sky-400' : 'bg-emerald-400'}`}
          style={{ width: `${progressPct}%` }}
        />
      </div>
      {activeLabel ? (
        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-sky-200">
          {loading ? <Loader2 size={11} className="animate-spin" /> : null}
          <span className="truncate">{zh ? '当前步骤' : 'Current step'}: {activeLabel}</span>
        </div>
      ) : null}
    </div>
  );
  if (loading && !steps.length) {
    return (
      <div className="rounded-lg border border-sky-400/20 bg-sky-400/[0.05] px-2.5 py-2">
        <div className="text-[9px] font-semibold uppercase tracking-wide text-sky-200">
          {zh ? '分析过程' : 'Analysis process'}
        </div>
        {bar}
        <div className="mt-2 space-y-1.5">
          {LOADING_STEPS.map((step, index) => (
            <div key={step.id} className="flex items-start gap-2 text-[10px] text-slate-300">
              <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${index === 0 ? 'animate-pulse bg-sky-300' : 'bg-white/20'}`} />
              <span>{zh ? step.zh : step.en}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (!steps.length) return null;
  return (
    <div className="rounded-lg border border-amber-300/20 bg-amber-300/[0.04] px-2.5 py-2">
      <div className="text-[9px] font-semibold uppercase tracking-wide text-amber-100">
        {zh ? `分析过程, ${steps.length} 步` : `Analysis process, ${steps.length} steps`}
      </div>
      {bar}
      <div className="mt-2 space-y-1.5">
        {(compact ? steps.slice(0, 4) : steps.slice(0, 8)).map((step) => (
          <div key={`${step.order}-${step.step_id}`} className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-[10px]">
            <div className="flex items-start gap-2">
              <span className="shrink-0 font-mono text-amber-200/80">{step.order}</span>
              <div className="min-w-0">
                <div className="font-semibold text-slate-200">{step.title}</div>
                <div className="mt-0.5 text-slate-500">
                  {step.tool_name || 'workflow'} / {step.status}
                </div>
                {step.decision || step.reasoning ? (
                  <div className="mt-0.5 leading-relaxed text-slate-400">
                    {String(step.decision || step.reasoning).slice(0, compact ? 90 : 160)}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ReaderEvidencePanel({
  result,
  loading = false,
  zh = true,
  onRun,
  onNextAction,
  onOpenFullReport,
}: Props) {
  const [fullReportOpen, setFullReportOpen] = React.useState(false);
  const previousResultRef = React.useRef<AgentAnalysisResponse | null>(result);
  const belief = result?.belief_state;
  const summary = stageSummary(result);
  const decision = result?.report?.clinical_decision;
  const contour = result?.report?.contour_diagnosis || null;
  const evidenceConflict = Boolean(
    (result?.report?.conflicting_evidence?.length || 0) > 0
    || (belief?.conflicts?.length || 0) > 0
    || (decision?.conflicts?.length || 0) > 0,
  );
  const contoursReady = Boolean(
    contour?.lesion_confirmed
    && (contour?.lumen_mask_type === 'sam31_polygon' || contour?.lumen_mask_type === 'confirmed_mask'),
  );
  const gatedDisplay = result?.report?.assist_display_stage || contour?.display_stage || summary.stage;
  const displayStage = evidenceConflict || !contoursReady ? 'cTx' : gatedDisplay;
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
  const t23 = buildT23Card(result, zh);
  const agentSteps = result?.agent_steps || [];

  React.useEffect(() => {
    if (!previousResultRef.current && result) {
      setFullReportOpen(true);
    } else if (!result) {
      setFullReportOpen(false);
    }
    previousResultRef.current = result;
  }, [result]);

  return (
    <>
    <section className="flex min-h-0 flex-col border-t border-white/10 bg-[#0b0d10]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <BrainCircuit size={14} className="shrink-0 text-cyan-300" />
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-slate-100">
              {zh ? '辅助诊断意见' : 'Assisted diagnosis'}
            </div>
            <div className="truncate text-[9px] text-slate-500">
              {belief?.schema_version || (zh ? '尚未生成辅助意见' : 'Assisted opinion not generated yet')}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={() => {
              if (onOpenFullReport) {
                onOpenFullReport();
              } else {
                setFullReportOpen(true);
              }
            }}
            className="reader-btn min-w-[5.5rem] justify-center border-emerald-400/30 text-emerald-100"
          >
            <FileText size={11} />
            {zh ? '完整报告' : 'Full report'}
          </button>
          {onRun ? (
            <button
              type="button"
              onClick={() => (onNextAction ? onNextAction(nextAction?.action_type) : onRun())}
              disabled={loading}
              className="reader-btn min-w-[6.5rem] justify-center border-cyan-400/30 text-cyan-200"
            >
              {loading ? <Loader2 size={11} className="animate-spin" /> : <ChevronRight size={11} />}
              {loading
                ? (zh ? '分析中' : 'Running')
                : (nextAction ? actionLabel(nextAction, zh) : (result ? (zh ? '重新分析' : 'Re-run') : (zh ? '生成辅助意见' : 'Generate assist')))}
            </button>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 space-y-2 overflow-y-auto p-3">
        <ContourDiagnosisCard contour={contour} loading={loading} zh={zh} />
        {result ? (
          <div className="rounded-lg border border-emerald-300/30 bg-emerald-400/[0.06] px-2.5 py-2">
            <div className="text-[9px] font-semibold uppercase tracking-wide text-emerald-100">
              {zh ? '主看点: 胃壁五层' : 'Primary: wall five-layer'}
            </div>
            <div className="mt-1.5 grid grid-cols-1 gap-1.5 sm:grid-cols-3">
              {(['layer_structure', 'serosa_change', 'boundary'] as const).map((key) => {
                const field = signField(result, key);
                const label = key === 'layer_structure'
                  ? (zh ? '层次' : 'Layers')
                  : key === 'serosa_change'
                    ? (zh ? '浆膜' : 'Serosa')
                    : (zh ? '边界' : 'Boundary');
                return (
                  <div key={key} className="rounded border border-white/10 bg-black/20 px-2 py-1.5 text-[9px]">
                    <div className="text-slate-500">{label}</div>
                    <div className="mt-0.5 font-semibold text-slate-100">{field?.value || (zh ? '待复核' : 'Review')}</div>
                  </div>
                );
              })}
            </div>
            <div className="mt-1.5 text-[8px] leading-relaxed text-emerald-50/70">
              {zh
                ? '层次与浆膜经确认后才可定 cT；边界评分见下方，仅作复核代理。'
                : 'Confirmed layers/serosa are required for cT; boundary scores below are review proxies only.'}
            </div>
          </div>
        ) : null}
        {result ? <BoundaryExplainabilityCard result={result} zh={zh} compact /> : null}

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2">
            <div className="text-[9px] text-slate-500">{zh ? '辅助显示分期' : 'Assist display stage'}</div>
            <div className="mt-1 text-xl font-black text-emerald-200">
              {result ? answerText(displayStage || 'cTx', zh) : 'cTx'}
            </div>
            <div className="mt-1 text-[9px] text-emerald-100/70">
              {loading
                ? (zh ? '分析中' : 'Analyzing')
                : contour?.provisional_stage && contour.provisional_stage !== displayStage
                  ? `${zh ? '分类器倾向' : 'Classifier'} ${contour.provisional_stage}`
                  : summary.confidence != null
                    ? `${zh ? '置信度' : 'Confidence'} ${Math.round(summary.confidence * 100)}%`
                    : (result?.report?.confidence
                      ? `${zh ? '置信度等级' : 'Confidence level'} ${result.report.confidence}`
                      : (zh ? '证据受限，需医生复核' : 'Evidence-limited; physician review'))}
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

        <AnalysisProcess loading={loading} steps={agentSteps} zh={zh} compact />

        {(result || loading) ? (
          <div className="rounded-lg border border-violet-300/25 bg-violet-400/[0.05] px-2.5 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[9px] font-semibold uppercase tracking-wide text-violet-100">
                {zh ? 'T2 / T3 判别依据' : 'T2 / T3 discrimination'}
              </div>
              <span className="rounded border border-violet-300/30 px-1.5 py-0.5 font-mono text-[9px] text-violet-100">
                {result ? t23.lean : (zh ? '分析中' : 'Running')}
              </span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div className="rounded border border-sky-300/20 bg-sky-400/[0.06] px-2 py-1.5">
                <div className="text-[9px] font-semibold text-sky-100">{zh ? '支持偏 T2' : 'Favors T2'}</div>
                {t23.t2.length ? t23.t2.map((line) => (
                  <div key={line} className="mt-1 text-[9px] leading-relaxed text-slate-300">· {line}</div>
                )) : (
                  <div className="mt-1 text-[9px] text-slate-500">{zh ? '暂无明确支持项' : 'No clear support yet'}</div>
                )}
              </div>
              <div className="rounded border border-rose-300/20 bg-rose-400/[0.06] px-2 py-1.5">
                <div className="text-[9px] font-semibold text-rose-100">{zh ? '支持偏 T3' : 'Favors T3'}</div>
                {t23.t3.length ? t23.t3.map((line) => (
                  <div key={line} className="mt-1 text-[9px] leading-relaxed text-slate-300">· {line}</div>
                )) : (
                  <div className="mt-1 text-[9px] text-slate-500">{zh ? '暂无明确支持项' : 'No clear support yet'}</div>
                )}
              </div>
            </div>
            {t23.caveats.length ? (
              <div className="mt-2 rounded border border-amber-300/20 bg-black/20 px-2 py-1.5">
                <div className="text-[9px] font-semibold text-amber-100">{zh ? '反证 / 不足 / 需复核' : 'Counter-evidence / gaps / review'}</div>
                {t23.caveats.map((line) => (
                  <div key={line} className="mt-1 text-[9px] leading-relaxed text-slate-400">· {line}</div>
                ))}
              </div>
            ) : null}
            <div className="mt-1.5 text-[8px] leading-relaxed text-slate-500">
              {zh
                ? '层次与浆膜经确认后才可定 cT；几何边界代理不能单独区分 T2/T3。最终判断由医生复核。'
                : 'Confirmed wall/serosa evidence is required for cT; geometric proxies alone cannot separate T2/T3. Final judgment stays with the physician.'}
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-1.5 text-[9px]">
          <span className="inline-flex items-center gap-1 rounded border border-cyan-400/20 bg-cyan-400/5 px-2 py-1 text-cyan-200">
            <Dna size={10} /> {zh ? '区域特征' : 'Region features'} {dinoAvailable ? (zh ? '已就绪' : 'ready') : (zh ? '待补' : 'pending')}
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
            {zh ? '生成辅助意见后，这里显示病例信念、区域特征、七征象和跨模态证据。' : 'After assisted analysis, this shows case belief, region features, seven-sign, and cross-modal evidence.'}
          </div>
        )}
      </div>
    </section>
    {fullReportOpen ? (
      <div className="fixed inset-0 z-[250000] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm">
        <div className="relative flex max-h-[92vh] w-[min(1180px,96vw)] flex-col overflow-hidden rounded-xl border border-white/15 bg-[#080b0f] shadow-2xl">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-black px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                <FileText size={15} />
                {zh ? '辅助诊断完整报告' : 'Assisted diagnosis full report'}
              </div>
              <div className="mt-1 truncate text-[10px] text-slate-500">
                {result
                  ? `${result.session_id} / ${result.traces?.length || 0} traces / ${result.knowledge_context?.length || 0} knowledge snippets`
                  : (zh ? '当前帧尚未生成辅助意见' : 'Assisted opinion has not been generated for this frame')}
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
            {result ? (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="space-y-3">
                <div className="rounded-lg border border-emerald-300/20 bg-emerald-300/[0.04] p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.16em] text-emerald-200/70">
                        {zh ? '临床展示分期（待确认）' : 'Clinical display stage (pending)'}
                      </div>
                      <div className="mt-1 text-3xl font-black text-emerald-100">
                        {answerText(displayStage || 'cTx', zh)}
                      </div>
                      <div className="mt-1 text-[10px] text-emerald-100/70">
                        {evidenceConflict
                          ? (zh ? '存在征象冲突，已降为 cTx' : 'Sign conflicts detected; downgraded to cTx')
                          : !contoursReady
                            ? (zh ? '病灶/胃腔轮廓未确认，保持 cTx' : 'Lesion/lumen contours unconfirmed; stays cTx')
                            : summary.confidence != null
                              ? `${zh ? '置信度' : 'Confidence'} ${Math.round(summary.confidence * 100)}%`
                              : (result.report?.confidence
                                ? `${zh ? '置信度等级' : 'Confidence level'} ${result.report.confidence}`
                                : (zh ? '置信度待生成' : 'Confidence pending'))}
                      </div>
                    </div>
                    <div className="max-w-[65%] text-[11px] leading-relaxed text-slate-300">
                      {result.report?.reasoning || result.report?.llm_reasoning || (zh ? '暂无推理文本。' : 'No reasoning text returned.')}
                    </div>
                  </div>
                </div>
                <AnalysisProcess loading={false} steps={agentSteps} zh={zh} />
                {result.report?.llm_reasoning ? (
                  <div className="rounded-lg border border-sky-300/25 bg-sky-400/[0.05] p-3">
                    <div className="text-xs font-semibold text-sky-100">{zh ? '大模型推理输出' : 'LLM reasoning output'}</div>
                    <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-slate-300">{result.report.llm_reasoning}</div>
                  </div>
                ) : null}
                {result.report?.dynamic_report_draft?.full_text ? (
                  <div className="rounded-lg border border-white/10 bg-black/30 p-3">
                    <div className="text-xs font-semibold text-slate-100">{zh ? '大模型报告全文草稿' : 'LLM full report draft'}</div>
                    <div className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-slate-400">{result.report.dynamic_report_draft.full_text}</div>
                  </div>
                ) : null}
                <BoundaryExplainabilityCard result={result} zh={zh} />
                <div className="rounded-lg border border-violet-300/25 bg-violet-400/[0.05] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold text-violet-100">{zh ? 'T2 / T3 判别依据' : 'T2 / T3 discrimination'}</div>
                    <span className="rounded border border-violet-300/30 px-1.5 py-0.5 font-mono text-[9px] text-violet-100">{t23.lean}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div className="rounded border border-sky-300/20 bg-sky-400/[0.06] px-2 py-1.5">
                      <div className="text-[9px] font-semibold text-sky-100">{zh ? '支持偏 T2' : 'Favors T2'}</div>
                      {t23.t2.length ? t23.t2.map((line) => (
                        <div key={line} className="mt-1 text-[9px] leading-relaxed text-slate-300">· {line}</div>
                      )) : (
                        <div className="mt-1 text-[9px] text-slate-500">{zh ? '暂无明确支持项' : 'No clear support yet'}</div>
                      )}
                    </div>
                    <div className="rounded border border-rose-300/20 bg-rose-400/[0.06] px-2 py-1.5">
                      <div className="text-[9px] font-semibold text-rose-100">{zh ? '支持偏 T3' : 'Favors T3'}</div>
                      {t23.t3.length ? t23.t3.map((line) => (
                        <div key={line} className="mt-1 text-[9px] leading-relaxed text-slate-300">· {line}</div>
                      )) : (
                        <div className="mt-1 text-[9px] text-slate-500">{zh ? '暂无明确支持项' : 'No clear support yet'}</div>
                      )}
                    </div>
                  </div>
                  {t23.caveats.length ? (
                    <div className="mt-2 rounded border border-amber-300/20 bg-black/20 px-2 py-1.5">
                      <div className="text-[9px] font-semibold text-amber-100">{zh ? '反证 / 不足 / 需复核' : 'Counter-evidence / gaps / review'}</div>
                      {t23.caveats.map((line) => (
                        <div key={line} className="mt-1 text-[9px] leading-relaxed text-slate-400">· {line}</div>
                      ))}
                    </div>
                  ) : null}
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
                          <div className="mt-0.5 text-[8px] text-slate-600">{valueText(item.source_type)} / {valueText(item.model_version || 'model')}</div>
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
                      {' / '}
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
                        <span className="shrink-0 text-slate-500">{item.T_stage} / {Math.round(Number(item.similarity || 0) * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              </div>
            ) : (
              <div className="flex min-h-[260px] flex-col items-center justify-center rounded-xl border border-dashed border-cyan-400/20 bg-cyan-400/[0.03] p-6 text-center">
                <FileText size={24} className="text-cyan-300/70" />
                <div className="mt-3 text-sm font-semibold text-slate-100">
                  {zh ? '当前帧尚未生成完整报告' : 'No full report has been generated for this frame'}
                </div>
                <div className="mt-2 max-w-md text-[11px] leading-relaxed text-slate-500">
                  {zh
                    ? '当前证据面板已准备好。先生成辅助意见后，这里会显示病例信念、区域特征、七征象和跨模态证据。'
                    : 'The evidence panel is ready. Generate an assisted opinion to populate belief, region features, seven signs, and cross-modal evidence.'}
                </div>
                {onRun ? (
                  <button
                    type="button"
                    onClick={() => (onNextAction ? onNextAction(nextAction?.action_type) : onRun())}
                    disabled={loading}
                    className="reader-btn mt-4 border-cyan-400/30 text-cyan-200"
                  >
                    {loading ? <Loader2 size={11} className="animate-spin" /> : <ChevronRight size={11} />}
                    {loading
                      ? (zh ? '分析中' : 'Running')
                      : (zh ? '生成辅助意见' : 'Generate assisted opinion')}
                  </button>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>
    ) : null}
    </>
  );
}
