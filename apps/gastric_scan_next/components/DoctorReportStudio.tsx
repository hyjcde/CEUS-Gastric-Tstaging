'use client';

import Image from 'next/image';
import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clipboard,
  FileText,
  Gauge,
  Image as ImageIcon,
  Layers3,
  MessageSquareText,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  TableProperties,
} from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import type {
  AgentAnalysisResponse,
  AgentReportPack,
  AgentToolResult,
  Patient,
} from '@/types';
import type { SamReport } from '@/lib/reader/types';
import { CaseQuestioner } from '@/components/CaseQuestioner';

type StudioTab = 'overview' | 'evidence' | 'report' | 'review';
type ReviewAction = 'accept' | 'modify' | 'reject' | 'request_more_evidence';
type SubmitState = 'idle' | 'submitting' | 'submitted' | 'error';

interface DoctorReportStudioProps {
  patient: Patient | null;
  analysis: AgentAnalysisResponse | null;
  gcUsReport?: GcUsReportState | null;
  systemReport?: SamReport | null;
}

type Metric = {
  id: string;
  label: string;
  value: number;
  unit?: string;
  scale?: number | null;
  note?: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function displayValue(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === '') return '未评估';
  if (typeof value === 'number' && Number.isFinite(value)) return value.toFixed(digits);
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).join(', ');
  if (typeof value === 'object') {
    const record = asRecord(value);
    return record ? displayValue(record.label ?? record.value ?? record.status) : '未评估';
  }
  return String(value);
}

function percentValue(value: unknown): number {
  const parsed = asNumber(value);
  if (parsed === null) return 0;
  return Math.max(0, Math.min(100, parsed <= 1 ? parsed * 100 : parsed));
}

function normalizeStage(value: unknown): string {
  const raw = String(value || '').trim();
  if (/^T4[ab]?$/i.test(raw)) return 'T4+';
  return raw || '未输出';
}

function statusTone(status: unknown): string {
  const value = String(status || '').toLowerCase();
  if (value === 'available' || value === 'confirmed' || value === 'active') {
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200';
  }
  if (
    value === 'partial'
    || value === 'fallback'
    || value === 'suggested'
    || value === 'candidate'
    || value === 'accepted_pending_qa'
    || value === 'deferred'
  ) {
    return 'border-amber-400/30 bg-amber-400/10 text-amber-200';
  }
  if (value === 'unavailable' || value === 'missing' || value === 'rejected' || value === 'conflict') {
    return 'border-red-400/30 bg-red-400/10 text-red-200';
  }
  return 'border-slate-400/20 bg-slate-400/5 text-slate-300';
}

function statusLabel(status: unknown, zh: boolean): string {
  const value = String(status || '').toLowerCase();
  if (zh) {
    return {
      available: '可用',
      confirmed: '已确认',
      active: '已采纳',
      partial: '部分可用',
      fallback: '降级',
      suggested: '系统建议',
      candidate: '待审核',
      accepted_pending_qa: '已记录，待 QA',
      deferred: '已暂缓',
      unavailable: '不可用',
      missing: '缺失',
      rejected: '已拒绝',
      conflict: '冲突',
      not_assessed: '未评估',
      present: '可疑存在',
      absent: '文本未见',
      uncertain: '不确定',
    }[value] || String(status || '未评估');
  }
  return String(status || 'Not assessed');
}

function tool(result: AgentAnalysisResponse | null, key: string): AgentToolResult {
  const value = result?.tool_evidence?.[key as keyof AgentAnalysisResponse['tool_evidence']];
  return asRecord(value) as AgentToolResult || {};
}

function MetricBars({
  metrics,
  accent = 'cyan',
  zh,
}: {
  metrics: Metric[];
  accent?: 'cyan' | 'amber' | 'emerald' | 'rose';
  zh: boolean;
}) {
  const colors = {
    cyan: 'bg-cyan-400',
    amber: 'bg-amber-400',
    emerald: 'bg-emerald-400',
    rose: 'bg-rose-400',
  };
  if (!metrics.length) {
    return <div className="rounded-lg border border-dashed border-white/10 px-3 py-4 text-center text-[11px] text-slate-500">{zh ? '暂无可用的量化指标' : 'No quantitative metrics available'}</div>;
  }
  const fallbackMax = Math.max(...metrics.map((metric) => Math.abs(metric.value)), 1);
  return (
    <div className="space-y-3">
      {metrics.map((metric) => {
        const denominator = metric.scale && metric.scale > 0 ? metric.scale : fallbackMax;
        const width = Math.max(2, Math.min(100, Math.abs(metric.value) / denominator * 100));
        const valueText = metric.scale === 1
          ? `${Math.round(metric.value * 100)}%`
          : `${displayValue(metric.value)}${metric.unit ? ` ${metric.unit}` : ''}`;
        return (
          <div key={metric.id}>
            <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
              <span className="text-slate-300">{metric.label}</span>
              <span className="font-mono text-slate-100">{valueText}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/8">
              <div className={`h-full rounded-full ${colors[accent]} transition-all`} style={{ width: `${width}%` }} />
            </div>
            {metric.note ? <div className="mt-1 text-[9px] leading-relaxed text-slate-500">{metric.note}</div> : null}
          </div>
        );
      })}
    </div>
  );
}

function StageProbabilityChart({
  probabilities,
  zh,
}: {
  probabilities: Array<{ stage: string; value: number }>;
  zh: boolean;
}) {
  const colors: Record<string, string> = {
    T1: 'bg-emerald-400',
    T2: 'bg-cyan-400',
    T3: 'bg-amber-400',
    'T4+': 'bg-rose-400',
  };
  if (!probabilities.length) {
    return <div className="rounded-lg border border-dashed border-white/10 px-3 py-4 text-center text-[11px] text-slate-500">{zh ? '分类器未返回概率分布' : 'No classifier probabilities returned'}</div>;
  }
  return (
    <div className="space-y-3">
      {probabilities.map((item) => (
        <div key={item.stage}>
          <div className="mb-1 flex items-center justify-between text-[11px]">
            <span className="font-mono text-slate-300">{normalizeStage(item.stage)}</span>
            <span className="font-mono text-slate-100">{Math.round(percentValue(item.value))}%</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/8">
            <div
              className={`h-full rounded-full ${colors[normalizeStage(item.stage)] || 'bg-slate-400'}`}
              style={{ width: `${percentValue(item.value)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionTitle({
  icon,
  title,
  detail,
}: {
  icon: React.ReactNode;
  title: string;
  detail?: string;
}) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="flex items-center gap-2 text-sm font-bold text-white">
        <span className="text-cyan-300">{icon}</span>
        <span>{title}</span>
      </div>
      {detail ? <span className="text-[10px] text-slate-500">{detail}</span> : null}
    </div>
  );
}

function ArtifactStrip({ patient, analysis, zh }: { patient: Patient; analysis: AgentAnalysisResponse | null; zh: boolean }) {
  const artifacts = asRecord(analysis?.prediction_artifacts);
  const candidates = [
    { key: 'image', label: zh ? '原始影像' : 'Original', src: patient.image_url },
    { key: 'overlay', label: zh ? '分割叠加' : 'Overlay', src: patient.overlay_url },
    { key: 'wall', label: zh ? '壁层分析' : 'Wall analysis', src: artifacts?.real_wall_analysis_panel_url },
    { key: 'signs', label: zh ? '核心征象' : 'Core signs', src: artifacts?.gc_us_sign_panel_url },
    { key: 'dino', label: zh ? 'DINO 区域特征' : 'DINO region features', src: artifacts?.current_image_dino_feature_panel_url },
  ].filter((item): item is { key: string; label: string; src: string } => typeof item.src === 'string' && item.src.length > 0);

  if (!candidates.length) return null;
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {candidates.map((item) => (
        <div key={item.key} className="overflow-hidden rounded-lg border border-white/10 bg-black/35">
          <div className="relative h-28 bg-black">
            <Image src={item.src} alt={item.label} fill sizes="(max-width: 1024px) 50vw, 25vw" className="object-contain" unoptimized />
          </div>
          <div className="border-t border-white/10 px-2 py-1.5 text-[10px] text-slate-300">{item.label}</div>
        </div>
      ))}
    </div>
  );
}

export function DoctorReportStudio({
  patient,
  analysis,
  gcUsReport = null,
  systemReport = null,
}: DoctorReportStudioProps) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const [tab, setTab] = useState<StudioTab>('overview');
  const [doctorStage, setDoctorStage] = useState('');
  const [pathologyStage, setPathologyStage] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewAction, setReviewAction] = useState<ReviewAction>('modify');
  const [qualityFlags, setQualityFlags] = useState<string[]>([]);
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [submitMessage, setSubmitMessage] = useState('');
  const [candidateState, setCandidateState] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState(false);

  const report = analysis?.report;
  const pack = report?.report_pack as AgentReportPack | undefined;
  const classification = tool(analysis, 'classification');
  const morphology = tool(analysis, 'morphology');
  const wall = tool(analysis, 'wall_evidence');
  const reportTool = tool(analysis, 'report');
  const clinicalDecision = tool(analysis, 'clinical_decision');
  const recommendedStage = normalizeStage(report?.recommended_t_stage);
  const selectedDoctorStage = doctorStage || recommendedStage;

  const stageProbabilities = useMemo(() => {
    const fromPack = pack?.charts?.stage_probability || pack?.stage?.probabilities;
    if (fromPack?.length) return fromPack;
    const probabilities = classification.probabilities;
    if (!probabilities || typeof probabilities !== 'object' || Array.isArray(probabilities)) return [];
    return Object.entries(probabilities as Record<string, unknown>).map(([stage, value]) => ({
      stage: normalizeStage(stage),
      value: Number(value) || 0,
    }));
  }, [classification.probabilities, pack]);

  const boundaryMetrics = useMemo<Metric[]>(() => {
    const fromPack = pack?.charts?.boundary_geometry || [];
    if (fromPack.length) return fromPack;
    return [
      { id: 'boundary_irregularity', label: '边界不规则度', value: asNumber(morphology.boundary_irregularity) ?? 0, scale: 1, note: '轮廓几何代理，不等同于病理浸润深度' },
      { id: 'smoothness_index', label: '轮廓平滑度', value: asNumber(morphology.smoothness_index) ?? 0, scale: 1 },
      { id: 'roughness_index', label: '轮廓粗糙度', value: asNumber(morphology.roughness_index) ?? 0, scale: 1 },
      { id: 'solidity', label: '实心度', value: asNumber(morphology.solidity) ?? 0, scale: 1 },
      { id: 'lesion_area_ratio', label: '病灶面积占比', value: asNumber(morphology.lesion_area_ratio) ?? 0, scale: 1 },
    ].filter((metric) => metric.value > 0);
  }, [morphology, pack]);

  const wallMetrics = useMemo<Metric[]>(() => {
    const fromPack = pack?.charts?.wall_geometry || [];
    if (fromPack.length) return fromPack;
    const features = asRecord(wall.wall_features) || {};
    return [
      { id: 'fraction_outside_lumen', label: '胃腔外比例', value: asNumber(features.fraction_outside_lumen) ?? 0, scale: 1, note: 'SDF 几何代理，不是病理壁层结论' },
      { id: 'fraction_inside_lumen', label: '胃腔内比例', value: asNumber(features.fraction_inside_lumen) ?? 0, scale: 1 },
      { id: 'contact_arc_ratio', label: '胃腔接触弧比例', value: asNumber(features.contact_arc_ratio) ?? 0, scale: 1, note: '接触弧过低时代理质量下降' },
      { id: 'max_outward_depth', label: '最大向外距离', value: asNumber(features.max_outward_depth) ?? 0, unit: 'px' },
      { id: 'proxy_quality_score', label: '代理质量', value: asNumber(wall.proxy_quality_score) ?? 0, scale: 1 },
    ].filter((metric) => metric.value > 0);
  }, [pack, wall]);

  const modalityStatus = pack?.charts?.modality_status || [];
  const review = pack?.review || {
    required: Boolean(report?.uncertainty_flags?.length || report?.conflicting_evidence?.length),
    priority: 'routine',
    reasons: [...(report?.conflicting_evidence || []), ...(report?.uncertainty_flags || [])],
    next_actions: [],
  };
  const fluidEvidence = pack?.fluid_evidence || asRecord(reportTool.fluid_evidence) || { status: 'not_assessed' };
  const coreSigns = pack?.core_signs?.length
    ? pack.core_signs
    : gcUsReport
      ? [
          ['length', '肿瘤长径', gcUsReport.signs.size.length],
          ['thickness', '肿瘤厚度', gcUsReport.signs.size.thickness],
          ['layer_structure', '胃壁层次结构', gcUsReport.signs.layer_structure],
          ['morphology', '肿瘤形态', gcUsReport.signs.morphology],
          ['boundary', '肿瘤边界', gcUsReport.signs.boundary],
          ['growth_pattern', '生长方式', gcUsReport.signs.growth_pattern],
          ['serosa_change', '浆膜改变', gcUsReport.signs.serosa_change],
        ].map(([id, label, field]) => {
          const record = asRecord(field) || {};
          return { id: String(id), label: String(label), value: record.value, status: record.status, confidence: record.confidence, evidence_role: record.source };
        })
      : [];
  const evidenceMatrix = pack?.evidence_matrix || [];
  const candidates = report?.memory_update_candidates || [];
  const dynamicDraft = report?.dynamic_report_draft;
  const reportText = dynamicDraft?.full_text || gcUsReport?.report.prose || systemReport?.summary || '';
  const llmInvocation = analysis?.runtime_verification?.invocations?.find((item) => item.component === 'llm_report_synthesis');
  const llmNotes = pack?.llm_guardrail?.quality_notes || report?.llm_quality_notes || [];
  const managementAdvice = report?.management_advice || [];
  const missingModalities = Array.isArray(clinicalDecision.missing_modalities)
    ? clinicalDecision.missing_modalities.filter((item): item is string => typeof item === 'string')
    : [];
  const pathologyReport = patient?.report?.pathology_report?.trim() || '';
  const sourceReports = [
    { label: zh ? '胃镜报告' : 'Endoscopy report', value: patient?.report?.endoscopy_report },
    { label: zh ? '增强 CT 报告' : 'Enhanced CT report', value: patient?.report?.enhanced_ct_report || patient?.report?.ct_report },
    { label: zh ? '超声所见' : 'Ultrasound findings', value: patient?.report?.ultrasound_findings || patient?.report?.ultrasound_report },
    { label: zh ? '病理报告' : 'Pathology report', value: pathologyReport },
  ].filter((item): item is { label: string; value: string } => Boolean(item.value?.trim()));
  const spectralRoughness = asNumber(morphology.boundary_roughness);
  const tumorSize = patient?.clinical?.tumorSize;
  const clinicalRows = [
    { label: zh ? '病灶部位' : 'Lesion location', value: patient?.clinical?.location || '暂无来源' },
    {
      label: zh ? '长径 x 厚度' : 'Length x thickness',
      value: tumorSize
        ? `${tumorSize.length ?? '未评估'} x ${tumorSize.thickness ?? '未评估'} cm`
        : '未评估',
    },
    { label: 'CEA', value: patient?.clinical?.biomarkers.cea ?? '未提供' },
    { label: 'CA19-9', value: patient?.clinical?.biomarkers.ca199 ?? '未提供' },
  ];

  const copyReport = async () => {
    if (!reportText) return;
    try {
      await navigator.clipboard.writeText(reportText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const toggleQualityFlag = (flag: string) => {
    setQualityFlags((previous) => previous.includes(flag)
      ? previous.filter((item) => item !== flag)
      : [...previous, flag]);
  };

  const submitReview = async (action: ReviewAction) => {
    if (!patient || !analysis) return;
    setSubmitState('submitting');
    setSubmitMessage('');
    try {
      const response = await fetch('/api/agent/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patient.patient_id,
          case_id: patient.id,
          session_id: analysis.session_id,
          memory_store: analysis.memory_store_ref?.path,
          predicted_t_stage: report?.recommended_t_stage,
          final_t_stage: selectedDoctorStage === '未输出' ? report?.recommended_t_stage : selectedDoctorStage,
          gold_t_stage: pathologyStage || undefined,
          feedback_type: pathologyStage ? 'pathology_result' : 'doctor_correction',
          review_action: action,
          correction_text: reviewNote,
          quality_flags: qualityFlags,
          accepted_evidence: evidenceMatrix.filter((item) => item.status === 'available').map((item) => item.id),
          rejected_evidence: evidenceMatrix.filter((item) => item.status === 'conflict').map((item) => item.id),
          reviewer: 'workbench',
          confidence: report?.confidence,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.error || '反馈保存失败');
      setSubmitState('submitted');
      setSubmitMessage(zh ? '医生复核已记录，记忆仍处于候选状态，等待 QA 晋升。' : 'Review recorded. Memory remains a QA-gated candidate.');
    } catch (error) {
      setSubmitState('error');
      setSubmitMessage(error instanceof Error ? error.message : '反馈保存失败');
    }
  };

  const submitCandidateAction = async (recordId: string, action: 'accept' | 'reject' | 'defer') => {
    if (!patient || !analysis) return;
    setCandidateState((previous) => ({ ...previous, [recordId]: 'submitting' }));
    try {
      const response = await fetch('/api/agent/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patient.patient_id,
          case_id: patient.id,
          session_id: analysis.session_id,
          record_id: recordId,
          action,
          memory_store: analysis.memory_store_ref?.path,
          reviewer: 'workbench',
          predicted_t_stage: report?.recommended_t_stage,
          final_t_stage: selectedDoctorStage,
          correction_text: reviewNote,
        }),
      });
      if (!response.ok) throw new Error('memory action failed');
      setCandidateState((previous) => ({
        ...previous,
        [recordId]: action === 'reject'
          ? 'rejected'
          : action === 'accept'
            ? 'accepted_pending_qa'
            : 'deferred',
      }));
    } catch {
      setCandidateState((previous) => ({ ...previous, [recordId]: 'error' }));
    }
  };

  const tabs: Array<{ id: StudioTab; label: string; icon: React.ReactNode }> = [
    { id: 'overview', label: zh ? '总览' : 'Overview', icon: <Gauge size={14} /> },
    { id: 'evidence', label: zh ? '证据图谱' : 'Evidence map', icon: <TableProperties size={14} /> },
    { id: 'report', label: zh ? '报告正文' : 'Report', icon: <FileText size={14} /> },
    { id: 'review', label: zh ? '医生复核' : 'Review', icon: <Stethoscope size={14} /> },
  ];

  if (!patient) {
    return (
      <div className="rounded-xl border border-dashed border-white/10 bg-black/20 px-5 py-10 text-center text-sm text-slate-500">
        {zh ? '运行当前病例 Agent 后，这里会显示完整证据报告。' : 'Run the case Agent to populate the complete evidence report.'}
      </div>
    );
  }

  if (!analysis || !report) {
    return (
      <div className="space-y-4 text-[12px] text-slate-200">
        <div className="rounded-2xl border border-amber-300/20 bg-amber-300/[0.04] p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-amber-200/70">
                {zh ? '病例报告预览' : 'Case report preview'}
              </div>
              <h3 className="mt-1 text-xl font-bold text-white">
                {zh ? '等待 Agent 证据链' : 'Waiting for the Agent evidence chain'}
              </h3>
              <div className="mt-1 text-[10px] text-slate-500">
                {zh ? '现有临床资料和文字报告仍可供医生参考；运行 Agent 后自动补充结构化证据。' : 'Existing clinical data and source text remain available while structured evidence is pending.'}
              </div>
            </div>
            <span className="rounded border border-amber-300/25 bg-amber-300/10 px-2 py-1 text-[9px] text-amber-100">
              {zh ? '未运行 Agent' : 'Agent not run'}
            </span>
          </div>
        </div>

        <section className="rounded-2xl border border-cyan-300/20 bg-[linear-gradient(135deg,rgba(8,37,53,0.42),rgba(6,10,15,0.94))] p-5">
          <SectionTitle icon={<MessageSquareText size={15} />} title={zh ? '自然语言报告输出' : 'Natural-language report output'} detail={zh ? '当前已加载的报告文本' : 'Currently loaded report text'} />
          <div className="whitespace-pre-wrap rounded-xl border border-white/10 bg-black/35 p-4 text-[13px] leading-7 text-slate-200">
            {reportText || patient.report?.ultrasound_impression || patient.report?.ultrasound_report || (zh ? '暂无自然语言报告正文。' : 'No natural-language report is available.')}
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 lg:col-span-2">
            <SectionTitle icon={<FileText size={15} />} title={zh ? '临床辅助资料' : 'Clinical auxiliary data'} detail={zh ? '仅供医生参考' : 'Physician reference only'} />
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {clinicalRows.map((row) => (
                <div key={row.label} className="rounded-lg border border-white/8 bg-black/20 p-3">
                  <div className="text-[10px] text-slate-500">{row.label}</div>
                  <div className="mt-1 font-mono text-[12px] text-slate-100">{String(row.value)}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
            <SectionTitle icon={<Sparkles size={15} />} title={zh ? '频谱特征' : 'Spectral feature'} detail={zh ? '边界高频代理' : 'Boundary high-frequency proxy'} />
            <div className="text-3xl font-black text-amber-100">
              {spectralRoughness == null ? '未评估' : spectralRoughness.toFixed(2)}
            </div>
            <div className="mt-2 text-[10px] leading-relaxed text-amber-100/70">
              {zh ? '当前病例尚未返回频谱粗糙度。仓库未发现独立 Fourier 模型或频域服务。' : 'No spectral roughness was returned. No independent Fourier model or frequency-domain service is available.'}
            </div>
          </div>
        </div>

        <details open={Boolean(pathologyReport)} className="rounded-2xl border border-rose-300/20 bg-rose-300/[0.04]">
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-bold text-rose-100">
            <span className="flex items-center justify-between gap-3">
              <span>{zh ? '病理与原始报告资料' : 'Pathology and source reports'}</span>
              <span className="rounded border border-rose-300/25 bg-rose-300/10 px-2 py-1 text-[9px] font-normal text-rose-100">
                {zh ? '后验资料，不参与术前自动分期' : 'Retrospective, excluded from preoperative staging'}
              </span>
            </span>
          </summary>
          <div className="space-y-3 border-t border-rose-300/15 p-5">
            {sourceReports.length ? sourceReports.map((item) => (
              <div key={item.label} className="rounded-xl border border-white/8 bg-black/25 p-3">
                <div className="mb-1 text-[10px] font-semibold text-rose-100">{item.label}</div>
                <div className="whitespace-pre-wrap text-[11px] leading-relaxed text-slate-300">{item.value}</div>
              </div>
            )) : (
              <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-center text-[11px] text-slate-500">
                {zh ? '当前病例未挂接原始报告或病理文本。' : 'No source report or pathology text is attached.'}
              </div>
            )}
            <div className="text-[10px] leading-relaxed text-rose-100/70">
              {zh ? '病理内容可用于医生复核和反馈登记，不会自动改写影像模型的术前结论。' : 'Pathology can be recorded for physician review and feedback, but does not rewrite the imaging model preoperative conclusion.'}
            </div>
          </div>
        </details>

        <CaseQuestioner patient={patient} analysis={null} reportText={reportText} zh={zh} />
      </div>
    );
  }

  return (
    <div className="space-y-4 text-[12px] text-slate-200">
      <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center gap-1 rounded-xl border border-white/10 bg-[#0c1118]/95 p-1.5 shadow-xl backdrop-blur">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-semibold transition ${tab === item.id ? 'bg-cyan-400/15 text-cyan-100 ring-1 ring-cyan-300/30' : 'text-slate-500 hover:bg-white/5 hover:text-slate-200'}`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
        <div className="ml-auto hidden items-center gap-1.5 px-2 text-[10px] text-slate-500 md:flex">
          <ShieldAlert size={13} className={review.required ? 'text-amber-300' : 'text-emerald-300'} />
          {review.required ? (zh ? '需人工复核' : 'Review required') : (zh ? '常规复核' : 'Routine review')}
        </div>
      </div>

      {tab === 'overview' ? (
        <div className="space-y-4">
          <div className={`grid gap-4 rounded-2xl border p-5 lg:grid-cols-[1.1fr_1fr] ${review.required ? 'border-amber-300/30 bg-[linear-gradient(120deg,rgba(120,72,12,0.28),rgba(8,14,20,0.95))]' : 'border-emerald-300/25 bg-[linear-gradient(120deg,rgba(8,75,63,0.28),rgba(8,14,20,0.95))]'}`}>
            <div>
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-slate-500">
                <Stethoscope size={13} />
                {zh ? '病例级 T 分期辅助结论' : 'Case-level T-staging support'}
              </div>
              <div className="flex items-end gap-4">
                <div className="text-6xl font-black tracking-tight text-white">{recommendedStage}</div>
                <div className="pb-2">
                  <div className={`rounded-full border px-2.5 py-1 text-[11px] ${statusTone(review.required ? 'partial' : 'available')}`}>
                    {review.required ? (zh ? '证据不足或存在冲突' : 'Conflict or incomplete evidence') : (zh ? '证据链可复核' : 'Evidence chain reviewable')}
                  </div>
                  <div className="mt-2 text-[11px] text-slate-400">
                    {zh ? '置信度' : 'Confidence'}: <span className="font-semibold text-white">{report.confidence}</span>
                    {pack?.stage?.top_gap != null ? `, top gap ${pack.stage.top_gap.toFixed(2)}` : ''}
                  </div>
                </div>
              </div>
              <p className="mt-4 max-w-2xl text-[13px] leading-6 text-slate-300">
                {report.reasoning || (zh ? '当前病例已完成结构化证据融合，仍需医生结合原始影像复核。' : 'Structured evidence fusion completed. Review the original images before signing.')}
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-black/25 p-4">
              <SectionTitle icon={<Gauge size={15} />} title={zh ? 'T 分期概率分布' : 'T-stage probability'} />
              <StageProbabilityChart probabilities={stageProbabilities} zh={zh} />
            </div>
          </div>

          <ArtifactStrip patient={patient} analysis={analysis} zh={zh} />

          <section className="rounded-2xl border border-cyan-300/20 bg-[linear-gradient(135deg,rgba(8,37,53,0.42),rgba(6,10,15,0.94))] p-5">
            <SectionTitle
              icon={<MessageSquareText size={15} />}
              title={zh ? '自然语言报告输出' : 'Natural-language report output'}
              detail={dynamicDraft?.generated_by || (zh ? '规则与证据融合' : 'Evidence and rule fusion')}
            />
            <div className="whitespace-pre-wrap rounded-xl border border-white/10 bg-black/35 p-4 text-[13px] leading-7 text-slate-200">
              {reportText || (zh ? '暂无自然语言报告正文。请先运行当前病例 Agent。' : 'No natural-language report is available. Run the case Agent first.')}
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 lg:col-span-2">
              <SectionTitle icon={<FileText size={15} />} title={zh ? '临床辅助资料' : 'Clinical auxiliary data'} detail={zh ? '仅供医生参考' : 'Physician reference only'} />
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {clinicalRows.map((row) => (
                  <div key={row.label} className="rounded-lg border border-white/8 bg-black/20 p-3">
                    <div className="text-[10px] text-slate-500">{row.label}</div>
                    <div className="mt-1 font-mono text-[12px] text-slate-100">{String(row.value)}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
              <SectionTitle icon={<Sparkles size={15} />} title={zh ? '频谱特征' : 'Spectral feature'} detail={zh ? '边界高频代理' : 'Boundary high-frequency proxy'} />
              <div className="text-3xl font-black text-amber-100">
                {spectralRoughness == null ? '未评估' : spectralRoughness.toFixed(2)}
              </div>
              <div className="mt-2 text-[10px] leading-relaxed text-amber-100/70">
                {zh
                  ? '当前数据契约提供边界频谱粗糙度代理。仓库未发现独立 Fourier 模型或频域服务，因此不把该值解释为独立 Fourier 结论。'
                  : 'The current contract provides a boundary spectral roughness proxy. No independent Fourier model or frequency-domain service is available.'}
              </div>
            </div>
          </div>

          <details open={Boolean(pathologyReport)} className="rounded-2xl border border-rose-300/20 bg-rose-300/[0.04]">
            <summary className="cursor-pointer list-none px-5 py-4 text-sm font-bold text-rose-100">
              <span className="flex items-center justify-between gap-3">
                <span>{zh ? '病理与原始报告资料' : 'Pathology and source reports'}</span>
                <span className="rounded border border-rose-300/25 bg-rose-300/10 px-2 py-1 text-[9px] font-normal text-rose-100">
                  {zh ? '后验资料，不参与术前自动分期' : 'Retrospective, excluded from preoperative staging'}
                </span>
              </span>
            </summary>
            <div className="space-y-3 border-t border-rose-300/15 p-5">
              {sourceReports.length ? (
                sourceReports.map((item) => (
                  <div key={item.label} className="rounded-xl border border-white/8 bg-black/25 p-3">
                    <div className="mb-1 text-[10px] font-semibold text-rose-100">{item.label}</div>
                    <div className="whitespace-pre-wrap text-[11px] leading-relaxed text-slate-300">{item.value}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-center text-[11px] text-slate-500">
                  {zh ? '当前病例未挂接原始报告或病理文本。' : 'No source report or pathology text is attached.'}
                </div>
              )}
              <div className="text-[10px] leading-relaxed text-rose-100/70">
                {zh ? '病理内容可用于医生复核和反馈登记，不会自动改写影像模型的术前结论。' : 'Pathology can be recorded for physician review and feedback, but does not rewrite the imaging model preoperative conclusion.'}
              </div>
            </div>
          </details>

          <CaseQuestioner patient={patient} analysis={analysis} reportText={reportText} zh={zh} />

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 xl:col-span-2">
              <SectionTitle icon={<Layers3 size={15} />} title={zh ? '证据可用性' : 'Evidence availability'} detail={zh ? `${modalityStatus.filter((item) => item.status === 'available').length}/${modalityStatus.length} 项可用` : `${modalityStatus.filter((item) => item.status === 'available').length}/${modalityStatus.length} available`} />
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {modalityStatus.map((item) => (
                  <div key={item.id} className="rounded-lg border border-white/8 bg-black/20 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[11px] text-slate-300">{item.label}</span>
                      <span className={`rounded border px-1.5 py-0.5 text-[9px] ${statusTone(item.status)}`}>{statusLabel(item.status, zh)}</span>
                    </div>
                    <div className="mt-2 truncate text-[10px] text-slate-500">{displayValue(item.detail)}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className={`rounded-xl border p-4 ${review.required ? 'border-amber-300/25 bg-amber-300/5' : 'border-emerald-300/20 bg-emerald-300/5'}`}>
              <SectionTitle icon={review.required ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />} title={zh ? '复核重点' : 'Review focus'} />
              <div className="space-y-2">
                {(review.reasons || []).slice(0, 4).map((reason, index) => (
                  <div key={`${reason}-${index}`} className="flex gap-2 text-[11px] leading-relaxed text-slate-300">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300" />
                    <span>{reason}</span>
                  </div>
                ))}
                {(review.next_actions || []).slice(0, 3).map((action, index) => (
                  <div key={`${action}-${index}`} className="flex gap-2 text-[11px] leading-relaxed text-cyan-100">
                    <Check size={13} className="mt-0.5 shrink-0" />
                    <span>{action}</span>
                  </div>
                ))}
                {!review.reasons?.length && !review.next_actions?.length ? <div className="text-[11px] text-slate-500">{zh ? '暂无额外复核提示。' : 'No additional review flags.'}</div> : null}
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<MessageSquareText size={15} />} title={zh ? '腹腔积液/游离液' : 'Free fluid'} />
              <div className={`rounded-lg border px-3 py-3 ${statusTone(fluidEvidence.status)}`}>
                <div className="text-lg font-bold">{statusLabel(fluidEvidence.status, zh)}</div>
                <div className="mt-1 text-[10px] leading-relaxed opacity-80">{typeof fluidEvidence.note === 'string' ? fluidEvidence.note : (zh ? '仅由报告文本线索提供，未提及不等于阴性。' : 'Text cue only; absence of text is not a negative finding.')}</div>
              </div>
              {Array.isArray(fluidEvidence.matched_terms) && fluidEvidence.matched_terms.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {fluidEvidence.matched_terms.map((item: string) => <span key={item} className="rounded bg-white/5 px-2 py-1 text-[10px] text-slate-400">{item}</span>)}
                </div>
              ) : null}
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<Sparkles size={15} />} title={zh ? 'LLM 服务护栏' : 'LLM guardrail'} />
              <div className="space-y-2 text-[11px] leading-relaxed">
                <div className="flex items-center justify-between gap-2"><span className="text-slate-500">角色</span><span className="text-cyan-100">{zh ? '语言层润色' : 'Language refinement only'}</span></div>
                <div className="flex items-center justify-between gap-2"><span className="text-slate-500">状态</span><span className={`rounded border px-1.5 py-0.5 ${statusTone(llmInvocation?.status === 'ok' ? 'available' : 'partial')}`}>{llmInvocation?.status === 'ok' ? (zh ? '已调用' : 'Called') : (zh ? '规则兜底' : 'Rule fallback')}</span></div>
                <div className="border-t border-white/8 pt-2 text-slate-400">{zh ? 'LLM 不拥有 T 分期、置信度、测量值或病理结论。' : 'The LLM does not own stage, confidence, measurements, or pathology.'}</div>
                {llmNotes.slice(0, 2).map((note) => <div key={note} className="text-amber-100/80">{note}</div>)}
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<RefreshCw size={15} />} title={zh ? '记忆闭环状态' : 'Memory loop'} />
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-lg bg-black/20 p-2"><div className="text-slate-500">{zh ? '已应用规则' : 'Rules applied'}</div><div className="mt-1 font-mono text-white">{pack?.memory_loop?.active_rules_used?.length || report.active_rules_used?.length || 0}</div></div>
                <div className="rounded-lg bg-black/20 p-2"><div className="text-slate-500">{zh ? '候选记忆' : 'Candidates'}</div><div className="mt-1 font-mono text-white">{candidates.length}</div></div>
              </div>
              <div className="mt-2 text-[10px] leading-relaxed text-slate-500">{zh ? '医生反馈先进入候选记忆，经过 QA 和离线回放后才可晋升。' : 'Feedback enters candidate memory first and requires QA and replay before promotion.'}</div>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'evidence' ? (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<TableProperties size={15} />} title={zh ? '边界和形态统计' : 'Boundary and morphology'} detail={zh ? 'mask-derived proxy' : 'mask-derived proxy'} />
              <MetricBars metrics={boundaryMetrics} accent="cyan" zh={zh} />
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<Layers3 size={15} />} title={zh ? '胃腔和壁层统计' : 'Lumen and wall geometry'} detail={String(wall.penetration_risk || 'unknown')} />
              <MetricBars metrics={wallMetrics} accent="amber" zh={zh} />
              {Array.isArray(wall.quality_flags) && wall.quality_flags.length ? (
                <div className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/5 p-2 text-[10px] leading-relaxed text-amber-100">{wall.quality_flags.join('，')}</div>
              ) : null}
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <SectionTitle icon={<TableProperties size={15} />} title={zh ? '七项核心影像征象' : 'Seven core imaging signs'} detail={zh ? '每项保留来源和状态' : 'Status and provenance preserved'} />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] border-collapse text-left text-[11px]">
                <thead><tr className="border-b border-white/10 text-slate-500"><th className="px-2 py-2 font-medium">{zh ? '征象' : 'Sign'}</th><th className="px-2 py-2 font-medium">{zh ? '值' : 'Value'}</th><th className="px-2 py-2 font-medium">{zh ? '状态' : 'Status'}</th><th className="px-2 py-2 font-medium">{zh ? '置信度' : 'Confidence'}</th><th className="px-2 py-2 font-medium">{zh ? '来源/说明' : 'Source/note'}</th></tr></thead>
                <tbody>
                  {coreSigns.map((item) => (
                    <tr key={String(item.id)} className="border-b border-white/5">
                      <td className="px-2 py-2 text-slate-200">{String(item.label || item.id)}</td>
                      <td className="px-2 py-2 text-slate-300">
                        {displayValue(item.value)}
                        {typeof asRecord(item)?.unit === 'string' ? ` ${asRecord(item)?.unit}` : ''}
                      </td>
                      <td className="px-2 py-2"><span className={`rounded border px-1.5 py-0.5 text-[9px] ${statusTone(item.status)}`}>{statusLabel(item.status, zh)}</span></td>
                      <td className="px-2 py-2 font-mono text-slate-300">{item.confidence == null ? '—' : `${Math.round(percentValue(item.confidence))}%`}</td>
                      <td className="max-w-[260px] px-2 py-2 text-slate-500">{displayValue(asRecord(item)?.note || asRecord(item)?.evidence_role)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <SectionTitle icon={<ShieldAlert size={15} />} title={zh ? '证据矩阵和冲突' : 'Evidence matrix and conflicts'} />
            <div className="grid gap-2 lg:grid-cols-2">
              {evidenceMatrix.map((item) => (
                <div key={item.id} className="rounded-lg border border-white/8 bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-200">{item.label}</span>
                    <span className={`rounded border px-1.5 py-0.5 text-[9px] ${statusTone(item.status)}`}>{statusLabel(item.status, zh)}</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3 text-[11px]">
                    <span className="text-slate-500">{displayValue(item.source)}</span>
                    <span className="font-mono text-cyan-100">{displayValue(item.value)}</span>
                  </div>
                  {item.supports?.length ? <div className="mt-2 text-[10px] leading-relaxed text-emerald-200/80">{zh ? '支持' : 'Supports'}: {item.supports.join('，')}</div> : null}
                  {item.refutes?.length ? <div className="mt-1 text-[10px] leading-relaxed text-rose-200/80">{zh ? '反驳' : 'Refutes'}: {item.refutes.join('，')}</div> : null}
                </div>
              ))}
            </div>
            {report.conflicting_evidence?.length ? (
              <div className="mt-3 rounded-lg border border-rose-300/20 bg-rose-300/5 p-3 text-[11px] leading-relaxed text-rose-100">
                {report.conflicting_evidence.map((item) => <div key={item}>- {item}</div>)}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {tab === 'report' ? (
        <div className="space-y-4">
          <div className="rounded-2xl border border-cyan-300/20 bg-[linear-gradient(135deg,rgba(8,37,53,0.5),rgba(6,10,15,0.95))] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-300/70">{zh ? '医生复核报告草稿' : 'Clinician review draft'}</div>
                <h3 className="mt-1 text-xl font-bold text-white">{dynamicDraft?.title || (zh ? '胃癌超声多模态辅助诊断报告' : 'Multimodal gastric ultrasound report')}</h3>
                <div className="mt-1 text-[10px] text-slate-500">{zh ? '结构化证据生成，保留草稿状态，未经医生签发。' : 'Evidence-bound draft, not finalized until physician sign-off.'}</div>
              </div>
              <button type="button" onClick={() => void copyReport()} className="flex items-center gap-1.5 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-[11px] text-cyan-100 hover:bg-cyan-300/20">
                {copied ? <Check size={13} /> : <Clipboard size={13} />}
                {copied ? (zh ? '已复制' : 'Copied') : (zh ? '复制正文' : 'Copy text')}
              </button>
            </div>
            <div className="mt-5 rounded-xl border border-white/10 bg-black/35 p-4">
              {dynamicDraft?.sections?.length ? (
                <div className="space-y-4">
                  {dynamicDraft.sections.map((section) => (
                    <section key={section.heading} className="border-l-2 border-cyan-300/40 pl-3">
                      <h4 className="text-[12px] font-bold text-cyan-100">{section.heading}</h4>
                      <div className="mt-1 space-y-1 text-[13px] leading-7 text-slate-200">
                        {section.lines.map((line) => <p key={line}>{line}</p>)}
                      </div>
                      {section.evidence_refs?.length ? <div className="mt-1 text-[9px] text-slate-600">evidence: {section.evidence_refs.join(', ')}</div> : null}
                    </section>
                  ))}
                </div>
              ) : (
                <pre className="whitespace-pre-wrap font-sans text-[13px] leading-7 text-slate-200">{reportText || (zh ? '暂无报告正文。' : 'No report text yet.')}</pre>
              )}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<Stethoscope size={15} />} title={zh ? '临床决策支持' : 'Clinical decision support'} />
              <div className="space-y-3">
                {clinicalDecision.recommendation ? <div className="rounded-lg border border-cyan-300/20 bg-cyan-300/5 p-3 leading-relaxed text-cyan-50">{String(clinicalDecision.recommendation)}</div> : null}
                {managementAdvice.map((item) => <div key={item.action} className="rounded-lg border border-white/8 bg-black/20 p-3"><div className="font-semibold text-slate-200">{item.action}</div>{item.basis?.length ? <div className="mt-1 text-[10px] text-slate-500">{item.basis.join('，')}</div> : null}</div>)}
                {missingModalities.map((item) => <div key={item} className="flex gap-2 text-[11px] text-amber-100"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{item}</div>)}
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<Sparkles size={15} />} title={zh ? '语言层复述和限制' : 'Language-layer refinement'} />
              <div className="rounded-lg border border-white/8 bg-black/20 p-3 text-[11px] leading-relaxed text-slate-300">{report.llm_reasoning || report.reasoning}</div>
              {llmNotes.length ? <div className="mt-3 space-y-1.5">{llmNotes.map((note) => <div key={note} className="text-[10px] text-amber-100/80">- {note}</div>)}</div> : null}
              <div className="mt-3 rounded-lg border border-amber-300/15 bg-amber-300/5 p-3 text-[10px] leading-relaxed text-amber-100/80">{zh ? '报告文本不能把自由文本、几何代理或病理后验直接写成确定 T 分期。' : 'Free text, geometry proxies, and pathology hindsight cannot be written as a definite T stage.'}</div>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'review' ? (
        <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-4">
            <div className="rounded-2xl border border-emerald-300/20 bg-emerald-300/5 p-5">
              <SectionTitle icon={<Stethoscope size={15} />} title={zh ? '医生最终复核' : 'Physician review'} detail={zh ? '反馈进入 QA 候选记忆' : 'Feedback enters QA-gated memory'} />
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-[11px] text-slate-400">
                  {zh ? '医生确认的 cT' : 'Physician cT'}
                  <select value={doctorStage} onChange={(event) => setDoctorStage(event.target.value)} className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white">
                    <option value="">{zh ? `沿用 Agent: ${recommendedStage}` : `Use Agent: ${recommendedStage}`}</option>
                    {['T1', 'T2', 'T3', 'T4+'].map((stage) => <option key={stage} value={stage}>{stage}</option>)}
                  </select>
                </label>
                <label className="text-[11px] text-slate-400">
                  {zh ? '最终病理 T 分期，可选' : 'Final pathology T stage, optional'}
                  <select value={pathologyStage} onChange={(event) => setPathologyStage(event.target.value)} className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white">
                    <option value="">{zh ? '暂未获得' : 'Not available'}</option>
                    {['T1', 'T2', 'T3', 'T4+'].map((stage) => <option key={stage} value={stage}>{stage}</option>)}
                  </select>
                </label>
              </div>
              <label className="mt-3 block text-[11px] text-slate-400">
                {zh ? '复核意见和修改原因' : 'Review note and correction reason'}
                <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} className="mt-1.5 min-h-28 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-[12px] leading-relaxed text-white outline-none focus:border-cyan-300/40" placeholder={zh ? '说明采纳、修改、拒绝或证据不足的原因' : 'Explain acceptance, modification, rejection, or missing evidence'} />
              </label>
              <div className="mt-3 flex flex-wrap gap-2">
                {['图像质量不足', '边界不清', '壁层代理不可靠', '分期证据冲突', '缺少多切面', '缺少增强 CT'].map((flag) => (
                  <button key={flag} type="button" onClick={() => toggleQualityFlag(flag)} className={`rounded-full border px-2.5 py-1 text-[10px] transition ${qualityFlags.includes(flag) ? 'border-amber-300/40 bg-amber-300/15 text-amber-100' : 'border-white/10 text-slate-500 hover:text-slate-200'}`}>{flag}</button>
                ))}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {([
                  ['accept', '采纳 AI', 'border-emerald-300/30 text-emerald-100'],
                  ['modify', '修改确认', 'border-cyan-300/30 text-cyan-100'],
                  ['reject', '拒绝 AI', 'border-rose-300/30 text-rose-100'],
                  ['request_more_evidence', '证据不足', 'border-amber-300/30 text-amber-100'],
                ] as Array<[ReviewAction, string, string]>).map(([action, label, style]) => (
                  <button key={action} type="button" onClick={() => { setReviewAction(action); void submitReview(action); }} disabled={submitState === 'submitting'} className={`rounded-lg border bg-black/20 px-2 py-2.5 text-[11px] font-semibold hover:bg-white/5 disabled:opacity-50 ${style}`}>{label}</button>
                ))}
              </div>
              {submitState !== 'idle' ? <div className={`mt-3 rounded-lg border px-3 py-2 text-[11px] ${submitState === 'error' ? 'border-rose-300/25 bg-rose-300/5 text-rose-100' : 'border-emerald-300/25 bg-emerald-300/5 text-emerald-100'}`}>{submitState === 'submitting' ? (zh ? '正在记录复核...' : 'Recording review...') : submitMessage}</div> : null}
              <div className="mt-2 text-[9px] text-slate-600">{zh ? `当前动作：${reviewAction}` : `Current action: ${reviewAction}`}</div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<RefreshCw size={15} />} title={zh ? '记忆候选审核' : 'Memory candidate review'} detail={zh ? '不会自动改模型权重' : 'Never updates weights automatically'} />
              {candidates.length ? (
                <div className="space-y-3">
                  {candidates.map((candidate, index) => {
                    const persistedRecordId = typeof candidate.record_id === 'string' && candidate.record_id.trim()
                      ? candidate.record_id
                      : null;
                    const recordId = persistedRecordId || `candidate-${index}`;
                    const currentStatus = candidateState[recordId] || String(candidate.status || 'candidate');
                    const actionNote = currentStatus === 'accepted_pending_qa'
                      ? (zh ? '已记录为采纳意见，但不会直接晋升 active；等待离线回放和 QA。' : 'Recorded as accepted, but remains non-active until offline replay and QA.')
                      : currentStatus === 'deferred'
                        ? (zh ? '已暂缓，保留在候选队列。' : 'Deferred and retained in the candidate queue.')
                        : null;
                    return (
                      <div key={recordId} className="rounded-lg border border-white/8 bg-black/20 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="font-semibold text-slate-200">{String(candidate.title || candidate.record_type || 'case_episode')}</div>
                          <span className={`rounded border px-1.5 py-0.5 text-[9px] ${statusTone(currentStatus)}`}>{statusLabel(currentStatus, zh)}</span>
                        </div>
                        <div className="mt-2 text-[10px] leading-relaxed text-slate-500">{displayValue(candidate.recommended_t_stage || candidate.evidence || candidate.target_scenario)}</div>
                        <div className="mt-2 flex gap-1.5">
                          <button type="button" disabled={!persistedRecordId || currentStatus === 'submitting'} onClick={() => persistedRecordId && void submitCandidateAction(recordId, 'accept')} title={!persistedRecordId ? '候选尚未写入记忆库' : undefined} className="rounded border border-emerald-300/20 px-2 py-1 text-[10px] text-emerald-100 hover:bg-emerald-300/10 disabled:cursor-not-allowed disabled:opacity-40">接受</button>
                          <button type="button" disabled={!persistedRecordId || currentStatus === 'submitting'} onClick={() => persistedRecordId && void submitCandidateAction(recordId, 'reject')} title={!persistedRecordId ? '候选尚未写入记忆库' : undefined} className="rounded border border-rose-300/20 px-2 py-1 text-[10px] text-rose-100 hover:bg-rose-300/10 disabled:cursor-not-allowed disabled:opacity-40">拒绝</button>
                          <button type="button" disabled={!persistedRecordId || currentStatus === 'submitting'} onClick={() => persistedRecordId && void submitCandidateAction(recordId, 'defer')} title={!persistedRecordId ? '候选尚未写入记忆库' : undefined} className="rounded border border-white/10 px-2 py-1 text-[10px] text-slate-400 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40">暂缓</button>
                        </div>
                        {actionNote ? <div className="mt-2 text-[10px] leading-relaxed text-amber-100/80">{actionNote}</div> : null}
                      </div>
                    );
                  })}
                </div>
              ) : <div className="text-[11px] text-slate-500">{zh ? '当前病例没有新的记忆候选。' : 'No new memory candidates for this case.'}</div>}
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <SectionTitle icon={<ImageIcon size={15} />} title={zh ? '审计摘要' : 'Audit summary'} />
              <div className="space-y-2 text-[11px]">
                <div className="flex justify-between gap-3"><span className="text-slate-500">session</span><span className="max-w-[65%] truncate font-mono text-slate-300">{analysis.session_id}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">{zh ? '轨迹步骤' : 'Trace steps'}</span><span className="font-mono text-slate-300">{analysis.agent_steps?.length || analysis.traces?.length || 0}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">{zh ? '证据条目' : 'Evidence items'}</span><span className="font-mono text-slate-300">{analysis.evidence?.length || evidenceMatrix.length}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-500">{zh ? '当前病例' : 'Case token'}</span><span className="max-w-[65%] truncate font-mono text-slate-300">{patient.agent_report.case_token}</span></div>
              </div>
              <div className="mt-3 rounded-lg border border-cyan-300/15 bg-cyan-300/5 p-3 text-[10px] leading-relaxed text-cyan-100/80">{zh ? '这份复核记录会保留医生动作、证据选择、质量标记、病例轨迹和记忆候选，供后续 QA 回放。' : 'The review preserves physician actions, evidence selections, quality flags, trajectory, and memory candidates for QA replay.'}</div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

