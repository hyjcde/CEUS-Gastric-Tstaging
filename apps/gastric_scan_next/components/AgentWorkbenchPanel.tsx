'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import { Activity, AlertTriangle, ArrowRight, Brain, CheckCircle2, Clipboard, Database, FileSearch, FileText, Layers3, Loader2, Microscope, Network, RefreshCw, ScanSearch, ShieldCheck, Sparkles, Workflow, X } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import { AgentAnalysisResponse, AgentReportCue, AgentStep, AgentToolResult, Patient, RuntimeVerification } from '@/types';

interface AgentWorkbenchPanelProps {
  patient: Patient | null;
  onAnalysisComplete?: (result: AgentAnalysisResponse) => void;
}

type StepIcon = React.ComponentType<{ size?: number; className?: string }>;

interface AgentDisplayStep {
  key: string;
  title: string;
  detail: string;
  icon: StepIcon;
  output: string;
  backendStep?: AgentStep;
}

function formatUnknown(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'N/A';
  if (Array.isArray(value)) return value.map(formatUnknown).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function getTrustClass(trustLabel: unknown): string {
  if (trustLabel === 'trusted') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  if (trustLabel === 'avoid') return 'border-red-500/40 bg-red-500/10 text-red-200';
  if (trustLabel === 'caution') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  return 'border-slate-500/40 bg-slate-500/10 text-slate-200';
}

function getReportCues(reportTool?: AgentToolResult): AgentReportCue[] {
  const cues = reportTool?.report_cues;
  return Array.isArray(cues) ? cues as AgentReportCue[] : [];
}

function numericPercent(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  if (parsed <= 1) return Math.round(parsed * 100);
  return Math.round(parsed);
}

function confidenceTone(value?: string): string {
  if (value === 'high') return 'text-emerald-200 border-emerald-400/40 bg-emerald-400/10';
  if (value === 'medium') return 'text-amber-200 border-amber-400/40 bg-amber-400/10';
  if (value === 'low') return 'text-red-200 border-red-400/40 bg-red-400/10';
  return 'text-slate-200 border-slate-400/30 bg-slate-400/10';
}

function toolAvailability(tool?: AgentToolResult): 'available' | 'partial' | 'unavailable' {
  if (!tool) return 'unavailable';
  if (tool.available === true || tool.valid === true || tool.mask_available === true) return 'available';
  if (tool.error || tool.available === false) return 'unavailable';
  return 'partial';
}

function statusClass(status: string): string {
  if (status === 'available') return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200';
  if (status === 'partial') return 'border-amber-400/40 bg-amber-400/10 text-amber-200';
  return 'border-red-400/40 bg-red-400/10 text-red-200';
}

function getToolBackend(tool?: AgentToolResult): string {
  if (!tool) return 'N/A';
  return formatUnknown(tool.backend_id ?? tool.source ?? tool.roi_source ?? tool.available ?? tool.valid);
}

function getToolMetricRows(tool?: AgentToolResult, keys: string[] = []) {
  if (!tool) return [];
  return keys
    .filter((key) => tool[key] !== undefined && tool[key] !== null && tool[key] !== '')
    .map((key) => ({ key, value: tool[key] }));
}

function normalizeStage(stage: string): string {
  if (stage === 'T4a' || stage === 'T4b' || stage === 'T4') return 'T4+';
  return stage;
}

function getStepIcon(stepId: string) {
  if (stepId.includes('intake')) return Brain;
  if (stepId.includes('segmentation') || stepId.includes('localization')) return Layers3;
  if (stepId.includes('wall')) return Activity;
  if (stepId.includes('runtime') || stepId.includes('llm_report')) return ShieldCheck;
  if (stepId.includes('morphology')) return Activity;
  if (stepId.includes('classification')) return Microscope;
  if (stepId.includes('dino')) return Sparkles;
  if (stepId.includes('clinical')) return ShieldCheck;
  if (stepId.includes('report_text')) return FileSearch;
  if (stepId.includes('retrieval') || stepId.includes('memory')) return Database;
  if (stepId.includes('knowledge')) return RefreshCw;
  if (stepId.includes('synthesis')) return Network;
  if (stepId.includes('report')) return FileText;
  return Workflow;
}

function getStepOutputSummary(step: AgentStep): string {
  const outputs = step.outputs || {};
  if (outputs.recommended_t_stage) return `${outputs.recommended_t_stage} / ${outputs.confidence ?? 'unknown'}`;
  if (outputs.top1_stage) return `${outputs.top1_stage} ${outputs.top1_prob ?? ''}`.trim();
  if (outputs.current_image_dino_feature_panel_url) return 'DINO feature panel ready';
  if (outputs.roi_source) return `roi=${outputs.roi_source}`;
  if (outputs.lesion_area_ratio !== undefined) return `area=${outputs.lesion_area_ratio}`;
  if (outputs.clinical_risk_score !== undefined) return `risk=${outputs.clinical_risk_score}`;
  if (outputs.retrieved_count !== undefined) return `${outputs.retrieved_count} retrieved`;
  if (outputs.memory_candidate_count !== undefined) return `${outputs.memory_candidate_count} memory candidates`;
  if (outputs.available !== undefined) return `available=${outputs.available}`;
  return step.status;
}

function getStepVisualRef(step: AgentStep | undefined, keys: string[]): string | undefined {
  const refs = step?.visual_refs;
  if (!refs || typeof refs !== 'object') return undefined;
  return visualRefPick(refs as Record<string, unknown>, keys);
}

function visualRefPick(refs: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = refs[key];
    if (typeof value === 'string' && value) return value;
  }
  return undefined;
}

function VisualFrame({
  title,
  subtitle,
  src,
  children,
}: {
  title: string;
  subtitle?: string;
  src?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2">
        <div>
          <div className="text-xs font-bold text-slate-100">{title}</div>
          {subtitle && <div className="mt-0.5 text-[10px] text-slate-500">{subtitle}</div>}
        </div>
      </div>
      {src ? (
        <div className="relative h-44 bg-black">
          <Image src={src} alt={title} fill sizes="(max-width: 768px) 100vw, 50vw" className="object-contain" unoptimized />
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.08)_1px,transparent_1px)] bg-[size:24px_24px]" />
        </div>
      ) : (
        <div className="flex h-44 items-center justify-center bg-black text-xs text-slate-600">
          No image output
        </div>
      )}
      {children && <div className="border-t border-white/10 p-3">{children}</div>}
    </div>
  );
}

export function AgentWorkbenchPanel({ patient, onAnalysisComplete }: AgentWorkbenchPanelProps) {
  const { language, cohortYear, treatmentType, dataset } = useSettings();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [result, setResult] = useState<AgentAnalysisResponse | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [workbenchOpen, setWorkbenchOpen] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [streamLogs, setStreamLogs] = useState<string[]>([]);
  const [runtimeVerification, setRuntimeVerification] = useState<RuntimeVerification | null>(null);
  const [copiedDraft, setCopiedDraft] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setResult(null);
    setModalOpen(false);
    setWorkbenchOpen(false);
    setActiveStep(0);
    setLiveSteps([]);
    setStreamLogs([]);
    setRuntimeVerification(null);
    setCopiedDraft(false);
    setCopyError(null);
  }, [patient?.id]);

  useEffect(() => {
    if (!loading && liveSteps.length > 0) {
      setActiveStep(Math.max(liveSteps.length - 1, 0));
    }
  }, [liveSteps.length, loading]);

  const copyDraft = async () => {
    const draftText = result?.report.dynamic_report_draft?.full_text;
    if (!draftText) return;
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(draftText);
      setCopiedDraft(true);
      window.setTimeout(() => setCopiedDraft(false), 1600);
    } catch {
      setCopyError(language === 'zh' ? '浏览器暂未授权剪贴板，请先点击页面后重试。' : 'Clipboard permission is not available. Focus the page and retry.');
    }
  };

  const runAnalysis = async () => {
    if (!patient) return;
    setModalOpen(false);
    setWorkbenchOpen(true);
    setLoading(true);
    setError(null);
    setResult(null);
    setLiveSteps([]);
    setStreamLogs([]);
    setRuntimeVerification(null);
    setActiveStep(0);
    try {
      const response = await fetch('/api/agent/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient,
          dataset,
          cohortYear,
          treatmentType,
          sessionId,
        }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        throw new Error(errorPayload?.error || 'Agent analysis failed');
      }
      if (!response.body) {
        throw new Error('Agent stream is unavailable in this browser');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as {
            event?: string;
            step?: AgentStep;
            result?: AgentAnalysisResponse;
            verification?: RuntimeVerification;
            message?: string;
            error?: string;
          };

          if (event.event === 'agent_step' && event.step) {
            setLiveSteps((prev) => {
              const next = [...prev, event.step as AgentStep];
              setActiveStep(next.length - 1);
              return next;
            });
          } else if (event.event === 'log' && event.message) {
            setStreamLogs((prev) => [...prev.slice(-5), event.message as string]);
          } else if (event.event === 'runtime_verification' && event.verification) {
            setRuntimeVerification(event.verification);
          } else if (event.event === 'final' && event.result) {
            setResult(event.result);
            setSessionId(event.result.session_id);
            setLiveSteps(event.result.agent_steps || []);
            setRuntimeVerification(event.result.runtime_verification ?? event.verification ?? null);
            setActiveStep(Math.max((event.result.agent_steps?.length || 1) - 1, 0));
            onAnalysisComplete?.(event.result);
          } else if (event.event === 'error') {
            throw new Error(event.error || 'Agent analysis failed');
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLauncherClick = () => {
    if ((result || liveSteps.length > 0 || error) && !loading && !workbenchOpen) {
      setWorkbenchOpen(true);
      return;
    }
    void runAnalysis();
  };

  const classificationProbs = useMemo(() => {
    const probs = result?.tool_evidence.classification?.probabilities;
    if (!probs || typeof probs !== 'object' || Array.isArray(probs)) return [];
    return Object.entries(probs as Record<string, unknown>).map(([stage, value]) => ({
      stage,
      value: Number(value) || 0,
    }));
  }, [result]);

  const toolCards = useMemo(() => {
    if (!result) return [];
    return [
      {
        key: 'segmentation',
        title: language === 'zh' ? '分割 / ROI 定位' : 'Segmentation / ROI',
        icon: Layers3,
        tool: result.tool_evidence.segmentation,
        metrics: getToolMetricRows(result.tool_evidence.segmentation, ['roi_source', 'lesion_area_ratio', 'mask_available', 'image_height', 'image_width']),
      },
      {
        key: 'lumen',
        title: language === 'zh' ? '胃腔检测 (YOLO)' : 'Lumen detection',
        icon: ScanSearch,
        tool: result.tool_evidence.lumen_detection ?? { available: false },
        metrics: getToolMetricRows(result.tool_evidence.lumen_detection, ['lumen_detected', 'lumen_confidence', 'lumen_area_ratio']),
      },
      {
        key: 'wall',
        title: language === 'zh' ? '壁层证据 (SDF)' : 'Wall evidence',
        icon: Activity,
        tool: result.tool_evidence.wall_evidence ?? { available: false },
        metrics: getToolMetricRows(result.tool_evidence.wall_evidence, ['penetration_risk', 'evidence_source', 'available']),
      },
      {
        key: 'classification',
        title: language === 'zh' ? 'T 分期分类' : 'T-stage classifier',
        icon: Microscope,
        tool: result.tool_evidence.classification,
        metrics: getToolMetricRows(result.tool_evidence.classification, ['top1_stage', 'top1_prob', 'top2_stage', 'top2_prob', 'uncertainty']),
      },
      {
        key: 'morphology',
        title: language === 'zh' ? '形态学证据' : 'Morphology',
        icon: Activity,
        tool: result.tool_evidence.morphology,
        metrics: getToolMetricRows(result.tool_evidence.morphology, ['boundary_irregularity', 'lesion_area_ratio', 'convexity', 'solidity', 'compactness']),
      },
      {
        key: 'clinical',
        title: language === 'zh' ? '临床风险' : 'Clinical risk',
        icon: ShieldCheck,
        tool: result.tool_evidence.clinical,
        metrics: getToolMetricRows(result.tool_evidence.clinical, ['clinical_risk_score', 'factors_available', 'risk_factors', 'protective_factors']),
      },
      {
        key: 'report',
        title: language === 'zh' ? '报告文本线索' : 'Report cues',
        icon: FileSearch,
        tool: result.tool_evidence.report,
        metrics: getToolMetricRows(result.tool_evidence.report, ['sections_available', 'text_length', 'report_source']),
      },
      {
        key: 'memory',
        title: language === 'zh' ? '相似病例 memory' : 'Similar-case memory',
        icon: Database,
        tool: { available: result.similar_cases.length > 0, backend_id: 'FAISS / current_case_memory', trust_label: 'caution' },
        metrics: [
          { key: 'retrieved_cases', value: result.similar_cases.length },
          { key: 'majority_stage', value: result.report.similar_case_summary?.majority_stage },
        ],
      },
    ];
  }, [language, result]);

  const adaptiveSteps = useMemo<AgentDisplayStep[]>(() => {
    const backendSteps = liveSteps.length ? liveSteps : result?.agent_steps;
    if (backendSteps?.length) {
      return backendSteps.map((step) => ({
        key: step.step_id,
        title: step.title,
        detail: step.reasoning || step.intent,
        icon: getStepIcon(step.step_id),
        output: getStepOutputSummary(step),
        backendStep: step,
      }));
    }
    if (loading) return [];

    const patientId = patient?.patient_id ?? 'N/A';
    const hasRoi = Boolean(patient?.roi_url);
    const hasReport = Boolean(patient?.report && Object.values(patient.report).some(Boolean));
    const hasClinical = Boolean(patient?.clinical);
    const steps = [
      {
        key: 'intake',
        title: language === 'zh' ? '病例接入与资料盘点' : 'Case intake',
        detail: language === 'zh'
          ? `读取 ${patientId}，检查原图、ROI、标注、临床表和报告文本。`
          : `Reading ${patientId} and checking image, ROI, annotation, clinical table, and reports.`,
        icon: Brain,
        output: hasClinical ? (language === 'zh' ? '临床资料可用' : 'Clinical data available') : (language === 'zh' ? '临床资料不足' : 'Clinical data limited'),
      },
      {
        key: 'localize',
        title: language === 'zh' ? '定位模型判断病灶候选区' : 'Localization model selects lesion region',
        detail: language === 'zh'
          ? '先根据原图和既有 ROI 判断是否需要模型重新定位；如果 ROI 不足，则使用分割预测框补位。'
          : 'Use image and existing ROI first; if ROI is weak, fall back to model-predicted localization.',
        icon: Layers3,
        output: result ? `roi=${formatUnknown(result.tool_evidence.segmentation?.roi_source)}` : (hasRoi ? 'ROI ready' : 'ROI pending'),
      },
      {
        key: 'segment',
        title: language === 'zh' ? '分割模型生成病灶与胃壁证据' : 'Segmentation model extracts lesion evidence',
        detail: language === 'zh'
          ? '分割病灶区域，得到 mask、bbox、面积占比，并给后续形态学和分类模型提供输入。'
          : 'Produce mask, bbox, area ratio, and downstream morphology/classification inputs.',
        icon: Activity,
        output: result ? `area=${formatUnknown(result.tool_evidence.segmentation?.lesion_area_ratio)}` : 'mask running',
      },
      {
        key: 'classify',
        title: language === 'zh' ? 'T 分期模型输出概率分布' : 'T-stage model outputs probability distribution',
        detail: language === 'zh'
          ? '调用分类模型，不只看 top-1，也看 T2/T3 等相邻分期差距和不确定性。'
          : 'Call classifier and inspect top-1, adjacent-stage gap, and uncertainty.',
        icon: Microscope,
        output: result ? `${formatUnknown(result.tool_evidence.classification?.top1_stage)} ${formatUnknown(result.tool_evidence.classification?.top1_prob)}` : 'probability pending',
      },
      {
        key: 'crosscheck',
        title: language === 'zh' ? '临床与报告线索交叉校验' : 'Clinical and report cross-check',
        detail: language === 'zh'
          ? hasReport ? '抽取报告中的胃壁增厚、浆膜、侵犯等词，并与临床风险评分互相验证。' : '当前报告文本不足，Agent 自动降低文本证据权重。'
          : hasReport ? 'Extract report cues and compare with clinical risk.' : 'Report text is limited, so text evidence receives lower weight.',
        icon: FileSearch,
        output: result ? `risk=${formatUnknown(result.tool_evidence.clinical?.clinical_risk_score)}` : 'risk pending',
      },
      {
        key: 'memory',
        title: language === 'zh' ? '检索历史相似病例并投票' : 'Retrieve similar cases and vote',
        detail: language === 'zh'
          ? '用当前病例向量检索历史病例，观察相似病例真实 T 分期分布，而不是只看单模型结论。'
          : 'Retrieve historical cases and inspect the stage distribution instead of trusting one model.',
        icon: Database,
        output: result ? `${result.similar_cases.length} cases` : 'memory search',
      },
      {
        key: 'synthesis',
        title: language === 'zh' ? '多证据综合推理与冲突处理' : 'Multi-evidence synthesis',
        detail: language === 'zh'
          ? '把分类概率、分割质量、形态学、临床、报告、相似病例投票合并，标出冲突和需要人工复核处。'
          : 'Fuse classifier, segmentation quality, morphology, clinical data, reports, and similar-case voting.',
        icon: Network,
        output: result ? `${result.report.recommended_t_stage} / ${result.report.confidence}` : 'reasoning',
      },
      {
        key: 'report',
        title: language === 'zh' ? '生成动态报告草稿与 memory 候选' : 'Draft report and memory candidates',
        detail: language === 'zh'
          ? '生成可复制报告，同时把本次推理轨迹和医生后续反馈预留为 memory 候选。'
          : 'Generate copy-ready report and keep trace/feedback candidates for memory.',
        icon: FileText,
        output: result ? `${result.report.memory_update_candidates?.length ?? 0} memory candidates` : 'drafting',
      },
    ];
    return steps;
  }, [language, liveSteps, loading, patient, result]);

  const stageVoting = useMemo(() => {
    const stages = ['T1', 'T2', 'T3', 'T4+'];
    const votes: Record<string, number> = { T1: 0, T2: 0, T3: 0, 'T4+': 0 };
    const classification = result?.tool_evidence.classification;
    const probabilities = classification?.probabilities;
    if (probabilities && typeof probabilities === 'object' && !Array.isArray(probabilities)) {
      Object.entries(probabilities as Record<string, unknown>).forEach(([stage, value]) => {
        const normalized = normalizeStage(stage);
        if (normalized in votes) votes[normalized] += Number(value) || 0;
      });
    }

    const stageDistribution = result?.report.similar_case_summary?.stage_distribution ?? {};
    const similarTotal = Object.values(stageDistribution).reduce((sum, value) => sum + Number(value || 0), 0);
    Object.entries(stageDistribution).forEach(([stage, count]) => {
      const normalized = normalizeStage(stage);
      if (normalized in votes && similarTotal > 0) votes[normalized] += 0.35 * (Number(count) / similarTotal);
    });

    const clinicalRisk = Number(result?.tool_evidence.clinical?.clinical_risk_score);
    if (Number.isFinite(clinicalRisk)) {
      if (clinicalRisk >= 0.45) {
        votes.T3 += 0.2;
        votes['T4+'] += 0.1;
      } else if (clinicalRisk >= 0.25) {
        votes.T2 += 0.2;
        votes.T3 += 0.1;
      } else {
        votes.T1 += 0.1;
        votes.T2 += 0.12;
      }
    }

    const maxVote = Math.max(...Object.values(votes), 0.01);
    return stages.map((stage) => ({
      stage,
      vote: votes[stage],
      percent: Math.round((votes[stage] / maxVote) * 100),
    }));
  }, [result]);

  const evidenceStreams = useMemo(() => {
    if (!result) return [];
    return [
      {
        label: language === 'zh' ? '分类模型' : 'Classifier',
        value: formatUnknown(result.tool_evidence.classification?.top1_stage),
        weight: numericPercent(result.tool_evidence.classification?.top1_prob, 0),
      },
      {
        label: language === 'zh' ? '相似病例多数票' : 'Similar-case majority',
        value: formatUnknown(result.report.similar_case_summary?.majority_stage),
        weight: Math.min(result.similar_cases.length * 20, 100),
      },
      {
        label: language === 'zh' ? '临床风险' : 'Clinical risk',
        value: formatUnknown(result.tool_evidence.clinical?.clinical_risk_score),
        weight: numericPercent(result.tool_evidence.clinical?.clinical_risk_score, 0),
      },
      {
        label: language === 'zh' ? '分割质量' : 'Segmentation quality',
        value: formatUnknown(result.tool_evidence.segmentation?.roi_source),
        weight: result.tool_evidence.segmentation?.mask_available ? 90 : 45,
      },
      {
        label: language === 'zh' ? '报告线索' : 'Report cues',
        value: `${getReportCues(result.tool_evidence.report).length} cues`,
        weight: Math.min(getReportCues(result.tool_evidence.report).length * 25, 100),
      },
    ];
  }, [language, result]);

  const currentBackendStep = adaptiveSteps[activeStep]?.backendStep;
  const renderCurrentStepVisual = () => {
    if (!patient) return null;

    const stepId = currentBackendStep?.step_id || '';
    const outputs = currentBackendStep?.outputs || {};
    const refs = currentBackendStep?.visual_refs || {};
    const stepProbabilities = outputs.probabilities && typeof outputs.probabilities === 'object' && !Array.isArray(outputs.probabilities)
      ? Object.entries(outputs.probabilities as Record<string, unknown>).map(([stage, value]) => ({ stage, value: Number(value) || 0 }))
      : classificationProbs;
    const stageDistribution = outputs.stage_distribution && typeof outputs.stage_distribution === 'object' && !Array.isArray(outputs.stage_distribution)
      ? outputs.stage_distribution as Record<string, unknown>
      : result?.report.similar_case_summary?.stage_distribution ?? {};
    const similarCases = Array.isArray(outputs.similar_cases)
      ? outputs.similar_cases as Array<Record<string, unknown>>
      : result?.similar_cases ?? [];

    if (!currentBackendStep || stepId.includes('intake')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <VisualFrame title={language === 'zh' ? '当前病例原始超声' : 'Current case ultrasound'} subtitle={patient.id_short} src={patient.image_url} />
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">{language === 'zh' ? '病例资料盘点' : 'Case evidence inventory'}</div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
              {[
                ['image', patient.image_url ? 'available' : 'missing'],
                ['roi', patient.roi_url ? 'available' : 'missing'],
                ['overlay', patient.overlay_url ? 'available' : 'missing'],
                ['clinical', patient.clinical ? 'available' : 'missing'],
                ['report', patient.report ? 'attached' : 'missing'],
                ['frames', patient.frame_count ?? 'N/A'],
              ].map(([key, value]) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{key}</div>
                  <div className="mt-1 font-mono text-emerald-100">{formatUnknown(value)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('segmentation') || stepId.includes('localization')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
          <VisualFrame title={language === 'zh' ? '预测分割叠加图' : 'Predicted segmentation overlay'} subtitle="model-generated overlay" src={typeof refs.predicted_overlay_url === 'string' ? refs.predicted_overlay_url : patient.overlay_url || patient.image_url} />
          <VisualFrame title={language === 'zh' ? '预测 mask' : 'Predicted mask'} subtitle="binary model mask" src={typeof refs.predicted_mask_url === 'string' ? refs.predicted_mask_url : undefined} />
          <VisualFrame title={language === 'zh' ? '预测 ROI 裁剪' : 'Predicted ROI crop'} subtitle={formatUnknown(outputs.roi_source)} src={typeof refs.predicted_roi_url === 'string' ? refs.predicted_roi_url : patient.roi_url || patient.image_url}>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              {['roi_source', 'mask_available', 'lesion_area_ratio', 'image_height', 'image_width'].map((key) => (
                <div key={key} className="rounded bg-black/25 px-2 py-1">
                  <span className="text-slate-500">{key}</span>
                  <div className="truncate font-mono text-cyan-100">{formatUnknown(outputs[key])}</div>
                </div>
              ))}
            </div>
          </VisualFrame>
          <VisualFrame title={language === 'zh' ? '胃壁穿透风险热力图' : 'Wall penetration risk heatmap'} subtitle={language === 'zh' ? '由预测 mask / ROI 生成的胃壁风险代理图' : 'wall-risk proxy from predicted mask / ROI'} src={typeof refs.wall_penetration_heatmap_url === 'string' ? refs.wall_penetration_heatmap_url : undefined} />
        </div>
      );
    }

    if (stepId.includes('wall_evidence') || stepId.includes('wall_analysis')) {
      const panelMode = formatUnknown(outputs.wall_panel_mode);
      const panelSource = formatUnknown(outputs.real_wall_analysis_panel_source);
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <VisualFrame
            title={language === 'zh' ? '真实胃壁分析面板' : 'Real wall analysis panel'}
            subtitle={
              language === 'zh'
                ? `来源: ${panelMode} · ${panelSource}`
                : `source: ${panelMode} · ${panelSource}`
            }
            src={
              visualRefPick(refs, [
                'real_wall_analysis_panel_url',
                'wall_penetration_heatmap_url',
                'wall_layer_profile_url',
              ])
            }
          />
          <VisualFrame
            title={language === 'zh' ? '胃壁穿透风险热力图' : 'Wall penetration risk heatmap'}
            subtitle={language === 'zh' ? '预测 mask 驱动的风险代理' : 'mask-driven risk proxy'}
            src={typeof refs.wall_penetration_heatmap_url === 'string' ? refs.wall_penetration_heatmap_url : undefined}
          />
          <VisualFrame
            title={language === 'zh' ? '胃壁层剖面' : 'Wall layer profile'}
            subtitle={formatUnknown(outputs.wall_layer_profile_source)}
            src={typeof refs.wall_layer_profile_url === 'string' ? refs.wall_layer_profile_url : undefined}
          />
        </div>
      );
    }

    if (stepId.includes('morphology')) {
      const metrics = ['boundary_irregularity', 'lesion_area_ratio', 'convexity', 'solidity', 'compactness', 'aspect_ratio'];
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.9fr_0.9fr_1.2fr]">
          <VisualFrame
            title={language === 'zh' ? '真实胃壁分析面板' : 'Real wall analysis panel'}
            subtitle={
              language === 'zh'
                ? '优先磁盘已有 `*_analysis.png`，否则自动生成合成面板'
                : 'prefer on-disk `_analysis.png`, else stacked proxy panel'
            }
            src={
              visualRefPick(refs, [
                'real_wall_analysis_panel_url',
                'wall_penetration_heatmap_url',
                'wall_layer_profile_url',
              ])
            }
          />
          <VisualFrame title={language === 'zh' ? '胃壁层厚度剖面' : 'Gastric wall layer profile'} subtitle={language === 'zh' ? '沿 ROI 横向的相对壁层信号' : 'relative wall signal along ROI'} src={typeof refs.wall_layer_profile_url === 'string' ? refs.wall_layer_profile_url : undefined} />
          <div className="rounded-xl border border-lime-300/20 bg-lime-300/5 p-4">
            <div className="text-sm font-black text-lime-100">{language === 'zh' ? '形态学指标' : 'Morphology metrics'}</div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              {metrics.map((key) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-[10px] text-slate-500">{key}</div>
                  <div className="mt-1 font-mono text-lg font-black text-lime-100">{formatUnknown(outputs[key])}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('classification')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="space-y-4">
            <VisualFrame title={language === 'zh' ? '真实 DINO 多模态证据面板' : 'Real DINO multimodal evidence panel'} subtitle={language === 'zh' ? '来自 scripts/generate_clean_agent_case_visual_panels.py' : 'from scripts/generate_clean_agent_case_visual_panels.py'} src={typeof refs.real_dino_multimodal_panel_url === 'string' ? refs.real_dino_multimodal_panel_url : undefined} />
            <VisualFrame title={language === 'zh' ? '分类概率图' : 'Classification probability plot'} subtitle="model-generated probability plot" src={typeof refs.classification_probabilities_url === 'string' ? refs.classification_probabilities_url : undefined} />
          </div>
          <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/5 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-black text-emerald-100">{language === 'zh' ? 'T 分期概率输出' : 'T-stage probability output'}</div>
                <div className="mt-1 text-xs text-slate-500">{language === 'zh' ? '显示 top-1、top-2 和相邻分期不确定性。' : 'Shows top-1, top-2, and adjacent-stage uncertainty.'}</div>
              </div>
              <div className="rounded-xl border border-emerald-300/30 bg-emerald-300/10 px-4 py-2 text-right">
                <div className="text-2xl font-black text-emerald-100">{formatUnknown(outputs.top1_stage)}</div>
                <div className="text-[10px] text-emerald-100/70">{formatUnknown(outputs.top1_prob)}</div>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {stepProbabilities.map((item) => (
                <div key={`step-prob-${item.stage}`}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-mono text-slate-200">{item.stage}</span>
                    <span className="font-mono text-emerald-200">{numericPercent(item.value)}%</span>
                  </div>
                  <div className="h-4 overflow-hidden rounded-full bg-slate-900">
                    <div className="h-full rounded-full bg-linear-to-r from-emerald-300 via-cyan-300 to-lime-200" style={{ width: `${Math.min(numericPercent(item.value), 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('dino')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <VisualFrame
            title={language === 'zh' ? '当前图像真实 DINO 特征面板' : 'Current-image real DINO feature panel'}
            subtitle={language === 'zh' ? '来自 generate_external_source_dino_token_panels.py 的实际推理' : 'actual inference from generate_external_source_dino_token_panels.py'}
            src={typeof refs.current_image_dino_feature_panel_url === 'string' ? refs.current_image_dino_feature_panel_url : undefined}
          />
          <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
            <div className="text-sm font-black text-cyan-100">{language === 'zh' ? 'DINO 调用信息' : 'DINO call details'}</div>
            <div className="mt-4 space-y-3 text-xs">
              {['current_image_dino_model', 'current_image_dino_feature_panel_url', 'current_image_dino_error'].map((key) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{key}</div>
                  <div className="mt-1 break-words font-mono text-cyan-100">{formatUnknown(outputs[key])}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('clinical') || stepId.includes('report_text')) {
      const cueList = Array.isArray(outputs.report_cues) ? outputs.report_cues as Array<Record<string, unknown>> : getReportCues(result?.tool_evidence.report);
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
            <div className="text-sm font-black text-amber-100">{language === 'zh' ? '临床风险/校准' : 'Clinical risk calibration'}</div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
              {['clinical_risk_score', 'risk_factors', 'protective_factors', 'factors_available', 'sections_available', 'text_length'].map((key) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{key}</div>
                  <div className="mt-1 break-words font-mono text-amber-100">{formatUnknown(outputs[key])}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-sky-300/20 bg-sky-300/5 p-4">
            <div className="text-sm font-black text-sky-100">{language === 'zh' ? '报告文本线索' : 'Report text cues'}</div>
            <div className="mt-4 space-y-2">
              {cueList.length ? cueList.map((cue, idx) => (
                <div key={`cue-${idx}`} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs">
                  <div className="font-mono text-sky-100">{formatUnknown('cue' in cue ? cue.cue : '')}</div>
                  <div className="mt-1 text-slate-500">{formatUnknown('matched_terms' in cue ? cue.matched_terms : '')}</div>
                </div>
              )) : (
                <div className="rounded-lg border border-dashed border-white/10 p-4 text-xs text-slate-500">{language === 'zh' ? '当前未抽取到明确文本线索。' : 'No explicit report cues extracted.'}</div>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('retrieval')) {
      const total = Object.values(stageDistribution).reduce((sum: number, value) => sum + Number(value || 0), 0) || 1;
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
            <div className="text-sm font-black text-cyan-100">{language === 'zh' ? '相似病例 T 分期投票' : 'Similar-case T-stage vote'}</div>
            <div className="mt-4">
              <VisualFrame
                title={language === 'zh' ? 'DINO 区域相似度热力图' : 'DINO region similarity heatmap'}
                subtitle={language === 'zh' ? '基于当前 ROI / mask 的区域相似性提示' : 'Region similarity cue from current ROI / mask'}
                src={typeof refs.dino_similarity_heatmap_url === 'string' ? refs.dino_similarity_heatmap_url : undefined}
              />
            </div>
            <div className="mt-5 space-y-4">
              {['T1', 'T2', 'T3', 'T4+'].map((stage) => {
                const raw = Number(stageDistribution[stage] || stageDistribution[stage.replace('+', '')] || 0);
                const percent = Math.round((raw / total) * 100);
                return (
                  <div key={`dist-${stage}`}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-mono text-slate-200">{stage}</span>
                      <span className="font-mono text-cyan-100">{raw} / {percent}%</span>
                    </div>
                    <div className="h-4 overflow-hidden rounded-full bg-slate-900">
                      <div className="h-full rounded-full bg-linear-to-r from-cyan-300 via-emerald-300 to-lime-200" style={{ width: `${percent}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">{language === 'zh' ? '检索到的历史相似病例' : 'Retrieved historical similar cases'}</div>
            <div className="mt-4">
              <VisualFrame
                title={language === 'zh' ? '真实 DINO / 多模态病例面板' : 'Real DINO / multimodal case panel'}
                subtitle={language === 'zh' ? '优先复用现有 Agent 可视化脚本输出' : 'reused from existing agent visualization script'}
                src={typeof refs.real_dino_multimodal_panel_url === 'string' ? refs.real_dino_multimodal_panel_url : (typeof refs.similar_cases_contact_sheet_url === 'string' ? refs.similar_cases_contact_sheet_url : undefined)}
              />
            </div>
            <div className="mt-4">
              <VisualFrame
                title={language === 'zh' ? '相似病例 contact sheet' : 'Similar-case contact sheet'}
                subtitle={
                  language === 'zh'
                    ? `已挂载预览图 ${formatUnknown(outputs.similar_cases_with_preview_count ?? 0)} / ${similarCases.length}`
                    : `previews attached ${formatUnknown(outputs.similar_cases_with_preview_count ?? 0)} / ${similarCases.length}`
                }
                src={
                  visualRefPick(refs, [
                    'similar_cases_contact_sheet_url',
                    'real_dino_multimodal_panel_url',
                  ])
                }
              />
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {similarCases.slice(0, 6).map((item, idx) => {
                const previewUrl = typeof item.preview_image_url === 'string' ? item.preview_image_url : undefined;
                return (
                  <div key={`similar-step-${idx}`} className="overflow-hidden rounded-xl border border-white/10 bg-black/25">
                  {previewUrl ? (
                    <div className="relative h-28 bg-black">
                      <Image src={previewUrl} alt={`similar-${idx}`} fill sizes="200px" className="object-contain" unoptimized />
                    </div>
                  ) : (
                    <div className="flex h-28 items-center justify-center bg-black text-[10px] text-slate-600">
                      {language === 'zh' ? '无预览图' : 'no preview'}
                    </div>
                  )}
                  <div className="px-3 py-2 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-slate-100">{formatUnknown(item.patient_id ?? `case-${idx + 1}`)}</span>
                    <span className="rounded-full bg-cyan-300/10 px-2 py-0.5 font-mono text-cyan-100">{numericPercent(item.similarity)}%</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
                        <span>{formatUnknown(item.data_source)}</span>
                        <span>{formatUnknown(item.T_stage)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('runtime_api') || stepId.includes('llm_report_synthesis')) {
      const verification = (outputs.invocations ? outputs : null) as RuntimeVerification | null
        ?? result?.runtime_verification
        ?? runtimeVerification;
      const invocations = verification?.invocations ?? [];
      return (
        <div className="space-y-4">
          <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
            <div className="text-sm font-black text-cyan-100">
              {language === 'zh' ? 'API / 模型调用核验' : 'API / model invocation audit'}
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className={`rounded-full px-2 py-0.5 ${verification?.all_core_models_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-amber-300/15 text-amber-100'}`}>
                {language === 'zh' ? '核心模型' : 'core models'}: {verification?.all_core_models_called ? 'OK' : 'CHECK'}
              </span>
              <span className={`rounded-full px-2 py-0.5 ${verification?.llm_api_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-slate-700/50 text-slate-300'}`}>
                LLM API: {verification?.llm_api_called ? (language === 'zh' ? '已调用' : 'called') : (language === 'zh' ? '未调用/跳过' : 'skipped')}
              </span>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-[11px]">
                <thead>
                  <tr className="text-slate-500">
                    <th className="pb-2 pr-3">{language === 'zh' ? '组件' : 'component'}</th>
                    <th className="pb-2 pr-3">{language === 'zh' ? '类型' : 'kind'}</th>
                    <th className="pb-2 pr-3">{language === 'zh' ? '已调用' : 'called'}</th>
                    <th className="pb-2">{language === 'zh' ? '状态' : 'status'}</th>
                  </tr>
                </thead>
                <tbody>
                  {invocations.map((row) => (
                    <tr key={`inv-${row.component}`} className="border-t border-white/5 text-slate-200">
                      <td className="py-2 pr-3 font-mono">{row.component}</td>
                      <td className="py-2 pr-3 font-mono text-slate-400">{formatUnknown(row.api_kind)}</td>
                      <td className="py-2 pr-3">{row.called ? '✓' : '—'}</td>
                      <td className="py-2 font-mono text-cyan-100">{formatUnknown(row.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(verification?.proxy_visual_notes?.length ?? 0) > 0 && (
              <div className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/5 px-3 py-2 text-[11px] text-amber-100">
                {verification?.proxy_visual_notes?.map((note) => (
                  <div key={note}>{note}</div>
                ))}
              </div>
            )}
          </div>
        </div>
      );
    }

    if (stepId.includes('synthesis')) {
      const support = Array.isArray(outputs.supporting_evidence) ? outputs.supporting_evidence : result?.report.supporting_evidence ?? [];
      const uncertainty = Array.isArray(outputs.uncertainty_flags) ? outputs.uncertainty_flags : result?.report.uncertainty_flags ?? [];
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.8fr_1.2fr]">
          <div className="space-y-4">
            <div className="rounded-xl border border-emerald-300/25 bg-emerald-300/10 p-5">
              <div className="text-xs uppercase tracking-[0.18em] text-emerald-100/70">{language === 'zh' ? '综合推荐' : 'Integrated recommendation'}</div>
              <div className="mt-3 text-6xl font-black text-emerald-100">{formatUnknown(outputs.recommended_t_stage ?? result?.report.recommended_t_stage)}</div>
              <div className="mt-2 text-sm text-emerald-100/80">{formatUnknown(outputs.confidence ?? result?.report.confidence)}</div>
            </div>
            <VisualFrame title={language === 'zh' ? '胃壁穿透风险图' : 'Wall penetration risk'} subtitle={language === 'zh' ? '综合推理使用的胃壁局部风险代理证据' : 'wall proxy evidence used during synthesis'} src={typeof refs.wall_penetration_heatmap_url === 'string' ? refs.wall_penetration_heatmap_url : undefined} />
            <VisualFrame
              title={language === 'zh' ? '真实胃壁分析图' : 'Real wall analysis figure'}
              subtitle={
                language === 'zh'
                  ? '优先脚本输出 PNG，其后为服务端合成面板'
                  : 'script PNG first, then composite panel'
              }
              src={
                visualRefPick(refs, [
                  'real_wall_analysis_panel_url',
                  'wall_penetration_heatmap_url',
                  'wall_layer_profile_url',
                ])
              }
            />
            <VisualFrame title={language === 'zh' ? '真实 DINO 多模态图' : 'Real DINO multimodal figure'} subtitle={language === 'zh' ? '来自现有 DINO 可视化脚本' : 'from existing DINO visualization script'} src={typeof refs.real_dino_multimodal_panel_url === 'string' ? refs.real_dino_multimodal_panel_url : (typeof refs.dino_similarity_heatmap_url === 'string' ? refs.dino_similarity_heatmap_url : undefined)} />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">{language === 'zh' ? '证据权重与冲突提示' : 'Evidence weights and conflict flags'}</div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              {evidenceStreams.map((stream) => (
                <div key={`synth-stream-${stream.label}`} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs">
                  <div className="flex justify-between"><span className="text-slate-400">{stream.label}</span><span className="font-mono text-slate-100">{stream.value}</span></div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-900"><div className="h-full rounded-full bg-linear-to-r from-lime-300 to-emerald-300" style={{ width: `${Math.min(Math.max(stream.weight, 5), 100)}%` }} /></div>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="space-y-2">{support.slice(0, 4).map((item, idx) => <div key={`support-${idx}`} className="rounded bg-emerald-300/10 px-3 py-2 text-xs text-emerald-100">{formatUnknown(item)}</div>)}</div>
              <div className="space-y-2">{uncertainty.slice(0, 4).map((item, idx) => <div key={`uncertain-${idx}`} className="rounded bg-amber-300/10 px-3 py-2 text-xs text-amber-100">{formatUnknown(item)}</div>)}</div>
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('report')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/5 p-4">
            <div className="text-sm font-black text-emerald-100">{language === 'zh' ? '动态报告草稿章节' : 'Dynamic report draft sections'}</div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              {result?.report.dynamic_report_draft?.sections.slice(0, 4).map((section) => (
                <div key={`draft-step-${section.heading}`} className="rounded-xl border border-white/10 bg-black/25 p-3 text-xs">
                  <div className="font-bold text-emerald-100">{section.heading}</div>
                  <div className="mt-2 line-clamp-3 leading-relaxed text-slate-400">{section.lines.join(' ')}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-violet-300/20 bg-violet-300/5 p-4">
            <div className="text-sm font-black text-violet-100">Memory</div>
            <div className="mt-4 space-y-3 text-xs">
              {['memory_candidate_count', 'report_sections', 'review_required'].map((key) => (
                <div key={key} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{key}</div>
                  <div className="mt-1 break-words font-mono text-violet-100">{formatUnknown(outputs[key])}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    return (
      <VisualFrame
        title={language === 'zh' ? '当前步骤输出图' : 'Current step output'}
        subtitle={currentBackendStep.step_id}
        src={getStepVisualRef(currentBackendStep, ['classification_probabilities_url', 'predicted_overlay_url', 'predicted_roi_url', 'predicted_mask_url']) || patient.image_url}
      />
    );
  };

  if (!patient) {
    return null;
  }

  return (
    <div className="pointer-events-none absolute inset-0 z-[100]">
      {workbenchOpen && (loading || result || liveSteps.length > 0 || error) && (
      <div className="pointer-events-auto fixed inset-0 z-[120] overflow-y-auto border border-cyan-500/25 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.18),transparent_36%),linear-gradient(135deg,rgba(0,0,0,0.98),rgba(8,13,24,0.98))] p-5 shadow-2xl shadow-black/70 backdrop-blur-xl md:p-6 custom-scrollbar">
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(59,130,246,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.12)_1px,transparent_1px)] [background-size:18px_18px]" />
        <div className="relative space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.22em] text-cyan-100">
                <Brain size={12} />
                Agent Clinical Console
              </div>
              <div className="mt-3 text-lg font-black leading-tight text-white">
                {language === 'zh' ? '对当前病例进行智能分析' : 'Run intelligent case analysis'}
              </div>
              <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
                {language === 'zh'
                  ? '自动串联分割、T 分期分类、临床风险、报告文本、相似病例与 memory，生成可复核的动态报告。'
                  : 'Run segmentation, classification, clinical risk, reports, similar cases, and memory in one reviewable workflow.'}
              </div>
            </div>
            <div className="flex shrink-0 items-start gap-3">
              {result && (
                <div className={`rounded-xl border px-3 py-2 text-right ${confidenceTone(result.report.confidence)}`}>
                  <div className="text-[10px] uppercase tracking-wider opacity-70">{language === 'zh' ? '推荐' : 'Stage'}</div>
                  <div className="text-2xl font-black">{result.report.recommended_t_stage}</div>
                  <div className="text-[10px] opacity-80">{result.report.confidence}</div>
                </div>
              )}
              <button
                type="button"
                onClick={() => setWorkbenchOpen(false)}
                className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
                aria-label={language === 'zh' ? '关闭 Agent 工作台' : 'Close Agent workbench'}
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-300">
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language === 'zh' ? '病例' : 'Case'}</div>
              <div className="mt-1 truncate font-mono text-slate-100">{patient.patient_id}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language === 'zh' ? '输入' : 'Inputs'}</div>
              <div className="mt-1 font-mono text-slate-100">{patient.roi_url ? 'Image + ROI' : 'Image only'}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language === 'zh' ? '调用链' : 'Tools'}</div>
              <div className="mt-1 font-mono text-slate-100">{result ? `${result.traces?.length ?? 0} traces` : '6 tools'}</div>
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-950/40 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}

          {!loading && !result && liveSteps.length === 0 && (
            <div className="rounded-2xl border border-dashed border-cyan-400/25 bg-cyan-400/5 px-4 py-3 text-xs leading-relaxed text-cyan-100/75">
              {language === 'zh'
                ? 'Agent 入口已固定在主界面右下角。点击浮窗按钮后，本区域会按真实工具调用逐步展开结果。'
                : 'The Agent launcher is pinned to the lower-right of the main interface. Start it there to stream each real tool result into this panel.'}
            </div>
          )}

          {(loading || result || liveSteps.length > 0) && (
            <div className="rounded-[1.35rem] border border-white/10 bg-[linear-gradient(135deg,rgba(3,7,18,0.96),rgba(15,23,42,0.82))] p-3 shadow-inner shadow-black/40">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-sm font-black text-white">
                    <Network size={16} className="text-cyan-300" />
                    {language === 'zh' ? '当前病例 Agent 分析窗口' : 'Current Case Agent Window'}
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
                    {language === 'zh'
                      ? '按后端真实事件逐步追加：工具没跑完就等待，跑完一个显示一个，不再用进度条模拟。'
                      : 'Steps are appended from real backend events: each tool appears only after it finishes.'}
                  </div>
                </div>
                <div className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.18em] ${
                  loading ? 'border-amber-300/30 bg-amber-300/10 text-amber-100' : 'border-cyan-300/30 bg-cyan-300/10 text-cyan-100'
                }`}>
                  {loading ? (language === 'zh' ? '等待工具输出' : 'waiting for tools') : (language === 'zh' ? '分析完成' : 'completed')}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[360px_minmax(0,1fr)]">
                <div className="rounded-2xl border border-white/10 bg-black/25 p-3 2xl:sticky 2xl:top-4 2xl:self-start">
                  <div className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
                    {language === 'zh' ? '实时调用队列' : 'Live Tool Queue'}
                  </div>
                  <div className="max-h-[72vh] space-y-2 overflow-y-auto pr-1 custom-scrollbar">
                    {adaptiveSteps.length ? adaptiveSteps.map((step, idx) => {
                      const Icon = step.icon;
                      const isSelected = idx === activeStep;
                      const isDone = idx < liveSteps.length || Boolean(result);
                      return (
                        <button
                          key={`inline-step-${step.key}-${idx}`}
                          type="button"
                          onClick={() => setActiveStep(idx)}
                          className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                            isSelected
                              ? 'border-emerald-200/60 bg-emerald-200/15 text-emerald-50'
                              : 'border-white/10 bg-white/[0.035] text-slate-300 hover:border-emerald-300/30'
                          }`}
                        >
                          <div className="flex items-start gap-2">
                            <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                              isSelected ? 'bg-emerald-200 text-slate-950' : 'bg-white/5 text-emerald-200'
                            }`}>
                              {loading && idx === liveSteps.length ? <Loader2 size={14} className="animate-spin" /> : isDone ? <CheckCircle2 size={14} /> : <Icon size={14} />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                <div className="truncate text-xs font-black">{idx + 1}. {step.title}</div>
                                <span className="text-[9px] uppercase text-slate-500">{step.backendStep?.status || 'pending'}</span>
                              </div>
                              <div className="mt-1 line-clamp-2 text-[10px] leading-relaxed opacity-70">{step.output}</div>
                            </div>
                          </div>
                        </button>
                      );
                    }) : (
                      <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.03] p-4 text-xs leading-relaxed text-slate-500">
                        {language === 'zh' ? '点击启动后，Agent 会先盘点病例资料，然后第一条真实步骤会出现在这里。' : 'Start the agent to see the first real backend step here.'}
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-black/25 p-4">
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,0.6fr)]">
                    <div className="space-y-3">
                      {renderCurrentStepVisual()}
                      <div className="grid grid-cols-3 gap-2 text-[11px]">
                        <div className="rounded-lg border border-white/10 bg-white/[0.04] px-2 py-2">
                          <span className="text-slate-500">case</span>
                          <div className="truncate font-mono text-slate-100">{patient.patient_id}</div>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-white/[0.04] px-2 py-2">
                          <span className="text-slate-500">steps</span>
                          <div className="font-mono text-emerald-100">{liveSteps.length || result?.agent_steps?.length || 0}</div>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-white/[0.04] px-2 py-2">
                          <span className="text-slate-500">stage</span>
                          <div className="font-mono text-emerald-100">{result?.report.recommended_t_stage || 'waiting'}</div>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                      {currentBackendStep ? (
                        <div className="space-y-3">
                          <div>
                            <div className="text-lg font-black text-white">{activeStep + 1}. {currentBackendStep.title}</div>
                            <div className="mt-1 text-xs leading-relaxed text-slate-400">{currentBackendStep.reasoning || currentBackendStep.intent}</div>
                          </div>
                          <div className="grid grid-cols-3 gap-2 text-[11px]">
                            <div className="rounded bg-emerald-300/10 px-2 py-1"><span className="text-slate-500">decision</span><div className="truncate font-mono text-emerald-100">{currentBackendStep.decision}</div></div>
                            <div className="rounded bg-emerald-300/10 px-2 py-1"><span className="text-slate-500">tool</span><div className="truncate font-mono text-emerald-100">{currentBackendStep.tool_name || 'agent'}</div></div>
                            <div className="rounded bg-emerald-300/10 px-2 py-1"><span className="text-slate-500">status</span><div className="truncate font-mono text-emerald-100">{currentBackendStep.status}</div></div>
                          </div>
                          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                            <pre className="max-h-44 overflow-auto rounded-xl border border-cyan-300/15 bg-cyan-300/5 p-3 text-[11px] text-cyan-50 custom-scrollbar">{JSON.stringify(currentBackendStep.inputs || {}, null, 2)}</pre>
                            <pre className="max-h-44 overflow-auto rounded-xl border border-lime-300/15 bg-lime-300/5 p-3 text-[11px] text-lime-50 custom-scrollbar">{JSON.stringify(currentBackendStep.outputs || {}, null, 2)}</pre>
                          </div>
                        </div>
                      ) : (
                        <div className="flex min-h-[260px] items-center justify-center rounded-xl border border-dashed border-white/10 bg-black/20 text-center text-xs leading-relaxed text-slate-500">
                          {language === 'zh' ? '等待 Agent 返回第一步工具调用结果。模型加载或预测较慢时，这里会保持等待状态。' : 'Waiting for the first real tool-call result from the agent.'}
                        </div>
                      )}
                    </div>
                  </div>

                  {streamLogs.length > 0 && (
                    <div className="mt-3 rounded-xl border border-white/10 bg-black/30 p-3">
                      <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">runtime logs</div>
                      <div className="space-y-1">
                        {streamLogs.map((item, idx) => (
                          <div key={`stream-log-${idx}`} className="line-clamp-1 font-mono text-[10px] text-slate-500">{item}</div>
                        ))}
                      </div>
                    </div>
                  )}

                  {(runtimeVerification ?? result?.runtime_verification) && (
                    <div className="mt-3 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-3">
                      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-200/80">
                        {language === 'zh' ? 'API 调用核验摘要' : 'API invocation summary'}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                        <span className={`rounded-full px-2 py-0.5 ${(runtimeVerification ?? result?.runtime_verification)?.all_core_models_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-amber-300/15 text-amber-100'}`}>
                          {language === 'zh' ? '核心模型' : 'core models'}: {(runtimeVerification ?? result?.runtime_verification)?.all_core_models_called ? 'OK' : 'CHECK'}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 ${(runtimeVerification ?? result?.runtime_verification)?.llm_api_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-slate-700/50 text-slate-300'}`}>
                          LLM: {(runtimeVerification ?? result?.runtime_verification)?.llm_api_called ? (language === 'zh' ? '已调用' : 'called') : (language === 'zh' ? '未调用' : 'skipped')}
                        </span>
                      </div>
                      <div className="mt-2 text-[10px] text-slate-500">
                        {language === 'zh'
                          ? '完整表格见步骤「运行时 API / 模型调用核验」。'
                          : 'See the runtime API verification step for the full table.'}
                      </div>
                    </div>
                  )}

                  {result && (
                    <div className="mt-3 rounded-xl border border-emerald-300/20 bg-emerald-300/10 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-black text-emerald-50">{language === 'zh' ? '综合推荐结果' : 'Integrated recommendation'}</div>
                          <div className="mt-1 text-xs leading-relaxed text-emerald-100/75">{result.report.reasoning}</div>
                        </div>
                        <div className={`rounded-xl border px-4 py-2 text-right ${confidenceTone(result.report.confidence)}`}>
                          <div className="text-3xl font-black">{result.report.recommended_t_stage}</div>
                          <div className="text-[10px] uppercase">{result.report.confidence}</div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      )}

      <div className="pointer-events-auto absolute left-1/2 top-4 z-40 w-[min(430px,calc(100%-2rem))] -translate-x-1/2">
        <button
          type="button"
          onClick={handleLauncherClick}
          disabled={loading}
          className="group relative w-full overflow-hidden rounded-[1.4rem] border border-cyan-200/60 bg-[linear-gradient(135deg,#38bdf8,#22d3ee_45%,#94a3b8)] p-1 text-left text-slate-950 shadow-[0_24px_70px_rgba(2,8,23,0.65)] transition hover:-translate-y-1 hover:shadow-[0_28px_90px_rgba(14,165,233,0.38)] disabled:translate-y-0 disabled:cursor-wait disabled:opacity-85"
          aria-label={language === 'zh' ? '启动当前病例 Agent 分析' : 'Start current case agent analysis'}
        >
          <span className="pointer-events-none absolute -left-10 top-1/2 h-24 w-24 -translate-y-1/2 rounded-full bg-white/45 blur-2xl transition group-hover:scale-150" />
          <span className="pointer-events-none absolute right-7 top-5 h-2.5 w-2.5 rounded-full bg-slate-950/50">
            {loading && <span className="absolute inset-0 animate-ping rounded-full bg-slate-950/50" />}
          </span>
          <span className="relative flex items-center gap-3 rounded-[1.2rem] bg-white/35 px-4 py-3 backdrop-blur-sm">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-cyan-200 shadow-lg shadow-slate-950/30">
              {loading ? <Loader2 size={22} className="animate-spin" /> : <Sparkles size={22} />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-black tracking-tight">
                {loading
                  ? (language === 'zh' ? 'Agent 正在等待工具输出' : 'Agent is waiting for tools')
                  : (result || liveSteps.length > 0 || error) && !workbenchOpen
                    ? (language === 'zh' ? '打开 Agent 工作台' : 'Open agent workbench')
                    : result
                      ? (language === 'zh' ? '重新运行当前病例 Agent' : 'Rerun agent for this case')
                    : (language === 'zh' ? '启动当前病例 Agent' : 'Start case agent')}
              </span>
              <span className="mt-0.5 block truncate text-[11px] font-semibold text-slate-800/80">
                {loading
                  ? `${liveSteps.length} ${language === 'zh' ? '步已返回' : 'steps returned'}`
                  : (language === 'zh' ? '分割、分类、相似病例、报告逐步显示' : 'Segmentation, staging, memory, report stream in')}
              </span>
            </span>
            <ArrowRight size={20} className="shrink-0 transition group-hover:translate-x-1" />
          </span>
        </button>
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="relative flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-emerald-300/30 bg-slate-950 shadow-2xl shadow-black">
            <div className="absolute inset-0 opacity-30 [background:radial-gradient(circle_at_20%_0%,rgba(16,185,129,0.35),transparent_32%),radial-gradient(circle_at_85%_18%,rgba(14,165,233,0.22),transparent_28%)]" />
            <div className="relative border-b border-white/10 bg-black/30 px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-emerald-300/30 bg-emerald-300/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.22em] text-emerald-100">AI Case Board</span>
                    <span className="font-mono text-[11px] text-slate-500">{patient.patient_id}</span>
                  </div>
                  <h2 className="mt-2 text-2xl font-black text-white">
                    {language === 'zh' ? '当前病例智能分析' : 'Current Case Intelligence'}
                  </h2>
                  <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-400">
                    {language === 'zh'
                      ? '按照临床主线逐步展示：病例接入、病灶定位、T 分期分类、临床与报告交叉验证、相似病例检索、综合判断、动态报告和 memory 候选。'
                      : 'A step-by-step clinical workflow: intake, lesion localization, T staging, clinical/report cross-checks, similar cases, final synthesis, report draft, and memory candidates.'}
                  </p>
                </div>
                <button
                  onClick={() => setModalOpen(false)}
                  className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
                  aria-label="Close Agent modal"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="relative overflow-y-auto p-5 custom-scrollbar">
              {loading && (
                <div className="mb-5 rounded-2xl border border-emerald-300/20 bg-emerald-300/10 p-5">
                  <div className="flex items-center gap-3 text-emerald-100">
                    <Loader2 size={20} className="animate-spin" />
                    <div>
                      <div className="text-sm font-bold">{language === 'zh' ? 'Agent 正在根据当前病例动态选择工具' : 'Agent is dynamically selecting tools for this case'}</div>
                      <div className="mt-1 text-xs text-emerald-100/70">
                        {language === 'zh' ? '不是只走固定模板，而是先盘点病例资料，再决定定位、分割、分类、临床/报告校验和相似病例投票的权重。' : 'This is not a rigid template: the agent inspects case evidence and weights localization, segmentation, classification, clinical/report checks, and similar-case voting.'}
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[0.85fr_1.15fr]">
                    <div className="space-y-2">
                      {adaptiveSteps.map((step, idx) => {
                        const Icon = step.icon;
                        const isActive = idx === activeStep;
                        const isDone = idx < activeStep;
                        return (
                          <div
                            key={step.key}
                            className={`rounded-xl border px-3 py-2 transition ${
                              isActive
                                ? 'border-emerald-200/60 bg-emerald-200/15 text-emerald-50 shadow-[0_0_22px_rgba(16,185,129,0.22)]'
                                : isDone
                                  ? 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100/75'
                                  : 'border-white/10 bg-black/20 text-slate-500'
                            }`}
                          >
                            <div className="flex items-start gap-2">
                              <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${isActive ? 'bg-emerald-200 text-slate-950' : 'bg-white/5 text-current'}`}>
                                {isActive ? <Loader2 size={14} className="animate-spin" /> : <Icon size={14} />}
                              </div>
                              <div className="min-w-0">
                                <div className="text-xs font-bold">{idx + 1}. {step.title}</div>
                                <div className="mt-0.5 line-clamp-2 text-[10px] leading-relaxed opacity-70">{step.detail}</div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="rounded-2xl border border-emerald-300/20 bg-black/25 p-3">
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-bold text-emerald-100">
                            {language === 'zh' ? '当前工具调用可视化' : 'Current tool-call visualization'}
                          </div>
                          <div className="mt-0.5 text-[10px] text-emerald-100/60">{adaptiveSteps[activeStep]?.title}</div>
                        </div>
                        <span className="rounded-full border border-emerald-300/30 bg-emerald-300/10 px-2 py-1 text-[10px] text-emerald-100">
                          calling
                        </span>
                      </div>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        <VisualFrame
                          title={language === 'zh' ? '原始超声输入' : 'Original ultrasound'}
                          subtitle={patient.id_short}
                          src={patient.image_url}
                        />
                        <VisualFrame
                          title={activeStep <= 1 ? (language === 'zh' ? '等待定位输出' : 'Waiting for localization') : (language === 'zh' ? 'ROI / 分割叠加预览' : 'ROI / overlay preview')}
                          subtitle={activeStep <= 1 ? 'pending model output' : 'case asset preview'}
                          src={activeStep <= 1 ? patient.image_url : (patient.overlay_url || patient.roi_url || patient.image_url)}
                        />
                      </div>
                      <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-slate-300">
                        {adaptiveSteps[activeStep]?.detail}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {error && (
                <div className="mb-5 rounded-2xl border border-red-500/30 bg-red-950/40 p-4 text-sm text-red-200">
                  {error}
                </div>
              )}

              {result ? (
                <div className="space-y-5">
                  <div className="sticky top-0 z-10 rounded-2xl border border-emerald-300/25 bg-slate-950/95 p-4 shadow-2xl shadow-black/40 backdrop-blur">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-bold text-white">
                          <Workflow size={16} className="text-emerald-300" />
                          {language === 'zh' ? '逐步检查 Agent 每一次工具调用' : 'Inspect each agent tool call step by step'}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {language === 'zh' ? '点击任意步骤，查看该步骤的输入、模型输出、图像证据和推理解释。' : 'Click any step to inspect its inputs, model outputs, visual evidence, and reasoning.'}
                        </div>
                      </div>
                      <span className="rounded-full border border-emerald-300/30 bg-emerald-300/10 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-emerald-100">
                        step {activeStep + 1}/{adaptiveSteps.length}
                      </span>
                    </div>

                    <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
                      {adaptiveSteps.map((step, idx) => {
                        const Icon = step.icon;
                        const isSelected = idx === activeStep;
                        return (
                          <button
                            key={`step-nav-${step.key}`}
                            onClick={() => setActiveStep(idx)}
                            className={`min-w-[132px] rounded-xl border px-3 py-2 text-left transition ${
                              isSelected
                                ? 'border-emerald-200/70 bg-emerald-200 text-slate-950 shadow-[0_0_24px_rgba(16,185,129,0.25)]'
                                : 'border-white/10 bg-white/[0.04] text-slate-300 hover:border-emerald-300/40 hover:bg-emerald-300/10'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <Icon size={14} />
                              <span className="text-[10px] font-black uppercase tracking-wider">Step {idx + 1}</span>
                            </div>
                            <div className="mt-1 line-clamp-1 text-[11px] font-semibold">{step.title}</div>
                          </button>
                        );
                      })}
                    </div>

                    <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                      <div className="rounded-xl border border-white/10 bg-black/25 p-4">
                        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{language === 'zh' ? '当前步骤' : 'Current step'}</div>
                        <div className="mt-2 text-lg font-black text-white">{activeStep + 1}. {adaptiveSteps[activeStep]?.title}</div>
                        <div className="mt-2 text-sm leading-relaxed text-slate-300">{adaptiveSteps[activeStep]?.detail}</div>
                        <div className="mt-3 rounded-lg border border-cyan-300/20 bg-cyan-300/10 px-3 py-2 font-mono text-xs text-cyan-100">
                          output: {adaptiveSteps[activeStep]?.output}
                        </div>
                        {currentBackendStep && (
                          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                            <div className="rounded bg-emerald-300/10 px-2 py-1">
                              <span className="text-slate-500">decision</span>
                              <div className="truncate font-mono text-emerald-100">{currentBackendStep.decision}</div>
                            </div>
                            <div className="rounded bg-emerald-300/10 px-2 py-1">
                              <span className="text-slate-500">tool</span>
                              <div className="truncate font-mono text-emerald-100">{currentBackendStep.tool_name || 'agent'}</div>
                            </div>
                            <div className="rounded bg-emerald-300/10 px-2 py-1">
                              <span className="text-slate-500">status</span>
                              <div className="truncate font-mono text-emerald-100">{currentBackendStep.status}</div>
                            </div>
                          </div>
                        )}
                        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                          <div className="rounded bg-white/[0.04] px-2 py-1">
                            <span className="text-slate-500">case</span>
                            <div className="truncate font-mono text-slate-200">{patient.patient_id}</div>
                          </div>
                          <div className="rounded bg-white/[0.04] px-2 py-1">
                            <span className="text-slate-500">source</span>
                            <div className="truncate font-mono text-slate-200">{patient.source_label}</div>
                          </div>
                        </div>
                      </div>

                      <div className="rounded-xl border border-white/10 bg-black/25 p-4">
                        {currentBackendStep && (
                          <div className="space-y-4">
                            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                              <VisualFrame
                                title={language === 'zh' ? '本次模型新生成的预测图' : 'New prediction artifact from this run'}
                                subtitle={currentBackendStep.step_id}
                                src={
                                  getStepVisualRef(currentBackendStep, [
                                    'classification_probabilities_url',
                                    'predicted_overlay_url',
                                    'predicted_roi_url',
                                    'predicted_mask_url',
                                  ]) || patient.image_url
                                }
                              />
                              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                                <div className="text-sm font-bold text-emerald-100">{language === 'zh' ? '真实 Agent 决策记录' : 'Real agent decision trace'}</div>
                                <div className="mt-2 text-xs leading-relaxed text-slate-300">{currentBackendStep.intent}</div>
                                <div className="mt-3 grid grid-cols-1 gap-2 text-[11px]">
                                  {Object.entries(currentBackendStep.outputs || {}).slice(0, 8).map(([key, value]) => (
                                    <div key={`backend-output-${currentBackendStep.step_id}-${key}`} className="rounded bg-black/25 px-2 py-1">
                                      <span className="text-slate-500">{key}</span>
                                      <div className="break-words font-mono text-emerald-100">{formatUnknown(value)}</div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                              <div className="rounded-xl border border-cyan-300/15 bg-cyan-300/5 p-3">
                                <div className="text-xs font-bold uppercase tracking-[0.16em] text-cyan-100">inputs</div>
                                <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[11px] text-cyan-50 custom-scrollbar">
                                  {JSON.stringify(currentBackendStep.inputs || {}, null, 2)}
                                </pre>
                              </div>
                              <div className="rounded-xl border border-lime-300/15 bg-lime-300/5 p-3">
                                <div className="text-xs font-bold uppercase tracking-[0.16em] text-lime-100">outputs</div>
                                <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[11px] text-lime-50 custom-scrollbar">
                                  {JSON.stringify(currentBackendStep.outputs || {}, null, 2)}
                                </pre>
                              </div>
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 0 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <VisualFrame title={language === 'zh' ? '原始超声输入' : 'Original ultrasound input'} subtitle={patient.id_short} src={patient.image_url} />
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-slate-100">{language === 'zh' ? '病例资料盘点' : 'Case evidence inventory'}</div>
                              <div className="mt-3 space-y-2 text-xs">
                                <div className="flex justify-between rounded bg-black/25 px-2 py-1"><span className="text-slate-500">ROI</span><span className="text-slate-200">{patient.roi_url ? 'available' : 'missing'}</span></div>
                                <div className="flex justify-between rounded bg-black/25 px-2 py-1"><span className="text-slate-500">overlay</span><span className="text-slate-200">{patient.overlay_url ? 'available' : 'missing'}</span></div>
                                <div className="flex justify-between rounded bg-black/25 px-2 py-1"><span className="text-slate-500">clinical</span><span className="text-slate-200">{patient.clinical ? 'available' : 'missing'}</span></div>
                                <div className="flex justify-between rounded bg-black/25 px-2 py-1"><span className="text-slate-500">report</span><span className="text-slate-200">{patient.report ? 'attached' : 'missing'}</span></div>
                              </div>
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 1 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <VisualFrame title={language === 'zh' ? 'ROI 裁剪输入' : 'ROI crop input'} subtitle={patient.roi_url ? 'frontend ROI asset' : 'fallback'} src={patient.roi_url || patient.image_url} />
                            <VisualFrame title={language === 'zh' ? '定位输出/叠加预览' : 'Localization output / overlay'} subtitle={formatUnknown(result.tool_evidence.segmentation?.roi_source)} src={patient.overlay_url || patient.roi_url || patient.image_url}>
                              <div className="grid grid-cols-2 gap-2 text-[11px]">
                                {getToolMetricRows(result.tool_evidence.segmentation, ['roi_source', 'mask_available', 'lesion_area_ratio', 'image_height', 'image_width']).map((row) => (
                                  <div key={`step1-${row.key}`} className="rounded bg-black/25 px-2 py-1">
                                    <span className="text-slate-500">{row.key}</span>
                                    <div className="truncate font-mono text-cyan-100">{formatUnknown(row.value)}</div>
                                  </div>
                                ))}
                              </div>
                            </VisualFrame>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 2 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <VisualFrame title={language === 'zh' ? '分割叠加证据' : 'Segmentation overlay evidence'} subtitle={patient.overlay_url ? 'overlay asset' : 'fallback preview'} src={patient.overlay_url || patient.roi_url || patient.image_url} />
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-lime-100">{language === 'zh' ? '形态学输出' : 'Morphology outputs'}</div>
                              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                                {getToolMetricRows(result.tool_evidence.morphology, ['boundary_irregularity', 'lesion_area_ratio', 'convexity', 'solidity', 'compactness', 'aspect_ratio']).map((row) => (
                                  <div key={`step2-${row.key}`} className="rounded bg-black/25 px-2 py-1">
                                    <span className="text-slate-500">{row.key}</span>
                                    <div className="truncate font-mono text-lime-100">{formatUnknown(row.value)}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 3 && (
                          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                            <div className="text-sm font-bold text-emerald-100">{language === 'zh' ? '分类概率输出' : 'Classifier probability output'}</div>
                            <div className="mt-4 space-y-3">
                              {classificationProbs.map((item) => (
                                <div key={`step3-${item.stage}`}>
                                  <div className="mb-1 flex items-center justify-between text-xs">
                                    <span className="font-mono text-slate-200">{item.stage}</span>
                                    <span className="font-mono text-emerald-200">{numericPercent(item.value)}%</span>
                                  </div>
                                  <div className="h-3 overflow-hidden rounded-full bg-slate-800">
                                    <div className="h-full rounded-full bg-linear-to-r from-emerald-300 to-cyan-300" style={{ width: `${Math.min(numericPercent(item.value), 100)}%` }} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 4 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-amber-100">{language === 'zh' ? '临床风险工具输出' : 'Clinical risk output'}</div>
                              <div className="mt-3 space-y-2 text-[11px]">
                                {getToolMetricRows(result.tool_evidence.clinical, ['clinical_risk_score', 'risk_factors', 'protective_factors', 'factors_available']).map((row) => (
                                  <div key={`step4-clinical-${row.key}`} className="rounded bg-black/25 px-2 py-1">
                                    <span className="text-slate-500">{row.key}</span>
                                    <div className="truncate font-mono text-amber-100">{formatUnknown(row.value)}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-sky-100">{language === 'zh' ? '报告线索抽取' : 'Report cue extraction'}</div>
                              <div className="mt-3 space-y-2">
                                {getReportCues(result.tool_evidence.report).length ? getReportCues(result.tool_evidence.report).map((cue, idx) => (
                                  <div key={`step4-cue-${idx}`} className="rounded bg-black/25 px-2 py-1 text-[11px]">
                                    <div className="font-mono text-sky-100">{cue.cue}</div>
                                    <div className="mt-1 text-slate-500">{formatUnknown(cue.matched_terms)}</div>
                                  </div>
                                )) : (
                                  <div className="text-xs text-slate-500">{language === 'zh' ? '没有可结构化文本线索，因此文本证据降权。' : 'No structured text cues; report evidence is down-weighted.'}</div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 5 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-cyan-100">{language === 'zh' ? '相似病例投票' : 'Similar-case voting'}</div>
                              <div className="mt-3 space-y-3">
                                {stageVoting.map((item) => (
                                  <div key={`step5-vote-${item.stage}`}>
                                    <div className="mb-1 flex items-center justify-between text-xs"><span>{item.stage}</span><span>{item.vote.toFixed(2)}</span></div>
                                    <div className="h-2.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-linear-to-r from-cyan-300 via-emerald-300 to-lime-200" style={{ width: `${item.percent}%` }} /></div>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="space-y-2">
                              {result.similar_cases.slice(0, 5).map((item, idx) => (
                                <div key={`step5-case-${item.patient_id}-${idx}`} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs">
                                  <div className="flex justify-between"><span className="font-mono text-slate-200">{item.patient_id ?? `case-${idx + 1}`}</span><span className="text-cyan-200">{numericPercent(item.similarity)}%</span></div>
                                  <div className="mt-1 text-[10px] text-slate-500">{item.T_stage} · {item.data_source}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 6 && (
                          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                            <div className="text-4xl font-black text-emerald-200">{result.report.recommended_t_stage}</div>
                            <div className="mt-2 text-sm leading-relaxed text-slate-300">{result.report.reasoning}</div>
                            <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                              {evidenceStreams.map((stream) => (
                                <div key={`step6-${stream.label}`} className="rounded bg-black/25 px-3 py-2 text-xs">
                                  <div className="flex justify-between"><span className="text-slate-400">{stream.label}</span><span className="font-mono text-slate-100">{stream.value}</span></div>
                                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-linear-to-r from-lime-300 to-emerald-300" style={{ width: `${Math.min(Math.max(stream.weight, 5), 100)}%` }} /></div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 7 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-emerald-100">{language === 'zh' ? '报告草稿章节' : 'Report draft sections'}</div>
                              <div className="mt-3 space-y-2">
                                {result.report.dynamic_report_draft?.sections.slice(0, 4).map((section) => (
                                  <div key={`step7-${section.heading}`} className="rounded bg-black/25 px-2 py-2 text-xs">
                                    <div className="font-bold text-emerald-100">{section.heading}</div>
                                    <div className="mt-1 line-clamp-2 text-slate-400">{section.lines.join(' ')}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-violet-100">Memory</div>
                              <div className="mt-3 space-y-2 text-xs">
                                <div className="rounded bg-black/25 px-2 py-1"><span className="text-slate-500">candidates</span><div className="font-mono text-violet-100">{result.report.memory_update_candidates?.length ?? 0}</div></div>
                                <div className="rounded bg-black/25 px-2 py-1"><span className="text-slate-500">traces</span><div className="font-mono text-violet-100">{result.traces?.length ?? 0}</div></div>
                                {result.trajectory_ref?.path && <div className="rounded bg-black/25 px-2 py-1"><span className="text-slate-500">trajectory</span><div className="break-all font-mono text-[10px] text-violet-100">{result.trajectory_ref.path}</div></div>}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-cyan-300/20 bg-black/20 p-4">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-bold text-white">
                          <Layers3 size={16} className="text-cyan-300" />
                          {language === 'zh' ? '逐步工具调用与图像输出' : 'Step-by-step tool calls and visual outputs'}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {language === 'zh'
                            ? '每一步都显示该工具看到的输入、产生的图像证据或结构化输出，避免只看最后一个总进度条。'
                            : 'Each step shows the input seen by the tool and the visual or structured output it produced.'}
                        </div>
                      </div>
                      <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-cyan-100">
                        visual reasoning
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-100">
                          <Brain size={15} className="text-emerald-300" />
                          1. {language === 'zh' ? '病例接入：原始影像输入' : 'Case intake: raw imaging input'}
                        </div>
                        <VisualFrame
                          title={language === 'zh' ? '原始超声图像' : 'Original ultrasound'}
                          subtitle={patient.id_short}
                          src={patient.image_url}
                        >
                          <div className="grid grid-cols-2 gap-2 text-[11px]">
                            <div className="rounded bg-black/25 px-2 py-1">
                              <span className="text-slate-500">patient</span>
                              <div className="font-mono text-slate-200">{patient.patient_id}</div>
                            </div>
                            <div className="rounded bg-black/25 px-2 py-1">
                              <span className="text-slate-500">frames</span>
                              <div className="font-mono text-slate-200">{patient.frame_count}</div>
                            </div>
                          </div>
                        </VisualFrame>
                      </div>

                      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-100">
                          <Layers3 size={15} className="text-cyan-300" />
                          2. {language === 'zh' ? '定位模型：ROI / 候选病灶区' : 'Localization: ROI / candidate lesion region'}
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                          <VisualFrame
                            title={language === 'zh' ? 'ROI 裁剪' : 'ROI crop'}
                            subtitle={patient.roi_url ? 'frontend ROI asset' : 'fallback pending'}
                            src={patient.roi_url || patient.image_url}
                          />
                          <VisualFrame
                            title={language === 'zh' ? '定位/叠加预览' : 'Localization overlay'}
                            subtitle={formatUnknown(result.tool_evidence.segmentation?.roi_source)}
                            src={patient.overlay_url || patient.roi_url || patient.image_url}
                          />
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                          {getToolMetricRows(result.tool_evidence.segmentation, ['roi_source', 'mask_available', 'lesion_area_ratio']).map((row) => (
                            <div key={row.key} className="rounded bg-black/25 px-2 py-1">
                              <span className="text-slate-500">{row.key}</span>
                              <div className="truncate font-mono text-cyan-100">{formatUnknown(row.value)}</div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-100">
                          <Activity size={15} className="text-lime-300" />
                          3. {language === 'zh' ? '分割/形态：病灶边界推理' : 'Segmentation/morphology: boundary reasoning'}
                        </div>
                        <VisualFrame
                          title={language === 'zh' ? '分割叠加图像证据' : 'Segmentation overlay evidence'}
                          subtitle={patient.overlay_url ? 'manual/predicted overlay asset' : 'overlay unavailable'}
                          src={patient.overlay_url || patient.roi_url || patient.image_url}
                        >
                          <div className="grid grid-cols-2 gap-2 text-[11px]">
                            {getToolMetricRows(result.tool_evidence.morphology, ['boundary_irregularity', 'convexity', 'solidity', 'compactness']).map((row) => (
                              <div key={row.key} className="rounded bg-black/25 px-2 py-1">
                                <span className="text-slate-500">{row.key}</span>
                                <div className="font-mono text-lime-100">{formatUnknown(row.value)}</div>
                              </div>
                            ))}
                          </div>
                        </VisualFrame>
                      </div>

                      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-100">
                          <Microscope size={15} className="text-emerald-300" />
                          4. {language === 'zh' ? '分类模型：T 分期概率输出' : 'Classifier: T-stage probability output'}
                        </div>
                        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
                          <div className="space-y-3">
                            {classificationProbs.length ? classificationProbs.map((item) => (
                              <div key={`visual-${item.stage}`}>
                                <div className="mb-1 flex items-center justify-between text-xs">
                                  <span className="font-mono text-slate-200">{item.stage}</span>
                                  <span className="font-mono text-emerald-200">{numericPercent(item.value)}%</span>
                                </div>
                                <div className="h-3 overflow-hidden rounded-full bg-slate-800">
                                  <div className="h-full rounded-full bg-linear-to-r from-emerald-300 to-cyan-300" style={{ width: `${Math.min(numericPercent(item.value), 100)}%` }} />
                                </div>
                              </div>
                            )) : (
                              <div className="text-xs text-slate-500">{language === 'zh' ? '分类概率暂不可用' : 'Classifier probabilities unavailable'}</div>
                            )}
                          </div>
                          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                            {getToolMetricRows(result.tool_evidence.classification, ['top1_stage', 'top1_prob', 'top2_stage', 'uncertainty']).slice(0, 4).map((row) => (
                              <div key={row.key} className="rounded bg-white/[0.04] px-2 py-1">
                                <span className="text-slate-500">{row.key}</span>
                                <div className="truncate font-mono text-emerald-100">{formatUnknown(row.value)}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-100">
                          <Database size={15} className="text-cyan-300" />
                          5. {language === 'zh' ? '相似病例：检索与投票' : 'Similar cases: retrieval and voting'}
                        </div>
                        <div className="space-y-3 rounded-xl border border-white/10 bg-black/30 p-3">
                          {stageVoting.map((item) => (
                            <div key={`visual-vote-${item.stage}`}>
                              <div className="mb-1 flex items-center justify-between text-xs">
                                <span className="font-mono text-slate-200">{item.stage}</span>
                                <span className="font-mono text-cyan-100">{item.vote.toFixed(2)}</span>
                              </div>
                              <div className="h-2.5 overflow-hidden rounded-full bg-slate-800">
                                <div className="h-full rounded-full bg-linear-to-r from-cyan-300 via-emerald-300 to-lime-200" style={{ width: `${item.percent}%` }} />
                              </div>
                            </div>
                          ))}
                        </div>
                        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                          {result.similar_cases.slice(0, 4).map((item, idx) => (
                            <div key={`visual-case-${item.patient_id}-${idx}`} className="rounded-lg bg-black/25 px-3 py-2 text-xs">
                              <div className="flex items-center justify-between">
                                <span className="font-mono text-slate-200">{item.patient_id ?? `case-${idx + 1}`}</span>
                                <span className="text-cyan-200">{numericPercent(item.similarity)}%</span>
                              </div>
                              <div className="mt-1 text-[10px] text-slate-500">{item.T_stage} · {item.data_source}</div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-100">
                          <FileText size={15} className="text-amber-300" />
                          6. {language === 'zh' ? '综合推理：报告草稿与人工复核点' : 'Synthesis: draft and review points'}
                        </div>
                        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
                          <div className="text-4xl font-black text-emerald-200">{result.report.recommended_t_stage}</div>
                          <div className="mt-1 text-xs text-slate-500">{language === 'zh' ? '最终综合推荐，不等同于单模型 top-1' : 'Final integrated recommendation, not a single-model top-1'}</div>
                          <div className="mt-3 space-y-2">
                            {result.report.rag_gate && (
                              <div className="rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100/85">
                                {language === 'zh' ? 'RAG 门控' : 'RAG gate'}: weight={result.report.rag_gate.rag_weight} ({result.report.rag_gate.rag_gate_reason})
                              </div>
                            )}
                            {result.report.conflicting_evidence?.slice(0, 3).map((item, idx) => (
                              <div key={`visual-conflict-${idx}`} className="rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-100/85">
                                {item}
                              </div>
                            ))}
                            {result.report.uncertainty_flags?.slice(0, 3).map((item, idx) => (
                              <div key={`visual-risk-${idx}`} className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs text-amber-100/85">
                                {item}
                              </div>
                            ))}
                            {!result.report.uncertainty_flags?.length && !result.report.conflicting_evidence?.length && (
                              <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100/85">
                                {language === 'zh' ? '暂无明显风险提示，但仍需医生结合原始图像复核。' : 'No major risk flags, but clinician review is still required.'}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-emerald-300/20 bg-black/20 p-4">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-bold text-white">
                          <Network size={16} className="text-emerald-300" />
                          {language === 'zh' ? 'Agent 自适应推理编排' : 'Adaptive agent orchestration'}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {language === 'zh'
                            ? '每个节点代表一次信息判断或模型调用；权重来自当前病例可用资料，而不是写死的单一路径。'
                            : 'Each node is an evidence decision or model call; weighting follows available case evidence, not one hard-coded path.'}
                        </div>
                      </div>
                      <div className="rounded-full border border-emerald-300/30 bg-emerald-300/10 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-emerald-100">
                        {result.traces?.length ?? 0} tool traces
                      </div>
                    </div>
                    <div className="relative">
                      <div className="absolute left-4 top-4 hidden h-[calc(100%-2rem)] w-px bg-emerald-300/20 md:block" />
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        {adaptiveSteps.map((step, idx) => {
                          const Icon = step.icon;
                          return (
                            <div key={step.key} className="relative rounded-xl border border-white/10 bg-white/[0.035] p-3">
                              <div className="flex items-start gap-3">
                                <div className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-emerald-300/30 bg-emerald-300/10 text-emerald-200">
                                  <Icon size={16} />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-start justify-between gap-2">
                                    <div className="text-sm font-bold text-slate-100">{idx + 1}. {step.title}</div>
                                    <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2 py-0.5 text-[9px] text-emerald-100">DONE</span>
                                  </div>
                                  <div className="mt-1 text-[11px] leading-relaxed text-slate-400">{step.detail}</div>
                                  <div className="mt-2 rounded-lg bg-black/25 px-2 py-1 font-mono text-[10px] text-cyan-100">
                                    output: {step.output}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{language === 'zh' ? '综合结论' : 'Synthesis'}</div>
                      <div className="mt-3 flex flex-wrap items-end gap-4">
                        <div>
                          <div className="text-5xl font-black text-emerald-200">{result.report.recommended_t_stage}</div>
                          <div className="mt-1 text-xs text-slate-500">{language === 'zh' ? '推荐 T 分期' : 'Recommended T stage'}</div>
                        </div>
                        <div className={`rounded-xl border px-3 py-2 text-sm ${confidenceTone(result.report.confidence)}`}>
                          {language === 'zh' ? '置信度' : 'Confidence'}: {result.report.confidence}
                        </div>
                        <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-300">
                          {language === 'zh' ? '会话累计' : 'Session'}: {result.session_memory.analysis_count}
                        </div>
                      </div>
                      <p className="mt-4 text-sm leading-relaxed text-slate-300">{result.report.reasoning}</p>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{language === 'zh' ? '分类概率可视化' : 'Classifier probabilities'}</div>
                      <div className="mt-4 space-y-3">
                        {classificationProbs.length ? classificationProbs.map((item) => (
                          <div key={item.stage}>
                            <div className="mb-1 flex items-center justify-between text-xs">
                              <span className="font-mono text-slate-200">{item.stage}</span>
                              <span className="font-mono text-emerald-200">{numericPercent(item.value)}%</span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                              <div className="h-full rounded-full bg-linear-to-r from-emerald-300 to-cyan-300" style={{ width: `${Math.min(numericPercent(item.value), 100)}%` }} />
                            </div>
                          </div>
                        )) : (
                          <div className="text-xs text-slate-500">{language === 'zh' ? '分类概率暂不可用' : 'Classifier probabilities unavailable'}</div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-[0.95fr_1.05fr]">
                    <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/5 p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2 text-sm font-bold text-cyan-100">
                            <Database size={16} />
                            {language === 'zh' ? '相似病例与多证据投票' : 'Similar-case and evidence voting'}
                          </div>
                          <div className="mt-1 text-xs text-cyan-100/55">
                            {language === 'zh' ? '分类概率是一个投票源，相似病例、临床风险、分割质量和报告线索也是投票源。' : 'Classifier probabilities are one vote source; similar cases, clinical risk, segmentation quality, and report cues also vote.'}
                          </div>
                        </div>
                        <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[10px] text-cyan-100">
                          {result.similar_cases.length} cases
                        </span>
                      </div>
                      <div className="space-y-3">
                        {stageVoting.map((item) => (
                          <div key={item.stage}>
                            <div className="mb-1 flex items-center justify-between text-xs">
                              <span className="font-mono text-slate-200">{item.stage}</span>
                              <span className="font-mono text-cyan-100">{item.vote.toFixed(2)}</span>
                            </div>
                            <div className="h-2.5 overflow-hidden rounded-full bg-slate-900">
                              <div className="h-full rounded-full bg-linear-to-r from-cyan-300 via-emerald-300 to-lime-200" style={{ width: `${item.percent}%` }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <ShieldCheck size={16} className="text-lime-300" />
                        {language === 'zh' ? '综合证据权重面板' : 'Integrated evidence weights'}
                      </div>
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                        {evidenceStreams.map((stream) => (
                          <div key={stream.label} className="rounded-xl border border-white/10 bg-black/25 p-3">
                            <div className="flex items-center justify-between gap-2 text-xs">
                              <span className="text-slate-400">{stream.label}</span>
                              <span className="font-mono text-slate-100">{stream.value}</span>
                            </div>
                            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                              <div className="h-full rounded-full bg-linear-to-r from-lime-300 to-emerald-300" style={{ width: `${Math.min(Math.max(stream.weight, 5), 100)}%` }} />
                            </div>
                            <div className="mt-1 text-right font-mono text-[10px] text-slate-500">{Math.min(Math.max(stream.weight, 0), 100)}%</div>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-[11px] leading-relaxed text-amber-100/80">
                        {language === 'zh'
                          ? '如果某一路证据缺失或冲突，Agent 会降低它的权重，并把不确定性写入人工复核提示。'
                          : 'When one evidence stream is missing or conflicting, the agent lowers its weight and records uncertainty for clinician review.'}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="mb-4 flex items-center gap-2 text-sm font-bold text-white">
                      <Workflow size={16} className="text-emerald-300" />
                      {language === 'zh' ? '按主线展开的模型调用结果' : 'Model calls along the clinical workflow'}
                    </div>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {toolCards.map((card, idx) => {
                        const Icon = card.icon;
                        const status = toolAvailability(card.tool);
                        return (
                          <div key={card.key} className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-center gap-2">
                                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-300/10 text-emerald-200">
                                  <Icon size={16} />
                                </div>
                                <div>
                                  <div className="text-sm font-bold text-slate-100">{idx + 1}. {card.title}</div>
                                  <div className="mt-0.5 max-w-[180px] truncate font-mono text-[10px] text-slate-500">{getToolBackend(card.tool)}</div>
                                </div>
                              </div>
                              <span className={`rounded-full border px-2 py-0.5 text-[9px] uppercase tracking-wider ${statusClass(status)}`}>{status}</span>
                            </div>
                            <div className="mt-3 space-y-1.5">
                              {card.metrics.length ? card.metrics.slice(0, 5).map((row) => (
                                <div key={row.key} className="flex items-start justify-between gap-2 rounded bg-black/25 px-2 py-1 text-[11px]">
                                  <span className="text-slate-500">{row.key}</span>
                                  <span className="max-w-[55%] truncate text-right font-mono text-slate-200">{formatUnknown(row.value)}</span>
                                </div>
                              )) : (
                                <div className="rounded bg-black/25 px-2 py-1 text-[11px] text-slate-500">{language === 'zh' ? '暂无结构化指标' : 'No structured metrics'}</div>
                              )}
                            </div>
                            {card.tool?.error && (
                              <div className="mt-2 rounded border border-red-500/20 bg-red-500/10 px-2 py-1 text-[10px] text-red-200">{card.tool.error}</div>
                            )}
                            {card.tool?.trust_label && (
                              <div className={`mt-2 inline-flex rounded border px-2 py-0.5 text-[10px] ${getTrustClass(card.tool.trust_label)}`}>
                                trust: {formatUnknown(card.tool.trust_label)}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-emerald-100">
                        <CheckCircle2 size={16} />
                        {language === 'zh' ? '支持证据' : 'Supporting evidence'}
                      </div>
                      <div className="space-y-2">
                        {result.report.supporting_evidence?.length ? result.report.supporting_evidence.map((item, idx) => (
                          <div key={idx} className="rounded-lg border border-emerald-400/15 bg-black/20 px-3 py-2 text-xs leading-relaxed text-emerald-50/80">{item}</div>
                        )) : (
                          <div className="text-xs text-slate-500">{language === 'zh' ? '暂无支持证据' : 'No supporting evidence'}</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-amber-400/20 bg-amber-400/5 p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-amber-100">
                        <AlertTriangle size={16} />
                        {language === 'zh' ? '不确定性与人工复核' : 'Uncertainty and review gates'}
                      </div>
                      <div className="space-y-2">
                        {result.report.uncertainty_flags?.length ? result.report.uncertainty_flags.map((item, idx) => (
                          <div key={idx} className="rounded-lg border border-amber-400/15 bg-black/20 px-3 py-2 text-xs leading-relaxed text-amber-50/80">{item}</div>
                        )) : (
                          <div className="text-xs text-slate-500">{language === 'zh' ? '暂无风险提示' : 'No risk flags'}</div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <Database size={16} className="text-cyan-300" />
                        {language === 'zh' ? '相似病例分布' : 'Similar cases'}
                      </div>
                      <div className="space-y-2">
                        {result.similar_cases.length ? result.similar_cases.slice(0, 5).map((item, idx) => (
                          <div key={`${item.patient_id}-${idx}`} className="rounded-lg bg-black/25 px-3 py-2">
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-mono text-slate-200">{item.patient_id ?? `case-${idx + 1}`}</span>
                              <span className="text-cyan-200">{numericPercent(item.similarity)}%</span>
                            </div>
                            <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                              <span>{item.data_source}</span>
                              <span>{item.T_stage}</span>
                            </div>
                          </div>
                        )) : (
                          <div className="text-xs text-slate-500">{language === 'zh' ? '暂无相似病例' : 'No similar cases'}</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <FileSearch size={16} className="text-sky-300" />
                        {language === 'zh' ? '报告文本线索' : 'Report text cues'}
                      </div>
                      <div className="space-y-2">
                        {getReportCues(result.tool_evidence.report).length ? getReportCues(result.tool_evidence.report).map((cue, idx) => (
                          <div key={`${cue.cue}-${idx}`} className="rounded-lg bg-black/25 px-3 py-2">
                            <div className="font-mono text-xs text-sky-200">{cue.cue}</div>
                            <div className="mt-1 text-[10px] text-slate-500">{formatUnknown(cue.matched_terms)}</div>
                          </div>
                        )) : (
                          <div className="text-xs text-slate-500">{language === 'zh' ? '暂无文本线索' : 'No report cues'}</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <RefreshCw size={16} className="text-violet-300" />
                        {language === 'zh' ? 'Memory / 轨迹' : 'Memory / trace'}
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="rounded-lg bg-black/25 px-3 py-2">
                          <div className="text-slate-500">{language === 'zh' ? '候选记忆' : 'Memory candidates'}</div>
                          <div className="mt-1 font-mono text-slate-100">{result.report.memory_update_candidates?.length ?? 0}</div>
                        </div>
                        <div className="rounded-lg bg-black/25 px-3 py-2">
                          <div className="text-slate-500">{language === 'zh' ? '工具调用轨迹' : 'Tool traces'}</div>
                          <div className="mt-1 font-mono text-slate-100">{result.traces?.length ?? 0}</div>
                        </div>
                        {result.trajectory_ref?.path && (
                          <div className="rounded-lg bg-black/25 px-3 py-2">
                            <div className="text-slate-500">{language === 'zh' ? '轨迹文件' : 'Trace file'}</div>
                            <div className="mt-1 break-all font-mono text-[10px] text-violet-100/80">{result.trajectory_ref.path}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {!!result.report.dynamic_report_draft && (
                    <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-4">
                      <div className="mb-4 flex items-center justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2 text-sm font-bold text-emerald-100">
                            <FileText size={16} />
                            {language === 'zh' ? '可复制动态报告草稿' : 'Copy-ready dynamic report draft'}
                          </div>
                          <div className="mt-1 text-xs text-emerald-100/60">{result.report.dynamic_report_draft.title}</div>
                        </div>
                        <button
                          onClick={copyDraft}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100 transition hover:bg-emerald-400/20"
                        >
                          {copiedDraft ? <CheckCircle2 size={13} /> : <Clipboard size={13} />}
                          {copiedDraft ? (language === 'zh' ? '已复制' : 'Copied') : (language === 'zh' ? '复制报告' : 'Copy report')}
                        </button>
                      </div>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        {result.report.dynamic_report_draft.sections.map((section) => (
                          <div key={section.heading} className="rounded-xl border border-white/10 bg-black/20 p-3">
                            <div className="mb-2 text-sm font-bold text-emerald-100">{section.heading}</div>
                            <div className="space-y-1 text-xs leading-relaxed text-slate-300">
                              {section.lines.map((line, idx) => (
                                <div key={`${section.heading}-${idx}`}>{line}</div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                      {copyError && (
                        <div className="mt-3 rounded border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{copyError}</div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                !loading && (
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-center">
                    <Brain size={28} className="mx-auto text-emerald-300" />
                    <div className="mt-3 text-sm font-bold text-white">{language === 'zh' ? '准备对当前病例进行智能分析' : 'Ready to analyze this case'}</div>
                    <button
                      onClick={runAnalysis}
                      className="mt-4 inline-flex items-center gap-2 rounded-lg bg-emerald-300 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-emerald-200"
                    >
                      <Sparkles size={15} />
                      {language === 'zh' ? '开始分析' : 'Start analysis'}
                    </button>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
