'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import { Activity, AlertTriangle, ArrowRight, Brain, CheckCircle2, ChevronRight, Clipboard, Database, FileSearch, FileText, Layers3, Loader2, Microscope, Network, RefreshCw, ScanSearch, ShieldCheck, Sparkles, Workflow, X } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import { AgentAnalysisResponse, AgentReportCue, AgentStep, AgentToolResult, LumenOverride, MaskBoundaryOverride, Patient, RuntimeVerification } from '@/types';
import { maskOverrideToAnalyzePayload } from '@/lib/mask-override';
import { lumenOverrideToAnalyzePayload } from '@/lib/lumen-override';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import type { Language } from '@/lib/i18n';
import { GcUsSignModelMap } from '@/components/GcUsSignModelMap';
import { computeLesionLumenGeometry } from '@/lib/lesion-lumen-geometry';

interface AgentWorkbenchPanelProps {
  patient: Patient | null;
  maskOverride?: MaskBoundaryOverride | null;
  lumenOverride?: LumenOverride | null;
  imagingAssist?: {
    lesionPolygon: number[][];
    lumenPolygon?: number[][];
    lumenBBox?: { x1: number; y1: number; x2: number; y2: number } | null;
    frameSize?: { width: number; height: number } | null;
  } | null;
  gcUsReport?: GcUsReportState | null;
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
  if (stepId.includes('lumen')) return ScanSearch;
  if (stepId.includes('segmentation') || stepId.includes('localization')) return Layers3;
  if (stepId.includes('wall')) return Activity;
  if (stepId.includes('runtime') || stepId.includes('llm_report')) return ShieldCheck;
  if (stepId.includes('gc_us_sign')) return Network;
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
  const stepId = step.step_id || '';
  const outputs = step.outputs || {};
  if (stepId.includes('gc_us_sign')) {
    const items = Array.isArray(outputs.items) ? outputs.items : [];
    return `GC-US signs=${items.length} status=${formatUnknown(outputs.status)} score=${formatUnknown(outputs.normalized_i)}`;
  }
  if (stepId.includes('dino_sign_fusion')) {
    const signs = outputs.structured_signs as Record<string, unknown> | undefined;
    return [
      `DINO=${formatUnknown((outputs.dino as Record<string, unknown> | undefined)?.available)}`,
      `morph=${formatUnknown(signs?.morphology)}`,
      `wall=${formatUnknown(signs?.wall)}`,
      `lumen=${formatUnknown(signs?.lumen)}`,
    ].join(' · ');
  }
  if (stepId.includes('lumen')) {
    const source = outputs.lumen_source || outputs.override_source || outputs.roi_source;
    return `lumen=${formatUnknown(source)} bbox=${formatUnknown(outputs.lumen_bbox)} polygon=${Array.isArray(outputs.lumen_polygon) ? outputs.lumen_polygon.length : 0}pt`;
  }
  if (outputs.recommended_t_stage) return `${outputs.recommended_t_stage} / ${outputs.confidence ?? 'unknown'}`;
  if (outputs.top1_stage) return `${outputs.top1_stage} ${outputs.top1_prob ?? ''}`.trim();
  if (outputs.current_image_dino_feature_panel_url) return 'DINO feature panel ready';
  if (outputs.roi_source) return `roi=${outputs.roi_source}`;
  if (outputs.lesion_area_ratio !== undefined) return `area=${outputs.lesion_area_ratio}`;
  if (outputs.clinical_risk_score !== undefined) return `risk=${outputs.clinical_risk_score}`;
  if (outputs.retrieved_count !== undefined) {
    const majority = outputs.majority_stage ? ` majority=${outputs.majority_stage}` : '';
    return `${outputs.retrieved_count} retrieved${majority}`;
  }
  if (outputs.memory_candidate_count !== undefined) return `${outputs.memory_candidate_count} memory candidates`;
  if (outputs.available !== undefined) return `available=${outputs.available}`;
  return step.status;
}

type RealtimeStepRecord = {
  step?: number;
  step_id?: string;
  agent_name?: string;
  tool_name?: string | null;
  status?: string;
  observation?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
  explanation?: string;
  figure_paths?: string[];
};

function buildRealtimeAgentStep(record: RealtimeStepRecord, fallbackOrder: number): AgentStep {
  const stepId = String(record.step_id || `step_${fallbackOrder}`);
  const outputs = record.observation && typeof record.observation === 'object' ? record.observation : {};
  const inputs = record.inputs && typeof record.inputs === 'object' ? record.inputs : {};
  return {
    order: Number(record.step) || fallbackOrder,
    step_id: stepId,
    title: String(record.agent_name || stepId),
    intent: '后端工具事件已完成',
    decision: String(record.status || 'completed'),
    tool_name: record.tool_name || null,
    status: String(record.status || 'completed'),
    inputs,
    outputs,
    reasoning: String(record.explanation || ''),
    visual_refs: record.figure_paths?.length ? { figure_paths: record.figure_paths } : {},
  };
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

type ImageZoomPayload = { src: string; title: string; subtitle?: string };

const ImageZoomContext = React.createContext<((payload: ImageZoomPayload) => void) | undefined>(undefined);

function ImageLightboxModal({
  payload,
  onClose,
  language,
}: {
  payload: ImageZoomPayload;
  onClose: () => void;
  language: Language;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[300000] flex items-center justify-center bg-black/90 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="fixed top-[72px] right-4 z-[300001] flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-neutral-900/95 text-gray-100 shadow-2xl hover:border-red-400/60 hover:bg-red-500/20"
        aria-label={language !== 'en' ? '关闭' : 'Close'}
      >
        <X size={22} />
      </button>
      <div
        className="relative flex max-h-[calc(100vh-6rem)] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-white/15 bg-[#0a0a0a] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-white/10 px-4 py-3">
          <div className="text-sm font-bold text-white">{payload.title}</div>
          {payload.subtitle && <div className="mt-1 text-xs text-slate-400">{payload.subtitle}</div>}
        </div>
        <div className="relative min-h-[50vh] flex-1 bg-black">
          <Image src={payload.src} alt={payload.title} fill sizes="100vw" className="object-contain p-2" unoptimized />
        </div>
      </div>
    </div>
  );
}

function VisualFrame({
  title,
  subtitle,
  src,
  children,
  zoomable = true,
}: {
  title: string;
  subtitle?: string;
  src?: string;
  children?: React.ReactNode;
  zoomable?: boolean;
}) {
  const openZoom = React.useContext(ImageZoomContext);

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2">
        <div>
          <div className="text-xs font-bold text-slate-100">{title}</div>
          {subtitle && <div className="mt-0.5 text-[10px] text-slate-500">{subtitle}</div>}
        </div>
        {src && zoomable && openZoom && (
          <span className="shrink-0 text-[10px] text-cyan-400/80">{/* hint rendered on image */}</span>
        )}
      </div>
      {src ? (
        <button
          type="button"
          className="relative block h-44 w-full cursor-zoom-in bg-black text-left"
          onClick={() => {
            if (zoomable && openZoom) {
              openZoom({ src, title, subtitle });
            }
          }}
          aria-label={`${title} enlarge`}
        >
          <Image src={src} alt={title} fill sizes="(max-width: 768px) 100vw, 50vw" className="object-contain" unoptimized />
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.08)_1px,transparent_1px)] bg-[size:24px_24px]" />
          {zoomable && openZoom && (
            <span className="pointer-events-none absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-[10px] text-cyan-200">
              点击放大
            </span>
          )}
        </button>
      ) : (
        <div className="flex h-44 items-center justify-center bg-black text-xs text-slate-600">
          No image output
        </div>
      )}
      {children && <div className="border-t border-white/10 p-3">{children}</div>}
    </div>
  );
}

export function AgentWorkbenchPanel({
  patient,
  maskOverride = null,
  lumenOverride = null,
  imagingAssist = null,
  gcUsReport = null,
  onAnalysisComplete,
}: AgentWorkbenchPanelProps) {
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
  const [imageLightbox, setImageLightbox] = useState<ImageZoomPayload | null>(null);
  const [memoryActionPending, setMemoryActionPending] = useState<string | null>(null);
  const [memoryActionMessage, setMemoryActionMessage] = useState<string | null>(null);
  const lastRunGeometrySignatureRef = React.useRef('');

  const geometryInputs = useMemo(() => {
    const lesionPolygon = maskOverride?.mask_polygon || [];
    const lumenPolygon = lumenOverride?.lumen_polygon || [];
    const lumenBBox = lumenOverride?.lumen_bbox || null;
    const geometry = computeLesionLumenGeometry(lesionPolygon, lumenPolygon, lumenBBox);
    const lumenReady = lumenPolygon.length >= 3 || Boolean(lumenBBox);
    return {
      lesionPolygon,
      lumenPolygon,
      lumenBBox,
      geometry,
      lesionReady: lesionPolygon.length >= 3,
      lumenReady,
      ready: lesionPolygon.length >= 3 && lumenReady,
      frameSize: maskOverride && lumenOverride
        ? { width: maskOverride.imageWidth, height: maskOverride.imageHeight }
        : null,
    };
  }, [
    lumenOverride,
    maskOverride,
  ]);

  const effectiveMaskOverride = maskOverride;
  const effectiveLumenOverride = lumenOverride;
  const liveGeometryPending = Boolean(
    !geometryInputs.ready
    && (
      imagingAssist?.lesionPolygon?.length
      || imagingAssist?.lumenPolygon?.length
      || imagingAssist?.lumenBBox
    ),
  );

  const geometrySignature = useMemo(
    () => JSON.stringify({
      lesion: geometryInputs.lesionPolygon,
      lumen: geometryInputs.lumenPolygon,
      lumen_bbox: geometryInputs.lumenBBox,
      mask_updated_at: maskOverride?.updated_at || null,
      lumen_updated_at: lumenOverride?.updated_at || null,
    }),
    [
      geometryInputs.lesionPolygon,
      geometryInputs.lumenBBox,
      geometryInputs.lumenPolygon,
      lumenOverride?.updated_at,
      maskOverride?.updated_at,
    ],
  );

  const openImageLightbox = React.useCallback((payload: ImageZoomPayload) => {
    setImageLightbox(payload);
  }, []);

  useEffect(() => {
    setError(null);
    setResult(null);
    setSessionId(undefined);
    setModalOpen(false);
    setWorkbenchOpen(false);
    setActiveStep(0);
    setLiveSteps([]);
    setStreamLogs([]);
    setRuntimeVerification(null);
    setCopiedDraft(false);
    setCopyError(null);
    lastRunGeometrySignatureRef.current = '';
  }, [patient?.id]);

  useEffect(() => {
    if (!loading && liveSteps.length > 0) {
      setActiveStep(Math.max(liveSteps.length - 1, 0));
    }
  }, [liveSteps.length, loading]);

  const copyDraft = async () => {
    const doctorEdited = Boolean(
      gcUsReport
      && (gcUsReport.report.doctor_edited || gcUsReport.reference_stage.source === 'doctor'),
    );
    const draftText = doctorEdited
      ? gcUsReport?.report.prose
      : result?.report.dynamic_report_draft?.full_text || gcUsReport?.report.prose;
    if (!draftText) return;
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(draftText);
      setCopiedDraft(true);
      window.setTimeout(() => setCopiedDraft(false), 1600);
    } catch {
      setCopyError(language !== 'en' ? '浏览器暂未授权剪贴板，请先点击页面后重试。' : 'Clipboard permission is not available. Focus the page and retry.');
    }
  };

  const submitMemoryCandidateAction = async (
    recordId: string,
    action: 'accept' | 'reject' | 'defer',
  ) => {
    if (!patient || !recordId) return;
    setMemoryActionPending(recordId);
    setMemoryActionMessage(null);
    try {
      const response = await fetch('/api/agent/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patient.patient_id,
          case_id: patient.id,
          session_id: sessionId,
          record_id: recordId,
          action,
          memory_store: result?.memory_store_ref?.path,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.error || 'Memory feedback failed');
      }
      setMemoryActionMessage(
        language !== 'en'
          ? `Memory 候选已${action === 'accept' ? '接受' : action === 'reject' ? '拒绝' : '暂缓'}`
          : `Memory candidate ${action} recorded`,
      );
      if (result?.report.memory_update_candidates) {
        setResult({
          ...result,
          report: {
            ...result.report,
            memory_update_candidates: result.report.memory_update_candidates.map((candidate) => (
              candidate.record_id === recordId
                ? { ...candidate, status: action === 'reject' ? 'rejected' : 'candidate' }
                : candidate
            )),
          },
        });
      }
    } catch (err) {
      setMemoryActionMessage(err instanceof Error ? err.message : 'Memory feedback failed');
    } finally {
      setMemoryActionPending(null);
    }
  };

  const runAnalysis = async () => {
    if (!patient || loading) return;
    if (!geometryInputs.lesionReady || !geometryInputs.lumenReady) {
      setWorkbenchOpen(true);
      setError(
        language !== 'en'
          ? `Agent 未启动：${!geometryInputs.lesionReady ? '请先确认病灶分割轮廓' : ''}${!geometryInputs.lesionReady && !geometryInputs.lumenReady ? '；' : ''}${!geometryInputs.lumenReady ? '请先确认胃腔轮廓或胃腔框' : ''}`
          : `Agent blocked: ${!geometryInputs.lesionReady ? 'confirm the lesion contour first' : ''}${!geometryInputs.lesionReady && !geometryInputs.lumenReady ? '; ' : ''}${!geometryInputs.lumenReady ? 'confirm the lumen contour or box first' : ''}`,
      );
      return;
    }
    lastRunGeometrySignatureRef.current = geometrySignature;
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
          memory_enabled: true,
          gc_us_report: gcUsReport || undefined,
          ...maskOverrideToAnalyzePayload(effectiveMaskOverride),
          ...lumenOverrideToAnalyzePayload(effectiveLumenOverride),
          geometry_gate: {
            confirmed_lesion: geometryInputs.lesionReady,
            confirmed_lumen: geometryInputs.lumenReady,
            relation: geometryInputs.geometry.relation,
            overlap: geometryInputs.geometry.relation === 'overlap',
            distance_px: geometryInputs.geometry.distancePx,
            quality: geometryInputs.geometry.quality,
            source: 'persisted_override',
          },
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
            step?: AgentStep | string;
            record?: RealtimeStepRecord;
            result?: AgentAnalysisResponse;
            verification?: RuntimeVerification;
            message?: string;
            error?: string;
          };

          if (event.event === 'step_complete' && event.record) {
            setLiveSteps((prev) => {
              const realtimeStep = buildRealtimeAgentStep(event.record as RealtimeStepRecord, prev.length + 1);
              const existingIndex = prev.findIndex((item) => item.step_id === realtimeStep.step_id);
              if (existingIndex >= 0) {
                const next = [...prev];
                next[existingIndex] = realtimeStep;
                setActiveStep(existingIndex);
                return next;
              }
              const next = [...prev, realtimeStep];
              setActiveStep(next.length - 1);
              return next;
            });
          } else if (event.event === 'agent_step' && event.step && typeof event.step !== 'string') {
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
    if (
      (result || liveSteps.length > 0 || error)
      && !loading
      && !workbenchOpen
      && lastRunGeometrySignatureRef.current === geometrySignature
    ) {
      setWorkbenchOpen(true);
      return;
    }
    void runAnalysis();
  };

  const handleLauncherClickRef = React.useRef(handleLauncherClick);
  handleLauncherClickRef.current = handleLauncherClick;

  // AssistHub focus request (additive; bottom launcher unchanged)
  useEffect(() => {
    const handler = () => {
      handleLauncherClickRef.current();
    };
    window.addEventListener('gastric:focus-agent', handler);
    return () => window.removeEventListener('gastric:focus-agent', handler);
  }, []);

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
        title: language !== 'en' ? '分割 / ROI 定位' : 'Segmentation / ROI',
        icon: Layers3,
        tool: result.tool_evidence.segmentation,
        metrics: getToolMetricRows(result.tool_evidence.segmentation, ['roi_source', 'lesion_area_ratio', 'mask_available', 'image_height', 'image_width']),
      },
      {
        key: 'lumen',
        title: language !== 'en' ? '胃腔检测' : 'Lumen detection',
        icon: ScanSearch,
        tool: result.tool_evidence.lumen_detection ?? { available: false },
        metrics: getToolMetricRows(result.tool_evidence.lumen_detection, ['lumen_detected', 'lumen_confidence', 'lumen_area_ratio']),
      },
      {
        key: 'wall',
        title: language !== 'en' ? '壁层证据 (SDF)' : 'Wall evidence',
        icon: Activity,
        tool: result.tool_evidence.wall_evidence ?? { available: false },
        metrics: getToolMetricRows(result.tool_evidence.wall_evidence, ['penetration_risk', 'evidence_source', 'available']),
      },
      {
        key: 'classification',
        title: language !== 'en' ? 'T 分期分类' : 'T-stage classifier',
        icon: Microscope,
        tool: result.tool_evidence.classification,
        metrics: getToolMetricRows(result.tool_evidence.classification, ['top1_stage', 'top1_prob', 'top2_stage', 'top2_prob', 'uncertainty']),
      },
      {
        key: 'morphology',
        title: language !== 'en' ? '形态学证据' : 'Morphology',
        icon: Activity,
        tool: result.tool_evidence.morphology,
        metrics: getToolMetricRows(result.tool_evidence.morphology, ['boundary_irregularity', 'lesion_area_ratio', 'convexity', 'solidity', 'compactness']),
      },
      {
        key: 'gc_us_signs',
        title: language !== 'en' ? '核心征象算法链' : 'Core sign model chain',
        icon: Network,
        tool: result.tool_evidence.gc_us_signs ?? { available: false },
        metrics: getToolMetricRows(result.tool_evidence.gc_us_signs, ['status', 'normalized_i', 'confidence', 'ct_stage', 'evidence_role']),
      },
      {
        key: 'dino',
        title: language !== 'en' ? '区域特征证据' : 'Region-feature evidence',
        icon: Sparkles,
        tool: result.tool_evidence.dino,
        metrics: getToolMetricRows(result.tool_evidence.dino, ['available', 'mask_available', 'fusion_mode', 'uncertainty_flags']),
      },
      {
        key: 'clinical',
        title: language !== 'en' ? '临床风险' : 'Clinical risk',
        icon: ShieldCheck,
        tool: result.tool_evidence.clinical,
        metrics: getToolMetricRows(result.tool_evidence.clinical, ['clinical_risk_score', 'factors_available', 'risk_factors', 'protective_factors']),
      },
      {
        key: 'report',
        title: language !== 'en' ? '报告文本线索' : 'Report cues',
        icon: FileSearch,
        tool: result.tool_evidence.report,
        metrics: getToolMetricRows(result.tool_evidence.report, ['sections_available', 'text_length', 'report_source']),
      },
      {
        key: 'clinical_decision',
        title: language !== 'en' ? '跨模态临床决策' : 'Cross-modal clinical decision',
        icon: Network,
        tool: result.tool_evidence.clinical_decision,
        metrics: getToolMetricRows(result.tool_evidence.clinical_decision, ['status', 'requires_mdt', 'provisional_stage', 'missing_modalities']),
      },
      {
        key: 'memory',
        title: language !== 'en' ? '相似病例 memory' : 'Similar-case memory',
        icon: Database,
        tool: (() => {
          const ragStep = (result.agent_steps || []).find((step) => String(step.step_id || '').includes('case_rag'));
          const outputs = (ragStep?.outputs || {}) as Record<string, unknown>;
          const runtime = (outputs.runtime_invocation && typeof outputs.runtime_invocation === 'object'
            ? outputs.runtime_invocation
            : {}) as Record<string, unknown>;
          const available = Boolean(outputs.available ?? result.similar_cases.length > 0);
          const backend = String(
            runtime.backend
            || outputs.memory_version
            || (available ? 'case_similarity' : 'unavailable'),
          );
          const reason = !available
            ? String(outputs.reason || runtime.reason || 'index_or_hits_unavailable')
            : undefined;
          return {
            available,
            backend_id: backend,
            trust_label: result.tool_evidence.classification?.trust_label ?? 'caution',
            reason,
            memory_version: String(outputs.memory_version || runtime.memory_version || ''),
            case_count: Number(runtime.case_count || result.similar_cases.length || 0),
          };
        })(),
        metrics: [
          { key: 'retrieved_cases', value: result.similar_cases.length },
          { key: 'majority_stage', value: result.report.similar_case_summary?.majority_stage },
          {
            key: 'memory_version',
            value: (() => {
              const ragStep = (result.agent_steps || []).find((step) => String(step.step_id || '').includes('case_rag'));
              const outputs = (ragStep?.outputs || {}) as Record<string, unknown>;
              const runtime = (outputs.runtime_invocation && typeof outputs.runtime_invocation === 'object'
                ? outputs.runtime_invocation
                : {}) as Record<string, unknown>;
              return outputs.memory_version || runtime.memory_version || 'n/a';
            })(),
          },
          {
            key: 'unavailable_reason',
            value: result.similar_cases.length
              ? undefined
              : (() => {
                const ragStep = (result.agent_steps || []).find((step) => String(step.step_id || '').includes('case_rag'));
                const outputs = (ragStep?.outputs || {}) as Record<string, unknown>;
                const runtime = (outputs.runtime_invocation && typeof outputs.runtime_invocation === 'object'
                  ? outputs.runtime_invocation
                  : {}) as Record<string, unknown>;
                return outputs.reason || runtime.reason || 'no_hits';
              })(),
          },
        ],
      },
    ];
  }, [language, result]);

  const adaptiveSteps = useMemo<AgentDisplayStep[]>(() => {
    const backendSteps = liveSteps.length ? liveSteps : result?.agent_steps;
    if (!backendSteps?.length) return [];
    return backendSteps.map((step) => ({
      key: step.step_id,
      title: step.title,
      detail: step.reasoning || step.intent,
      icon: getStepIcon(step.step_id),
      output: getStepOutputSummary(step),
      backendStep: step,
    }));
  }, [liveSteps, result]);

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
        label: language !== 'en' ? '分类模型' : 'Classifier',
        value: formatUnknown(result.tool_evidence.classification?.top1_stage),
        weight: numericPercent(result.tool_evidence.classification?.top1_prob, 0),
      },
      {
        label: language !== 'en' ? '相似病例多数票' : 'Similar-case majority',
        value: formatUnknown(result.report.similar_case_summary?.majority_stage),
        weight: Math.min(result.similar_cases.length * 20, 100),
      },
      {
        label: language !== 'en' ? '临床风险' : 'Clinical risk',
        value: formatUnknown(result.tool_evidence.clinical?.clinical_risk_score),
        weight: numericPercent(result.tool_evidence.clinical?.clinical_risk_score, 0),
      },
      {
        label: language !== 'en' ? '分割质量' : 'Segmentation quality',
        value: formatUnknown(result.tool_evidence.segmentation?.roi_source),
        weight: result.tool_evidence.segmentation?.mask_available ? 90 : 45,
      },
      {
        label: language !== 'en' ? '报告线索' : 'Report cues',
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

    if (stepId.includes('gc_us_sign')) {
      const signAnalysis = result?.tool_evidence.gc_us_signs || outputs as AgentToolResult;
      const gate = signAnalysis.structural_gate && typeof signAnalysis.structural_gate === 'object'
        ? signAnalysis.structural_gate as Record<string, unknown>
        : {};
      const items = Array.isArray(signAnalysis.items) ? signAnalysis.items : [];
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.25fr_0.75fr]">
          <GcUsSignModelMap
            signAnalysis={signAnalysis}
            zh={language !== 'en'}
            showGeometry
          />
          <div className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
            <div className="text-sm font-black text-amber-100">
              {language !== 'en' ? '软评分与结构闸门' : 'Soft score and structural gate'}
            </div>
            <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
              {language !== 'en'
                ? '评分用于整理证据，墙壁几何代理不会单独解锁确定 cT。'
                : 'The score organizes evidence; wall geometry proxies do not unlock definite cT alone.'}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              {[
                [language !== 'en' ? '已评分项' : 'Scored items', items.length],
                [language !== 'en' ? '总分' : 'Total', `${formatUnknown(signAnalysis.total)}/${formatUnknown(signAnalysis.max_total)}`],
                [language !== 'en' ? 'cT 输出' : 'cT output', signAnalysis.ct_stage],
                [language !== 'en' ? '确定闸门' : 'Definite gate', gate.unlock_definite_ct],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{String(label)}</div>
                  <div className="mt-1 font-mono text-amber-100">{formatUnknown(value)}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-lg border border-amber-300/20 bg-black/20 p-3 text-[10px] leading-relaxed text-amber-100/80">
              {formatUnknown(signAnalysis.mapping_note || signAnalysis.risk_semantics)}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('dino_sign_fusion')) {
      const signs = (outputs.structured_signs || {}) as Record<string, unknown>;
      const dino = (outputs.dino || {}) as Record<string, unknown>;
      const supporting = Array.isArray(outputs.supporting_evidence)
        ? outputs.supporting_evidence
        : [];
      const uncertainty = Array.isArray(outputs.uncertainty_flags)
        ? outputs.uncertainty_flags
        : [];
      const provenance = (outputs.provenance || {}) as Record<string, unknown>;
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
          <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
            <div className="text-sm font-black text-cyan-100">
              {language !== 'en' ? 'DINO + 结构化征象' : 'DINO + structured signs'}
            </div>
            <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
              {language !== 'en'
                ? '此步骤提供可追溯证据，不覆盖 T 分期主模型。'
                : 'Evidence-only fusion; it does not replace the T-stage model.'}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              {[
                ['DINO', dino.available],
                ['形态征象', signs.morphology],
                ['胃壁证据', signs.wall],
                ['胃腔对齐', signs.lumen],
                ['融合模式', outputs.fusion_mode],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{String(label)}</div>
                  <div className="mt-1 font-mono text-emerald-100">{formatUnknown(value)}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 text-[10px] text-slate-500">
              {language !== 'en' ? '探针来源' : 'Probe source'}：{formatUnknown(provenance.probe)}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">
              {language !== 'en' ? '支持与限制' : 'Support and limits'}
            </div>
            <div className="mt-3 space-y-2 text-xs">
              {supporting.slice(0, 4).map((item, index) => (
                <div key={`dino-sign-support-${index}`} className="rounded bg-emerald-300/10 px-3 py-2 text-emerald-100">
                  {formatUnknown(item)}
                </div>
              ))}
              {uncertainty.slice(0, 4).map((item, index) => (
                <div key={`dino-sign-uncertainty-${index}`} className="rounded bg-amber-300/10 px-3 py-2 text-amber-100">
                  {formatUnknown(item)}
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (!currentBackendStep || stepId.includes('intake')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <VisualFrame title={language !== 'en' ? '当前病例原始超声' : 'Current case ultrasound'} subtitle={patient.id_short} src={patient.image_url} />
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">{language !== 'en' ? '病例资料盘点' : 'Case evidence inventory'}</div>
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

    if (stepId.includes('lumen')) {
      const bbox = outputs.lumen_bbox && typeof outputs.lumen_bbox === 'object'
        ? outputs.lumen_bbox as Record<string, unknown>
        : null;
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <VisualFrame
            title={language !== 'en' ? '胃腔 YOLO 检测框' : 'Lumen YOLO detection box'}
            subtitle={
              outputs.lumen_detected
                ? (language !== 'en'
                  ? `置信度 ${formatUnknown(outputs.lumen_confidence)} · 面积比 ${formatUnknown(outputs.lumen_area_ratio)}`
                  : `conf ${formatUnknown(outputs.lumen_confidence)} · area ${formatUnknown(outputs.lumen_area_ratio)}`)
                : (language !== 'en' ? '未检测到胃腔，仍显示当前帧' : 'no lumen box; showing current frame')
            }
            src={
              typeof refs.lumen_detection_overlay_url === 'string'
                ? refs.lumen_detection_overlay_url
                : patient.image_url
            }
          />
          <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
            <div className="text-sm font-black text-cyan-100">{language !== 'en' ? '检测输出' : 'Detection outputs'}</div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
              {[
                ['lumen_detected', outputs.lumen_detected],
                ['lumen_confidence', outputs.lumen_confidence],
                ['lumen_area_ratio', outputs.lumen_area_ratio],
                ['available', outputs.available],
              ].map(([key, value]) => (
                <div key={String(key)} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                  <div className="text-slate-500">{String(key)}</div>
                  <div className="mt-1 font-mono text-cyan-100">{formatUnknown(value)}</div>
                </div>
              ))}
            </div>
            {bbox && (
              <div className="mt-4 rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs font-mono text-slate-200">
                bbox: x1={formatUnknown(bbox.x1)} y1={formatUnknown(bbox.y1)} x2={formatUnknown(bbox.x2)} y2={formatUnknown(bbox.y2)}
              </div>
            )}
          </div>
        </div>
      );
    }

    if (stepId.includes('segmentation') || stepId.includes('localization')) {
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
          <VisualFrame title={language !== 'en' ? '预测分割叠加图' : 'Predicted segmentation overlay'} subtitle="model-generated overlay" src={typeof refs.predicted_overlay_url === 'string' ? refs.predicted_overlay_url : patient.overlay_url || patient.image_url} />
          <VisualFrame title={language !== 'en' ? '预测 mask' : 'Predicted mask'} subtitle="binary model mask" src={typeof refs.predicted_mask_url === 'string' ? refs.predicted_mask_url : undefined} />
          <VisualFrame title={language !== 'en' ? '预测 ROI 裁剪' : 'Predicted ROI crop'} subtitle={formatUnknown(outputs.roi_source)} src={typeof refs.predicted_roi_url === 'string' ? refs.predicted_roi_url : patient.roi_url || patient.image_url}>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              {['roi_source', 'mask_available', 'lesion_area_ratio', 'image_height', 'image_width'].map((key) => (
                <div key={key} className="rounded bg-black/25 px-2 py-1">
                  <span className="text-slate-500">{key}</span>
                  <div className="truncate font-mono text-cyan-100">{formatUnknown(outputs[key])}</div>
                </div>
              ))}
            </div>
          </VisualFrame>
          <VisualFrame title={language !== 'en' ? '胃壁穿透风险热力图' : 'Wall penetration risk heatmap'} subtitle={language !== 'en' ? '由预测 mask / ROI 生成的胃壁风险代理图' : 'wall-risk proxy from predicted mask / ROI'} src={typeof refs.wall_penetration_heatmap_url === 'string' ? refs.wall_penetration_heatmap_url : undefined} />
        </div>
      );
    }

    if (stepId.includes('wall_evidence') || stepId.includes('wall_analysis')) {
      const panelMode = formatUnknown(outputs.wall_panel_mode);
      const liveSubtitle = language !== 'en'
        ? `当前选中帧实时生成 · ${panelMode}`
        : `live on selected frame · ${panelMode}`;
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <VisualFrame
            title={language !== 'en' ? '真实胃壁分析面板' : 'Real wall analysis panel'}
            subtitle={liveSubtitle}
            src={
              visualRefPick(refs, [
                'real_wall_analysis_panel_url',
                'wall_penetration_heatmap_url',
                'wall_layer_profile_url',
              ])
            }
          />
          <VisualFrame
            title={language !== 'en' ? '胃壁穿透风险热力图' : 'Wall penetration risk heatmap'}
            subtitle={language !== 'en' ? '预测 mask 驱动的风险代理' : 'mask-driven risk proxy'}
            src={typeof refs.wall_penetration_heatmap_url === 'string' ? refs.wall_penetration_heatmap_url : undefined}
          />
          <VisualFrame
            title={language !== 'en' ? '胃壁层剖面' : 'Wall layer profile'}
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
            title={language !== 'en' ? '真实胃壁分析面板' : 'Real wall analysis panel'}
            subtitle={
              language !== 'en'
                ? '基于当前选中图 + 预测 mask 实时生成'
                : 'live from selected image + predicted mask'
            }
            src={
              visualRefPick(refs, [
                'real_wall_analysis_panel_url',
                'wall_penetration_heatmap_url',
                'wall_layer_profile_url',
              ])
            }
          />
          <VisualFrame title={language !== 'en' ? '胃壁层厚度剖面' : 'Gastric wall layer profile'} subtitle={language !== 'en' ? '沿 ROI 横向的相对壁层信号' : 'relative wall signal along ROI'} src={typeof refs.wall_layer_profile_url === 'string' ? refs.wall_layer_profile_url : undefined} />
          <div className="rounded-xl border border-lime-300/20 bg-lime-300/5 p-4">
            <div className="text-sm font-black text-lime-100">{language !== 'en' ? '形态学指标' : 'Morphology metrics'}</div>
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
            <VisualFrame
              title={language !== 'en' ? '真实 DINO 多模态证据面板' : 'Real DINO multimodal evidence panel'}
              subtitle={
                language !== 'en'
                  ? '优先磁盘缓存；若无则 analyze_case 按需调用 generate_clean_agent_case_visual_panels 布局实时生成（较慢）'
                  : 'prefer cached PNG; else on-demand generation via analyze_case (slower)'
              }
              src={visualRefPick(refs, [
                'real_dino_multimodal_panel_url',
                'current_image_dino_feature_panel_url',
              ])}
            />
            <VisualFrame title={language !== 'en' ? '分类概率图' : 'Classification probability plot'} subtitle="model-generated probability plot" src={typeof refs.classification_probabilities_url === 'string' ? refs.classification_probabilities_url : undefined} />
          </div>
          <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/5 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-black text-emerald-100">{language !== 'en' ? 'T 分期概率输出' : 'T-stage probability output'}</div>
                <div className="mt-1 text-xs text-slate-500">{language !== 'en' ? '显示 top-1、top-2 和相邻分期不确定性。' : 'Shows top-1, top-2, and adjacent-stage uncertainty.'}</div>
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
      const dinoGrid = formatUnknown(outputs.dino_token_grid);
      const dinoNote = formatUnknown(outputs.dino_note);
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <VisualFrame
            title={language !== 'en' ? '当前图像真实 DINO 特征面板' : 'Current-image real DINO feature panel'}
            subtitle={
              language !== 'en'
                ? `真 DINOv3 · 全图 resize ${formatUnknown(outputs.dino_input_size ?? 512)} · token ${dinoGrid}`
                : `real DINOv3 · full-frame resize ${formatUnknown(outputs.dino_input_size ?? 512)} · token ${dinoGrid}`
            }
            src={typeof refs.current_image_dino_feature_panel_url === 'string' ? refs.current_image_dino_feature_panel_url : undefined}
          />
          <div className="space-y-4">
            <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
              <div className="text-sm font-black text-cyan-100">{language !== 'en' ? 'DINO 推理说明' : 'DINO inference notes'}</div>
              <div className="mt-3 space-y-2 text-xs leading-relaxed text-slate-300">
                <p>{language !== 'en' ? '✓ 真实特征：本地 DINOv3 checkpoint 前向，不是梯度 proxy。' : '✓ Real features: local DINOv3 forward, not gradient proxy.'}</p>
                <p>{language !== 'en' ? '✓ 全图模式：整帧 resize 512×512 一次前向，不是 ROI patch 裁剪。' : '✓ Full frame: resize 512×512 single forward, not ROI patch crop.'}</p>
                <p>{language !== 'en' ? '✓ 区域池化：预测 mask 下采样到 token 网格算 affinity。' : '✓ Pooling: predicted mask on token grid for affinity maps.'}</p>
                <p className="text-amber-200/90">{language !== 'en' ? '⚠ 相似病例 saliency 图仍是 Sobel proxy。' : '⚠ Similar-case saliency is still Sobel proxy.'}</p>
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-sm font-black text-white">{language !== 'en' ? 'DINO 调用信息' : 'DINO call details'}</div>
              <div className="mt-4 space-y-3 text-xs">
                {['current_image_dino_model', 'dino_inference_mode', 'dino_input_size', 'dino_token_grid', 'dino_region_pooling', 'current_image_dino_error'].map((key) => (
                  <div key={key} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                    <div className="text-slate-500">{key}</div>
                    <div className="mt-1 break-words font-mono text-cyan-100">{formatUnknown(outputs[key])}</div>
                  </div>
                ))}
              </div>
              {dinoNote !== 'N/A' && <p className="mt-3 text-[11px] leading-relaxed text-slate-400">{dinoNote}</p>}
            </div>
            {typeof refs.real_dino_multimodal_panel_url === 'string' && (
              <VisualFrame
                title={language !== 'en' ? 'DINO 多模态合成面板' : 'DINO multimodal composite'}
                subtitle={language !== 'en' ? '同一次 DINO 推理 + 分类概率' : 'same DINO forward + classification probs'}
                src={refs.real_dino_multimodal_panel_url}
              />
            )}
          </div>
        </div>
      );
    }

    if (stepId.includes('clinical') || stepId.includes('report_text')) {
      const cueList = Array.isArray(outputs.report_cues) ? outputs.report_cues as Array<Record<string, unknown>> : getReportCues(result?.tool_evidence.report);
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-4">
            <div className="text-sm font-black text-amber-100">{language !== 'en' ? '临床风险/校准' : 'Clinical risk calibration'}</div>
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
            <div className="text-sm font-black text-sky-100">{language !== 'en' ? '报告文本线索' : 'Report text cues'}</div>
            <div className="mt-4 space-y-2">
              {cueList.length ? cueList.map((cue, idx) => (
                <div key={`cue-${idx}`} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs">
                  <div className="font-mono text-sky-100">{formatUnknown('cue' in cue ? cue.cue : '')}</div>
                  <div className="mt-1 text-slate-500">{formatUnknown('matched_terms' in cue ? cue.matched_terms : '')}</div>
                </div>
              )) : (
                <div className="rounded-lg border border-dashed border-white/10 p-4 text-xs text-slate-500">{language !== 'en' ? '当前未抽取到明确文本线索。' : 'No explicit report cues extracted.'}</div>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('knowledge')) {
      const snippets = result?.knowledge_context?.length
        ? result.knowledge_context
        : (Array.isArray(outputs.knowledge_snippets) ? outputs.knowledge_snippets as Array<{ source?: string; title?: string; content?: string }> : []);
      const highlights = result?.report.knowledge_highlights ?? [];
      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_0.8fr]">
          <div className="rounded-xl border border-violet-300/20 bg-violet-300/5 p-4">
            <div className="text-sm font-black text-violet-100">{language !== 'en' ? '指南/知识检索' : 'Guideline knowledge retrieval'}</div>
            <div className="mt-4 max-h-[360px] space-y-2 overflow-y-auto custom-scrollbar">
              {snippets.length ? snippets.map((item, idx) => (
                <div key={`knowledge-${idx}`} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs">
                  <div className="font-bold text-violet-100">{item.title || `Snippet ${idx + 1}`}</div>
                  <div className="mt-1 text-[10px] text-slate-500">{item.source}</div>
                  <div className="mt-2 line-clamp-4 leading-relaxed text-slate-400">{item.content}</div>
                </div>
              )) : (
                <div className="rounded-lg border border-dashed border-white/10 p-4 text-xs text-slate-500">
                  {language !== 'en' ? '当前未检索到指南片段。' : 'No guideline snippets retrieved.'}
                </div>
              )}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">{language !== 'en' ? '知识要点摘要' : 'Knowledge highlights'}</div>
            <div className="mt-4 space-y-2">
              {highlights.length ? highlights.map((item, idx) => (
                <div key={`highlight-${idx}`} className="rounded-lg border border-violet-300/20 bg-violet-300/5 px-3 py-2 text-xs text-violet-100">{item}</div>
              )) : (
                <div className="text-xs text-slate-500">{language !== 'en' ? '暂无高亮摘要。' : 'No highlights available.'}</div>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (stepId.includes('retrieval') || stepId.includes('similar_case')) {
      const voteWeights = outputs.similarity_vote_weights && typeof outputs.similarity_vote_weights === 'object' && !Array.isArray(outputs.similarity_vote_weights)
        ? outputs.similarity_vote_weights as Record<string, unknown>
        : {};
      const majorityStage = formatUnknown(outputs.majority_stage ?? result?.report.similar_case_summary?.majority_stage);
      const total = Object.values(stageDistribution).reduce((sum: number, value) => sum + Number(value || 0), 0) || 1;
      const voteStages = ['T1', 'T2', 'T3', 'T4+'] as const;

      return (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
          <div className="space-y-4">
            <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm font-black text-cyan-100">{language !== 'en' ? '相似病例 T 分期投票' : 'Similar-case T-stage vote'}</div>
                <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-xs font-mono text-cyan-100">
                  {language !== 'en' ? '多数票' : 'majority'}: {majorityStage}
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {voteStages.map((stage) => {
                  const countRaw = Number(stageDistribution[stage] || stageDistribution[stage.replace('+', '')] || 0);
                  const countPercent = Math.round((countRaw / total) * 100);
                  const weightRaw = Number(voteWeights[stage] || 0);
                  const weightPercent = Math.round(weightRaw * 100);
                  return (
                    <div key={`dist-${stage}`}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="font-mono text-slate-200">{stage}</span>
                        <span className="font-mono text-cyan-100">
                          {countRaw} {language !== 'en' ? '票' : 'votes'} · {countPercent}%
                          {weightPercent > 0 ? ` · sim ${weightPercent}%` : ''}
                        </span>
                      </div>
                      <div className="h-3 overflow-hidden rounded-full bg-slate-900">
                        <div
                          className="h-full rounded-full bg-linear-to-r from-cyan-400 via-emerald-300 to-lime-200"
                          style={{ width: `${Math.max(countPercent, weightPercent, countRaw > 0 ? 8 : 0)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <VisualFrame
              title={language !== 'en' ? '当前帧区域显著性（非 DINO）' : 'Current-frame saliency (not DINO)'}
              subtitle={language !== 'en' ? 'Sobel 梯度 + mask 加权 proxy，仅作检索辅助' : 'Sobel + mask weighted proxy for retrieval cue only'}
              src={typeof refs.dino_similarity_heatmap_url === 'string' ? refs.dino_similarity_heatmap_url : undefined}
            />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-black text-white">{language !== 'en' ? '检索到的历史相似病例' : 'Retrieved similar cases'}</div>
              <span className="text-[11px] font-mono text-slate-400">
                {formatUnknown(outputs.similar_cases_with_preview_count ?? 0)} / {similarCases.length} preview
              </span>
            </div>
            <div className="mt-4">
              <VisualFrame
                title={language !== 'en' ? '相似病例 contact sheet' : 'Similar-case contact sheet'}
                subtitle={
                  language !== 'en'
                    ? `Top-${similarCases.length} 预览 · 按相似度排序`
                    : `Top-${similarCases.length} previews · ranked by similarity`
                }
                src={
                  visualRefPick(refs, [
                    'similar_cases_contact_sheet_url',
                    'dino_similarity_heatmap_url',
                  ])
                }
              />
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {similarCases.slice(0, 6).map((item, idx) => {
                const previewUrl = typeof item.preview_image_url === 'string' ? item.preview_image_url : undefined;
                const stage = formatUnknown(item.T_stage);
                const sim = numericPercent(item.similarity);
                return (
                  <div key={`similar-step-${idx}`} className="overflow-hidden rounded-xl border border-white/10 bg-black/25">
                    {previewUrl ? (
                      <button
                        type="button"
                        className="relative block h-32 w-full cursor-zoom-in bg-black"
                        onClick={() => openImageLightbox({
                          src: previewUrl,
                          title: `${language !== 'en' ? '相似病例' : 'Similar case'} #${formatUnknown('rank' in item ? item.rank : idx + 1)}`,
                          subtitle: `${formatUnknown(item.patient_id)} · ${stage} · sim ${sim}%`,
                        })}
                      >
                        <Image src={previewUrl} alt={`similar-${idx}`} fill sizes="240px" className="object-contain" unoptimized />
                        <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-[9px] text-cyan-200">放大</span>
                      </button>
                    ) : (
                      <div className="flex h-32 items-center justify-center bg-black text-[10px] text-slate-600">
                        {language !== 'en' ? '无预览图' : 'no preview'}
                      </div>
                    )}
                    <div className="px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-slate-100">#{formatUnknown('rank' in item ? item.rank : idx + 1)} {formatUnknown(item.patient_id ?? `case-${idx + 1}`)}</span>
                        <span className="shrink-0 rounded-full bg-cyan-300/10 px-2 py-0.5 font-mono text-cyan-100">{sim}%</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
                        <span className="truncate">{formatUnknown(item.data_source)}</span>
                        <span className="font-mono text-emerald-200">{stage}</span>
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
              {language !== 'en' ? 'API / 模型调用核验' : 'API / model invocation audit'}
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className={`rounded-full px-2 py-0.5 ${verification?.all_core_models_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-amber-300/15 text-amber-100'}`}>
                {language !== 'en' ? '核心模型' : 'core models'}: {verification?.all_core_models_called ? 'OK' : 'CHECK'}
              </span>
              <span className={`rounded-full px-2 py-0.5 ${verification?.llm_api_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-slate-700/50 text-slate-300'}`}>
                LLM API: {verification?.llm_api_called ? (language !== 'en' ? '已调用' : 'called') : (language !== 'en' ? '未调用/跳过' : 'skipped')}
              </span>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-[11px]">
                <thead>
                  <tr className="text-slate-500">
                    <th className="pb-2 pr-3">{language !== 'en' ? '组件' : 'component'}</th>
                    <th className="pb-2 pr-3">{language !== 'en' ? '类型' : 'kind'}</th>
                    <th className="pb-2 pr-3">{language !== 'en' ? '已调用' : 'called'}</th>
                    <th className="pb-2">{language !== 'en' ? '状态' : 'status'}</th>
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
              <div className="text-xs uppercase tracking-[0.18em] text-emerald-100/70">{language !== 'en' ? '综合推荐' : 'Integrated recommendation'}</div>
              <div className="mt-3 text-6xl font-black text-emerald-100">{formatUnknown(outputs.recommended_t_stage ?? result?.report.recommended_t_stage)}</div>
              <div className="mt-2 text-sm text-emerald-100/80">{formatUnknown(outputs.confidence ?? result?.report.confidence)}</div>
            </div>
            <VisualFrame title={language !== 'en' ? '胃壁穿透风险图' : 'Wall penetration risk'} subtitle={language !== 'en' ? '综合推理使用的胃壁局部风险代理证据' : 'wall proxy evidence used during synthesis'} src={typeof refs.wall_penetration_heatmap_url === 'string' ? refs.wall_penetration_heatmap_url : undefined} />
            <VisualFrame
              title={language !== 'en' ? '真实胃壁分析图' : 'Real wall analysis figure'}
              subtitle={
                language !== 'en'
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
            <VisualFrame title={language !== 'en' ? '真实 DINO 多模态图' : 'Real DINO multimodal figure'} subtitle={language !== 'en' ? '来自 DINO 可视化脚本（按需生成）' : 'from DINO visualization script (on-demand)'} src={visualRefPick(refs, ['real_dino_multimodal_panel_url', 'current_image_dino_feature_panel_url', 'dino_similarity_heatmap_url'])} />
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-sm font-black text-white">{language !== 'en' ? '证据权重与冲突提示' : 'Evidence weights and conflict flags'}</div>
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
            <div className="text-sm font-black text-emerald-100">{language !== 'en' ? '动态报告草稿章节' : 'Dynamic report draft sections'}</div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              {result?.report.dynamic_report_draft?.sections.slice(0, 4).map((section) => (
                <div key={`draft-step-${section.heading}`} className="rounded-xl border border-white/10 bg-black/25 p-3 text-xs">
                  <div className="font-bold text-emerald-100">{section.heading}</div>
                  <div className="mt-2 line-clamp-3 leading-relaxed text-slate-400">{section.lines.join(' ')}</div>
                    {section.evidence_refs?.length ? (
                      <div className="mt-2 font-mono text-[9px] text-cyan-200/60">
                        refs: {section.evidence_refs.join(', ')}
                      </div>
                    ) : null}
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
        title={language !== 'en' ? '当前步骤输出图' : 'Current step output'}
        subtitle={currentBackendStep.step_id}
        src={getStepVisualRef(currentBackendStep, ['lumen_detection_overlay_url', 'classification_probabilities_url', 'predicted_overlay_url', 'predicted_roi_url', 'predicted_mask_url']) || patient.image_url}
      />
    );
  };

  if (!patient) {
    return null;
  }

  return (
    <ImageZoomContext.Provider value={openImageLightbox}>
      <>
      <div className="pointer-events-none absolute inset-0 z-[100]">
      {workbenchOpen && (loading || result || liveSteps.length > 0 || error) && (
      <div className="pointer-events-auto fixed inset-0 z-[120] overflow-y-auto border border-cyan-500/25 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.18),transparent_36%),linear-gradient(135deg,rgba(0,0,0,0.98),rgba(8,13,24,0.98))] p-5 shadow-2xl shadow-black/70 backdrop-blur-xl md:p-6 custom-scrollbar">
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(59,130,246,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.12)_1px,transparent_1px)] [background-size:18px_18px]" />
        <div className="relative space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.22em] text-cyan-100">
                <Brain size={12} />
                {language !== 'en' ? '辅助诊断工作台' : 'Assisted diagnosis'}
              </div>
              <div className="mt-3 text-lg font-black leading-tight text-white">
                {language !== 'en' ? '生成可编辑的辅助诊断意见' : 'Generate editable assisted diagnosis'}
              </div>
              <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
                {language !== 'en'
                  ? '汇总胃腔、病灶、胃壁、分期与临床线索，生成医生可快速复核与编辑的意见。'
                  : 'Combine lumen, lesion, wall, staging, and clinical cues into a physician-editable opinion.'}
              </div>
              <div className={`mt-3 rounded-lg border px-3 py-2 text-[10px] leading-relaxed ${
                geometryInputs.ready
                  ? 'border-emerald-300/30 bg-emerald-300/10 text-emerald-100'
                  : 'border-amber-300/30 bg-amber-300/10 text-amber-100'
              }`}>
                <div className="font-semibold">
                  {language !== 'en' ? 'Agent 几何输入门禁' : 'Agent geometry gate'}
                </div>
                <div className="mt-1">
                  {language !== 'en'
                    ? `病灶 ${geometryInputs.lesionReady ? '已确认' : '缺失'}，胃腔 ${geometryInputs.lumenReady ? '已确认' : '缺失'}`
                    : `Lesion ${geometryInputs.lesionReady ? 'confirmed' : 'missing'}, lumen ${geometryInputs.lumenReady ? 'confirmed' : 'missing'}`}
                  {geometryInputs.geometry.available
                    ? `; ${geometryInputs.geometry.relation === 'overlap' ? (language !== 'en' ? '存在重叠' : 'overlap') : geometryInputs.geometry.relation}`
                    : ''}
                </div>
                {liveGeometryPending ? (
                  <div className="mt-1 text-amber-200">
                    {language !== 'en'
                      ? '当前轮廓尚未保存为确认 override，保存病灶和胃腔后 Agent 才会启动。'
                      : 'The live contours are not saved as confirmed overrides. Save lesion and lumen geometry before starting the Agent.'}
                  </div>
                ) : null}
                {geometryInputs.geometry.relation === 'overlap' ? (
                  <div className="mt-1 text-amber-200">
                    {language !== 'en'
                      ? '重叠只表示投影关系，Agent 将同时接收两条轮廓，不把重叠当作侵犯证据。'
                      : 'Overlap is only a projection relation. The Agent receives both contours and will not treat overlap as invasion evidence.'}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="flex shrink-0 items-start gap-3">
              {result && (
                <div className={`rounded-xl border px-3 py-2 text-right ${confidenceTone(result.report.confidence)}`}>
                  <div className="text-[10px] uppercase tracking-wider opacity-70">{language !== 'en' ? '推荐' : 'Stage'}</div>
                  <div className="text-2xl font-black">{result.report.recommended_t_stage}</div>
                  <div className="text-[10px] opacity-80">{result.report.confidence}</div>
                </div>
              )}
              <button
                type="button"
                onClick={() => setWorkbenchOpen(false)}
                className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
                aria-label={language !== 'en' ? '关闭 Agent 工作台' : 'Close Agent workbench'}
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-300 md:grid-cols-4">
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language !== 'en' ? '病例' : 'Case'}</div>
              <div className="mt-1 truncate font-mono text-slate-100">{patient.patient_id}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language !== 'en' ? '输入模态' : 'Inputs'}</div>
              <div className="mt-1 font-mono text-slate-100">{patient.roi_url ? 'Image + ROI' : 'Image only'}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language !== 'en' ? '帧聚合' : 'Frames'}</div>
              <div className="mt-1 font-mono text-slate-100">
                {result?.frame_evidence
                  ? `${result.frame_evidence.aggregated_frame_count ?? result.frame_evidence.frame_count} (${result.frame_evidence.aggregation ?? 'single'})`
                  : `${patient.frame_count ?? 1}`}
              </div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-2">
              <div className="text-slate-500">{language !== 'en' ? '工具链' : 'Tools'}</div>
              <div className="mt-1 font-mono text-slate-100">{result ? `${result.traces?.length ?? 0} traces` : '8+ tools'}</div>
            </div>
          </div>

          {result?.evidence?.length ? (
            <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-black text-cyan-100">
                  {language !== 'en' ? '统一证据总览' : 'Unified evidence'}
                </div>
                <div className="font-mono text-[10px] text-cyan-200/80">
                  {result.evidence.length} items · {result.provenance?.schema_version || 'provenance'}
                </div>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {result.evidence.slice(0, 8).map((item) => (
                  <div key={item.evidence_id} className="rounded-lg border border-white/10 bg-black/25 px-2.5 py-2">
                    <div className="truncate text-[10px] font-semibold text-slate-200">{item.feature}</div>
                    <div className="mt-1 text-[10px] text-slate-500">
                      {String(item.domain)} · {String(item.source_type)}
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-emerald-200">{String(item.status)}</div>
                  </div>
                ))}
              </div>
              {result.provenance ? (
                <div className="mt-2 text-[10px] text-slate-500">
                  run={result.provenance.run_id} · manifest={result.provenance.manifest_version} · steps={result.provenance.step_count}
                </div>
              ) : null}
            </div>
          ) : null}

          {result?.belief_state ? (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.04] p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-black text-cyan-100">
                    <Brain size={13} />
                    {language !== 'en' ? '病例信念状态' : 'Case belief state'}
                  </div>
                  <span className="font-mono text-[9px] text-cyan-200/60">{result.belief_state.schema_version}</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                  {result.belief_state.hypotheses
                    .filter((item) => item.probability != null)
                    .sort((a, b) => Number(b.probability || 0) - Number(a.probability || 0))
                    .slice(0, 6)
                    .map((item) => (
                      <div key={item.hypothesis_id} className="rounded-lg border border-white/10 bg-black/25 px-2 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-slate-300">{item.label}</span>
                          <span className="font-mono text-emerald-200">
                            {item.probability == null ? '—' : `${Math.round(item.probability * 100)}%`}
                          </span>
                        </div>
                        <div className="mt-1 h-1 overflow-hidden rounded bg-white/10">
                          <div
                            className="h-full rounded bg-emerald-300/70"
                            style={{ width: `${Math.max(0, Math.min(100, Number(item.probability || 0) * 100))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                </div>
                {result.belief_state.missing_evidence.length ? (
                  <div className="mt-2 rounded-lg border border-amber-300/20 bg-amber-300/5 px-2 py-1.5 text-[10px] leading-relaxed text-amber-100/80">
                    {language !== 'en' ? '缺失证据：' : 'Missing evidence: '}
                    {result.belief_state.missing_evidence.join(', ')}
                  </div>
                ) : null}
              </div>
              <div className="rounded-xl border border-amber-300/20 bg-amber-300/[0.04] p-3">
                <div className="text-xs font-black text-amber-100">
                  {language !== 'en' ? '下一步主动取证' : 'Next active evidence action'}
                </div>
                {result.belief_state.next_actions.slice(0, 3).map((action) => (
                  <div key={action.action_id} className={`mt-2 rounded-lg border px-2.5 py-2 ${action.status === 'selected' ? 'border-cyan-300/35 bg-cyan-300/10' : 'border-white/10 bg-black/20'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold text-slate-200">{action.action_type}</span>
                      <span className="font-mono text-[9px] text-cyan-200">{Math.round(action.expected_information_gain * 100)}%</span>
                    </div>
                    <div className="mt-1 text-[9px] leading-relaxed text-slate-500">{action.reason}</div>
                  </div>
                ))}
                {result.report.clinical_decision?.recommendation ? (
                  <div className="mt-2 text-[10px] leading-relaxed text-amber-50/80">
                    {result.report.clinical_decision.recommendation}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-950/40 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}

          {!loading && !result && liveSteps.length === 0 && (
            <div className="rounded-2xl border border-dashed border-cyan-400/25 bg-cyan-400/5 px-4 py-3 text-xs leading-relaxed text-cyan-100/75">
              {language !== 'en'
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
                    {language !== 'en' ? '当前病例 Agent 分析窗口' : 'Current Case Agent Window'}
                  </div>
                  <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
                    {language !== 'en'
                      ? '按后端真实事件逐步追加：工具没跑完就等待，跑完一个显示一个，不再用进度条模拟。'
                      : 'Steps are appended from real backend events: each tool appears only after it finishes.'}
                  </div>
                </div>
                <div className={`rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.18em] ${
                  loading ? 'border-amber-300/30 bg-amber-300/10 text-amber-100' : 'border-cyan-300/30 bg-cyan-300/10 text-cyan-100'
                }`}>
                  {loading ? (language !== 'en' ? '等待工具输出' : 'waiting for tools') : (language !== 'en' ? '分析完成' : 'completed')}
                </div>
              </div>

              <div className="space-y-3">
                <div className="rounded-2xl border border-white/10 bg-black/25 p-3">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
                        {language !== 'en' ? '实时调用队列' : 'Live Tool Queue'}
                      </div>
                      {liveSteps.length > 0 && (
                        <div className="mt-1 text-[10px] text-slate-500">
                          {language !== 'en'
                            ? `已返回 ${liveSteps.length} 条真实步骤 · 当前查看第 ${activeStep + 1} 条`
                            : `${liveSteps.length} real steps returned · viewing step ${activeStep + 1}`}
                        </div>
                      )}
                    </div>
                  </div>

                  {adaptiveSteps.length ? (
                    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                      {adaptiveSteps.map((step, idx) => {
                        const Icon = step.icon;
                        const isSelected = idx === activeStep;
                        const isDone = idx < liveSteps.length || Boolean(result);
                        const isRunning = loading && idx === liveSteps.length;
                        const isPending = !isDone && !isRunning;
                        const showConnector = (idx + 1) % 4 !== 0 && idx < adaptiveSteps.length - 1;
                        const statusLabel = isRunning
                          ? (language !== 'en' ? '运行中' : 'running')
                          : isDone
                            ? (step.backendStep?.status || (language !== 'en' ? '完成' : 'done'))
                            : (language !== 'en' ? '等待' : 'pending');
                        return (
                          <button
                            key={`inline-step-${step.key}-${idx}`}
                            type="button"
                            onClick={() => setActiveStep(idx)}
                            className={`group relative rounded-xl border px-2.5 py-2 text-left transition ${
                              isSelected
                                ? 'border-emerald-200/70 bg-emerald-200/15 text-emerald-50 shadow-[0_0_20px_rgba(16,185,129,0.2)] ring-1 ring-emerald-200/40'
                                : isRunning
                                  ? 'border-amber-300/40 bg-amber-300/10 text-amber-50'
                                  : isDone
                                    ? 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100/90 hover:border-emerald-300/35'
                                    : 'border-white/10 bg-white/[0.03] text-slate-500 hover:border-white/20 hover:text-slate-300'
                            }`}
                          >
                            {showConnector && (
                              <span className="pointer-events-none absolute -right-[9px] top-1/2 z-10 hidden -translate-y-1/2 text-slate-600 md:block" aria-hidden="true">
                                <ChevronRight size={12} />
                              </span>
                            )}
                            <div className="flex items-center justify-between gap-1.5">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-black ${
                                  isSelected ? 'bg-emerald-200 text-slate-950' : isDone ? 'bg-cyan-400/20 text-cyan-100' : 'bg-white/10 text-slate-400'
                                }`}>
                                  {idx + 1}
                                </span>
                                <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
                                  isSelected ? 'bg-emerald-200 text-slate-950' : isPending ? 'bg-white/5 text-slate-500' : 'bg-white/10 text-emerald-200'
                                }`}>
                                  {isRunning ? <Loader2 size={12} className="animate-spin" /> : isDone ? <CheckCircle2 size={12} /> : <Icon size={12} />}
                                </div>
                              </div>
                              <span className={`shrink-0 rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wide ${
                                isRunning ? 'bg-amber-300/20 text-amber-100' : isDone ? 'bg-emerald-300/15 text-emerald-100' : 'bg-white/5 text-slate-500'
                              }`}>
                                {statusLabel}
                              </span>
                            </div>
                            <div className="mt-1.5 line-clamp-2 text-[10px] font-bold leading-snug">{step.title}</div>
                            <div className="mt-1 truncate text-[9px] opacity-70">{step.output}</div>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.03] p-3 text-xs leading-relaxed text-slate-500">
                      {loading
                        ? '等待后端返回第一条真实工具事件，不预填步骤，不模拟进度。'
                        : (language !== 'en' ? '点击启动后，Agent 会先盘点病例资料，然后第一条真实步骤会出现在这里。' : 'Start the agent to see the first real backend step here.')}
                    </div>
                  )}

                  {loading && liveSteps.length > 0 ? (
                    <div className="mt-2 border-t border-white/5 pt-2 text-[10px] text-amber-200/80">
                      已返回 {liveSteps.length} 条真实步骤，等待后端下一条工具事件。
                    </div>
                  ) : null}

                  {liveSteps.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-white/5 pt-2 text-[9px] text-slate-500">
                      <span>{language !== 'en' ? '每条卡片均来自后端已完成事件' : 'Each card is a completed backend event'}</span>
                      <span>{language !== 'en' ? '点击卡片查看该步详情' : 'Click a card for step details'}</span>
                    </div>
                  )}
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
                          {language !== 'en' ? '等待 Agent 返回第一步工具调用结果。模型加载或预测较慢时，这里会保持等待状态。' : 'Waiting for the first real tool-call result from the agent.'}
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
                        {language !== 'en' ? 'API 调用核验摘要' : 'API invocation summary'}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                        <span className={`rounded-full px-2 py-0.5 ${(runtimeVerification ?? result?.runtime_verification)?.all_core_models_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-amber-300/15 text-amber-100'}`}>
                          {language !== 'en' ? '核心模型' : 'core models'}: {(runtimeVerification ?? result?.runtime_verification)?.all_core_models_called ? 'OK' : 'CHECK'}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 ${(runtimeVerification ?? result?.runtime_verification)?.llm_api_called ? 'bg-emerald-300/15 text-emerald-100' : 'bg-slate-700/50 text-slate-300'}`}>
                          LLM: {(runtimeVerification ?? result?.runtime_verification)?.llm_api_called ? (language !== 'en' ? '已调用' : 'called') : (language !== 'en' ? '未调用' : 'skipped')}
                        </span>
                      </div>
                      <div className="mt-2 text-[10px] text-slate-500">
                        {language !== 'en'
                          ? '完整表格见步骤「运行时 API / 模型调用核验」。'
                          : 'See the runtime API verification step for the full table.'}
                      </div>
                    </div>
                  )}

                  {result?.tool_evidence && (
                    <div className="mt-3 rounded-xl border border-sky-300/20 bg-sky-300/5 p-3">
                      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-sky-200/80">
                        {language !== 'en' ? '冻结后端口径（2026-08-09）' : 'Frozen backend contract (2026-08-09)'}
                      </div>
                      <div className="mt-2 grid gap-2 text-[11px] text-slate-200 sm:grid-cols-2">
                        <div className="rounded-lg bg-black/25 px-2 py-1.5">
                          <div className="text-[10px] uppercase tracking-wide text-slate-500">T staging</div>
                          <div className="mt-0.5 font-mono text-[10px] text-sky-100">
                            {formatUnknown(
                              result.tool_evidence.classification?.backend_id
                              ?? result.tool_evidence.classification?.checkpoint
                              ?? 'tstage_acc_boost2_screened_20260603',
                            )}
                          </div>
                        </div>
                        <div className="rounded-lg bg-black/25 px-2 py-1.5">
                          <div className="text-[10px] uppercase tracking-wide text-slate-500">Segmentation</div>
                          <div className="mt-0.5 font-mono text-[10px] text-sky-100">
                            {formatUnknown(
                              result.tool_evidence.segmentation?.backend_id
                              ?? result.tool_evidence.segmentation?.checkpoint
                              ?? 'lesion_segmentation_unet_fulldata_convnext_base',
                            )}
                          </div>
                        </div>
                        <div className="rounded-lg bg-black/25 px-2 py-1.5">
                          <div className="text-[10px] uppercase tracking-wide text-slate-500">
                            {language !== 'en' ? '支持 / 冲突 / 不确定' : 'support / conflict / uncertainty'}
                          </div>
                          <div className="mt-0.5 text-sky-100">
                            {(result.report.supporting_evidence?.length ?? 0)}
                            {' / '}
                            {(result.report.conflicting_evidence?.length ?? 0)}
                            {' / '}
                            {(result.report.uncertainty_flags?.length ?? 0)}
                          </div>
                        </div>
                        <div className="rounded-lg bg-black/25 px-2 py-1.5">
                          <div className="text-[10px] uppercase tracking-wide text-slate-500">SAM3.1</div>
                          <div className="mt-0.5 text-[10px] text-slate-300">
                            {language !== 'en'
                              ? '交互候选已上线；Agent 批量主分割仍为 UNet'
                              : 'Interactive candidate online; Agent batch primary remains UNet'}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {result?.evidence_pack && (
                    <div className="mt-3 rounded-xl border border-violet-300/20 bg-violet-300/5 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-violet-200/80">
                            {language !== 'en' ? '统一病例证据包' : 'Unified case evidence pack'}
                          </div>
                          <div className="mt-1 text-[10px] text-slate-400">
                            {language !== 'en'
                              ? `已汇总 ${result.evidence_pack.assessments?.length || 0} 项评估, ${result.evidence_pack.artifacts?.length || 0} 个持久化产物`
                              : `${result.evidence_pack.assessments?.length || 0} assessments, ${result.evidence_pack.artifacts?.length || 0} persisted artifacts`}
                          </div>
                        </div>
                        {result.evidence_pack_refs?.evidence_pack_url && (
                          <a
                            href={result.evidence_pack_refs.evidence_pack_url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-lg border border-violet-300/30 bg-violet-300/10 px-3 py-1.5 text-[11px] font-bold text-violet-100 transition hover:bg-violet-300/20"
                          >
                            {language !== 'en' ? '打开证据包 JSON' : 'Open evidence pack JSON'}
                          </a>
                        )}
                      </div>
                    </div>
                  )}

                  {result && (
                    <div className="mt-3 space-y-3">
                      <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/10 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-black text-emerald-50">{language !== 'en' ? '综合推荐结果' : 'Integrated recommendation'}</div>
                            <div className="mt-1 text-xs leading-relaxed text-emerald-100/75">{result.report.reasoning}</div>
                          </div>
                          <div className="flex items-center gap-2">
                            {result.report.dynamic_report_draft && (
                              <button
                                type="button"
                                onClick={() => void copyDraft()}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/30 bg-emerald-300/10 px-3 py-1.5 text-[11px] font-bold text-emerald-100 transition hover:bg-emerald-300/20"
                              >
                                <Clipboard size={12} />
                                {copiedDraft
                                  ? (language !== 'en' ? '已复制' : 'Copied')
                                  : (language !== 'en' ? '复制报告草稿' : 'Copy draft')}
                              </button>
                            )}
                            <div className={`rounded-xl border px-4 py-2 text-right ${confidenceTone(result.report.confidence)}`}>
                              <div className="text-3xl font-black">{result.report.recommended_t_stage}</div>
                              <div className="text-[10px] uppercase">{result.report.confidence}</div>
                            </div>
                          </div>
                        </div>
                        {copyError && <div className="mt-2 text-[10px] text-red-300">{copyError}</div>}
                      </div>

                      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-black text-white">{language !== 'en' ? '多模态证据面板' : 'Multimodal evidence panel'}</div>
                          {result.report.rag_gate && (
                            <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-[10px] text-amber-100">
                              RAG {Math.round((result.report.rag_gate.rag_weight ?? 0) * 100)}% · {result.report.rag_gate.rag_gate_reason}
                            </span>
                          )}
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
                          {toolCards.map((card) => {
                            const Icon = card.icon;
                            const status = toolAvailability(card.tool);
                            const trust = card.tool?.trust_label;
                            return (
                              <div key={card.key} className="rounded-lg border border-white/10 bg-black/25 p-2.5">
                                <div className="flex items-center justify-between gap-1">
                                  <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-200">
                                    <Icon size={11} />
                                    {card.title}
                                  </div>
                                  <span className={`rounded px-1 py-0.5 text-[8px] uppercase ${statusClass(status)}`}>{status}</span>
                                </div>
                                {trust && (
                                  <span className={`mt-1 inline-block rounded border px-1 py-0.5 text-[8px] ${getTrustClass(trust)}`}>{String(trust)}</span>
                                )}
                                <div className="mt-1.5 space-y-0.5">
                                  {card.metrics.slice(0, 2).map((m) => (
                                    <div key={m.key} className="flex justify-between gap-1 text-[9px]">
                                      <span className="text-slate-500">{m.key}</span>
                                      <span className="truncate font-mono text-slate-300">{formatUnknown(m.value)}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                          <div>
                            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400">{language !== 'en' ? '支持证据' : 'Supporting'}</div>
                            <div className="space-y-1">
                              {(result.report.supporting_evidence ?? []).slice(0, 3).map((item, idx) => (
                                <div key={`wb-support-${idx}`} className="rounded bg-emerald-300/10 px-2 py-1 text-[10px] text-emerald-100">{item}</div>
                              ))}
                            </div>
                          </div>
                          <div>
                            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-red-400">{language !== 'en' ? '冲突证据' : 'Conflicting'}</div>
                            <div className="space-y-1">
                              {(result.report.conflicting_evidence ?? []).slice(0, 3).map((item, idx) => (
                                <div key={`wb-conflict-${idx}`} className="rounded bg-red-300/10 px-2 py-1 text-[10px] text-red-100">{item}</div>
                              ))}
                              {!result.report.conflicting_evidence?.length && (
                                <div className="text-[10px] text-slate-600">{language !== 'en' ? '无显著冲突' : 'No major conflicts'}</div>
                              )}
                            </div>
                          </div>
                          <div>
                            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-400">{language !== 'en' ? '不确定性' : 'Uncertainty'}</div>
                            <div className="space-y-1">
                              {(result.report.uncertainty_flags ?? []).slice(0, 3).map((item, idx) => (
                                <div key={`wb-uncertain-${idx}`} className="rounded bg-amber-300/10 px-2 py-1 text-[10px] text-amber-100">{item}</div>
                              ))}
                            </div>
                          </div>
                        </div>
                        {(result.report.memory_update_candidates?.length ?? 0) > 0 && (
                          <div className="mt-3 rounded-lg border border-violet-300/20 bg-violet-300/5 p-3">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-violet-300">
                              {language !== 'en' ? 'Memory 候选' : 'Memory candidates'} ({result.report.memory_update_candidates?.length})
                            </div>
                            <div className="mt-2 space-y-2">
                              {result.report.memory_update_candidates?.slice(0, 4).map((candidate, idx) => {
                                const recordId = String(candidate.record_id ?? '');
                                const label = formatUnknown(
                                  candidate.title ?? candidate.record_type ?? candidate.kind ?? candidate.type ?? candidate,
                                );
                                return (
                                  <div key={`memory-${recordId || idx}`} className="rounded bg-black/25 px-2 py-2">
                                    <div className="font-mono text-[9px] text-violet-100 line-clamp-2">{label}</div>
                                    {recordId && (
                                      <div className="mt-2 flex flex-wrap gap-1">
                                        {(['accept', 'reject', 'defer'] as const).map((action) => (
                                          <button
                                            key={`${recordId}-${action}`}
                                            type="button"
                                            disabled={memoryActionPending === recordId}
                                            onClick={() => submitMemoryCandidateAction(recordId, action)}
                                            className="rounded border border-violet-300/30 px-2 py-0.5 text-[9px] uppercase tracking-wide text-violet-100 transition hover:bg-violet-300/15 disabled:opacity-50"
                                          >
                                            {action}
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                              {memoryActionMessage && (
                                <div className="text-[9px] text-violet-200/80">{memoryActionMessage}</div>
                              )}
                            </div>
                          </div>
                        )}
                        {(result.report.guideline_evidence?.length || result.report.management_advice?.length) ? (
                          <div className="mt-3 rounded-lg border border-amber-300/25 bg-amber-300/5 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="text-[10px] font-bold uppercase tracking-wider text-amber-300">
                                {language !== 'en' ? '临床指南 RAG' : 'Clinical guideline RAG'}
                              </div>
                              <span className="rounded border border-amber-300/25 px-1.5 py-0.5 text-[8px] text-amber-100">AJCC TNM + NCCN 3.2026</span>
                            </div>
                            <div className="mt-2 space-y-1.5">
                              {(result.report.guideline_evidence ?? []).slice(0, 4).map((item) => (
                                <div key={`guideline-${item.id}`} className="rounded bg-black/25 px-2 py-1.5 text-[10px] text-amber-50">
                                  <div className="font-bold">{item.title}</div>
                                  <div className="mt-0.5 leading-relaxed text-amber-100/75">{item.statement}</div>
                                  {item.citations?.length ? <div className="mt-0.5 text-[8px] text-slate-500">{item.citations.join(' · ')}</div> : null}
                                </div>
                              ))}
                            </div>
                            {(result.report.management_advice ?? []).length > 0 && (
                              <div className="mt-2 rounded border border-emerald-300/20 bg-emerald-300/5 p-2">
                                <div className="mb-1 text-[9px] font-bold uppercase tracking-wider text-emerald-300">
                                  {language !== 'en' ? '对应处理意见（需 MDT 复核）' : 'Care pathway context (MDT review required)'}
                                </div>
                                <div className="space-y-1">
                                  {(result.report.management_advice ?? []).slice(0, 4).map((item, idx) => (
                                    <div key={`management-${idx}`} className="text-[10px] leading-relaxed text-emerald-100">{item.action}</div>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div className="mt-2 text-[8px] leading-relaxed text-slate-500">
                              {language !== 'en'
                                ? 'AJCC 用于 TNM 定义；管理路径参考 NCCN。当前 Agent 不输出药物剂量或替代医生决定。'
                                : 'AJCC defines TNM; management context follows NCCN. The Agent does not issue drug doses or replace clinician decisions.'}
                            </div>
                          </div>
                        ) : null}

                        {result.knowledge_context?.length > 0 && (
                          <div className="mt-3 rounded-lg border border-cyan-300/20 bg-cyan-300/5 p-3">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-cyan-300">{language !== 'en' ? '知识检索' : 'Knowledge context'}</div>
                            <div className="mt-2 space-y-1">
                              {result.knowledge_context.slice(0, 2).map((item, idx) => (
                                <div key={`kb-${idx}`} className="text-[10px] text-cyan-100">
                                  <span className="font-bold">{item.title}</span>
                                  <span className="text-slate-500"> · {item.source}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
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

      {/* Hidden from main canvas: analysis opens from full-report entry only */}
      {false && (
      <div className="pointer-events-auto absolute bottom-[5.75rem] left-1/2 z-30 w-[min(380px,calc(100%-2rem))] -translate-x-1/2">
        <button
          type="button"
          onClick={handleLauncherClick}
          disabled={loading}
          className="group relative w-full overflow-hidden rounded-[1.4rem] border border-cyan-200/60 bg-[linear-gradient(135deg,#38bdf8,#22d3ee_45%,#94a3b8)] p-1 text-left text-slate-950 shadow-[0_24px_70px_rgba(2,8,23,0.65)] transition hover:-translate-y-1 hover:shadow-[0_28px_90px_rgba(14,165,233,0.38)] disabled:translate-y-0 disabled:cursor-wait disabled:opacity-85"
          aria-label={language !== 'en' ? '启动当前病例辅助分析' : 'Start assisted analysis for this case'}
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
                  ? (language !== 'en' ? 'Agent 正在等待工具输出' : 'Agent is waiting for tools')
                  : (result || liveSteps.length > 0 || error) && !workbenchOpen
                    ? (language !== 'en' ? '打开 Agent 工作台' : 'Open agent workbench')
                    : result
                      ? (language !== 'en' ? '重新运行当前病例 Agent' : 'Rerun agent for this case')
                    : (language !== 'en' ? '启动当前病例 Agent' : 'Start case agent')}
              </span>
              <span className="mt-0.5 block truncate text-[11px] font-semibold text-slate-800/80">
                {loading
                  ? `${liveSteps.length} ${language !== 'en' ? '步已返回' : 'steps returned'}`
                  : maskOverride
                    ? (language !== 'en' ? '将使用已编辑边界覆盖分割' : 'Using edited boundary override')
                    : (language !== 'en' ? '分割、腔检测、壁层、分类、相似病例逐步显示' : 'Lumen, wall, staging, memory stream in')}
              </span>
            </span>
            <ArrowRight size={20} className="shrink-0 transition group-hover:translate-x-1" />
          </span>
        </button>
      </div>
      )}

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
                    {language !== 'en' ? '当前病例智能分析' : 'Current Case Intelligence'}
                  </h2>
                  <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-400">
                    {language !== 'en'
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
                      <div className="text-sm font-bold">{language !== 'en' ? 'Agent 正在根据当前病例动态选择工具' : 'Agent is dynamically selecting tools for this case'}</div>
                      <div className="mt-1 text-xs text-emerald-100/70">
                        {language !== 'en' ? '不是只走固定模板，而是先盘点病例资料，再决定定位、分割、分类、临床/报告校验和相似病例投票的权重。' : 'This is not a rigid template: the agent inspects case evidence and weights localization, segmentation, classification, clinical/report checks, and similar-case voting.'}
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
                            {language !== 'en' ? '当前工具调用可视化' : 'Current tool-call visualization'}
                          </div>
                          <div className="mt-0.5 text-[10px] text-emerald-100/60">{adaptiveSteps[activeStep]?.title}</div>
                        </div>
                        <span className="rounded-full border border-emerald-300/30 bg-emerald-300/10 px-2 py-1 text-[10px] text-emerald-100">
                          calling
                        </span>
                      </div>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        <VisualFrame
                          title={language !== 'en' ? '原始超声输入' : 'Original ultrasound'}
                          subtitle={patient.id_short}
                          src={patient.image_url}
                        />
                        <VisualFrame
                          title={activeStep <= 1 ? (language !== 'en' ? '等待定位输出' : 'Waiting for localization') : (language !== 'en' ? 'ROI / 分割叠加预览' : 'ROI / overlay preview')}
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
                          {language !== 'en' ? '逐步检查 Agent 每一次工具调用' : 'Inspect each agent tool call step by step'}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {language !== 'en' ? '点击任意步骤，查看该步骤的输入、模型输出、图像证据和推理解释。' : 'Click any step to inspect its inputs, model outputs, visual evidence, and reasoning.'}
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
                        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{language !== 'en' ? '当前步骤' : 'Current step'}</div>
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
                                title={language !== 'en' ? '本次模型新生成的预测图' : 'New prediction artifact from this run'}
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
                                <div className="text-sm font-bold text-emerald-100">{language !== 'en' ? '真实 Agent 决策记录' : 'Real agent decision trace'}</div>
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
                            <VisualFrame title={language !== 'en' ? '原始超声输入' : 'Original ultrasound input'} subtitle={patient.id_short} src={patient.image_url} />
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-slate-100">{language !== 'en' ? '病例资料盘点' : 'Case evidence inventory'}</div>
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
                            <VisualFrame title={language !== 'en' ? 'ROI 裁剪输入' : 'ROI crop input'} subtitle={patient.roi_url ? 'frontend ROI asset' : 'fallback'} src={patient.roi_url || patient.image_url} />
                            <VisualFrame title={language !== 'en' ? '定位输出/叠加预览' : 'Localization output / overlay'} subtitle={formatUnknown(result.tool_evidence.segmentation?.roi_source)} src={patient.overlay_url || patient.roi_url || patient.image_url}>
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
                            <VisualFrame title={language !== 'en' ? '分割叠加证据' : 'Segmentation overlay evidence'} subtitle={patient.overlay_url ? 'overlay asset' : 'fallback preview'} src={patient.overlay_url || patient.roi_url || patient.image_url} />
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-lime-100">{language !== 'en' ? '形态学输出' : 'Morphology outputs'}</div>
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
                            <div className="text-sm font-bold text-emerald-100">{language !== 'en' ? '分类概率输出' : 'Classifier probability output'}</div>
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
                              <div className="text-sm font-bold text-amber-100">{language !== 'en' ? '临床风险工具输出' : 'Clinical risk output'}</div>
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
                              <div className="text-sm font-bold text-sky-100">{language !== 'en' ? '报告线索抽取' : 'Report cue extraction'}</div>
                              <div className="mt-3 space-y-2">
                                {getReportCues(result.tool_evidence.report).length ? getReportCues(result.tool_evidence.report).map((cue, idx) => (
                                  <div key={`step4-cue-${idx}`} className="rounded bg-black/25 px-2 py-1 text-[11px]">
                                    <div className="font-mono text-sky-100">{cue.cue}</div>
                                    <div className="mt-1 text-slate-500">{formatUnknown(cue.matched_terms)}</div>
                                  </div>
                                )) : (
                                  <div className="text-xs text-slate-500">{language !== 'en' ? '没有可结构化文本线索，因此文本证据降权。' : 'No structured text cues; report evidence is down-weighted.'}</div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {!currentBackendStep && activeStep === 5 && (
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                              <div className="text-sm font-bold text-cyan-100">{language !== 'en' ? '相似病例投票' : 'Similar-case voting'}</div>
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
                              <div className="text-sm font-bold text-emerald-100">{language !== 'en' ? '报告草稿章节' : 'Report draft sections'}</div>
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
                          {language !== 'en' ? '逐步工具调用与图像输出' : 'Step-by-step tool calls and visual outputs'}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {language !== 'en'
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
                          1. {language !== 'en' ? '病例接入：原始影像输入' : 'Case intake: raw imaging input'}
                        </div>
                        <VisualFrame
                          title={language !== 'en' ? '原始超声图像' : 'Original ultrasound'}
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
                          2. {language !== 'en' ? '定位模型：ROI / 候选病灶区' : 'Localization: ROI / candidate lesion region'}
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                          <VisualFrame
                            title={language !== 'en' ? 'ROI 裁剪' : 'ROI crop'}
                            subtitle={patient.roi_url ? 'frontend ROI asset' : 'fallback pending'}
                            src={patient.roi_url || patient.image_url}
                          />
                          <VisualFrame
                            title={language !== 'en' ? '定位/叠加预览' : 'Localization overlay'}
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
                          3. {language !== 'en' ? '分割/形态：病灶边界推理' : 'Segmentation/morphology: boundary reasoning'}
                        </div>
                        <VisualFrame
                          title={language !== 'en' ? '分割叠加图像证据' : 'Segmentation overlay evidence'}
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
                          4. {language !== 'en' ? '分类模型：T 分期概率输出' : 'Classifier: T-stage probability output'}
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
                              <div className="text-xs text-slate-500">{language !== 'en' ? '分类概率暂不可用' : 'Classifier probabilities unavailable'}</div>
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
                          5. {language !== 'en' ? '相似病例：检索与投票' : 'Similar cases: retrieval and voting'}
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
                          6. {language !== 'en' ? '综合推理：报告草稿与人工复核点' : 'Synthesis: draft and review points'}
                        </div>
                        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
                          <div className="text-4xl font-black text-emerald-200">{result.report.recommended_t_stage}</div>
                          <div className="mt-1 text-xs text-slate-500">{language !== 'en' ? '最终综合推荐，不等同于单模型 top-1' : 'Final integrated recommendation, not a single-model top-1'}</div>
                          <div className="mt-3 space-y-2">
                            {result.report.rag_gate && (
                              <div className="rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100/85">
                                {language !== 'en' ? 'RAG 门控' : 'RAG gate'}: weight={result.report.rag_gate.rag_weight} ({result.report.rag_gate.rag_gate_reason})
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
                                {language !== 'en' ? '暂无明显风险提示，但仍需医生结合原始图像复核。' : 'No major risk flags, but clinician review is still required.'}
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
                          {language !== 'en' ? 'Agent 自适应推理编排' : 'Adaptive agent orchestration'}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {language !== 'en'
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
                      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{language !== 'en' ? '综合结论' : 'Synthesis'}</div>
                      <div className="mt-3 flex flex-wrap items-end gap-4">
                        <div>
                          <div className="text-5xl font-black text-emerald-200">{result.report.recommended_t_stage}</div>
                          <div className="mt-1 text-xs text-slate-500">{language !== 'en' ? '推荐 T 分期' : 'Recommended T stage'}</div>
                        </div>
                        <div className={`rounded-xl border px-3 py-2 text-sm ${confidenceTone(result.report.confidence)}`}>
                          {language !== 'en' ? '置信度' : 'Confidence'}: {result.report.confidence}
                        </div>
                        <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-300">
                          {language !== 'en' ? '会话累计' : 'Session'}: {result.session_memory.analysis_count}
                        </div>
                      </div>
                      <p className="mt-4 text-sm leading-relaxed text-slate-300">{result.report.reasoning}</p>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{language !== 'en' ? '分类概率可视化' : 'Classifier probabilities'}</div>
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
                          <div className="text-xs text-slate-500">{language !== 'en' ? '分类概率暂不可用' : 'Classifier probabilities unavailable'}</div>
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
                            {language !== 'en' ? '相似病例与多证据投票' : 'Similar-case and evidence voting'}
                          </div>
                          <div className="mt-1 text-xs text-cyan-100/55">
                            {language !== 'en' ? '分类概率是一个投票源，相似病例、临床风险、分割质量和报告线索也是投票源。' : 'Classifier probabilities are one vote source; similar cases, clinical risk, segmentation quality, and report cues also vote.'}
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
                        {language !== 'en' ? '综合证据权重面板' : 'Integrated evidence weights'}
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
                        {language !== 'en'
                          ? '如果某一路证据缺失或冲突，Agent 会降低它的权重，并把不确定性写入人工复核提示。'
                          : 'When one evidence stream is missing or conflicting, the agent lowers its weight and records uncertainty for clinician review.'}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="mb-4 flex items-center gap-2 text-sm font-bold text-white">
                      <Workflow size={16} className="text-emerald-300" />
                      {language !== 'en' ? '按主线展开的模型调用结果' : 'Model calls along the clinical workflow'}
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
                                <div className="rounded bg-black/25 px-2 py-1 text-[11px] text-slate-500">{language !== 'en' ? '暂无结构化指标' : 'No structured metrics'}</div>
                              )}
                            </div>
                            {card.tool && 'error' in card.tool && card.tool.error && (
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
                        {language !== 'en' ? '支持证据' : 'Supporting evidence'}
                      </div>
                      <div className="space-y-2">
                        {result.report.supporting_evidence?.length ? result.report.supporting_evidence.map((item, idx) => (
                          <div key={idx} className="rounded-lg border border-emerald-400/15 bg-black/20 px-3 py-2 text-xs leading-relaxed text-emerald-50/80">{item}</div>
                        )) : (
                          <div className="text-xs text-slate-500">{language !== 'en' ? '暂无支持证据' : 'No supporting evidence'}</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-amber-400/20 bg-amber-400/5 p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-amber-100">
                        <AlertTriangle size={16} />
                        {language !== 'en' ? '不确定性与人工复核' : 'Uncertainty and review gates'}
                      </div>
                      <div className="space-y-2">
                        {result.report.uncertainty_flags?.length ? result.report.uncertainty_flags.map((item, idx) => (
                          <div key={idx} className="rounded-lg border border-amber-400/15 bg-black/20 px-3 py-2 text-xs leading-relaxed text-amber-50/80">{item}</div>
                        )) : (
                          <div className="text-xs text-slate-500">{language !== 'en' ? '暂无风险提示' : 'No risk flags'}</div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <Database size={16} className="text-cyan-300" />
                        {language !== 'en' ? '相似病例分布' : 'Similar cases'}
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
                          <div className="text-xs text-slate-500">{language !== 'en' ? '暂无相似病例' : 'No similar cases'}</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <FileSearch size={16} className="text-sky-300" />
                        {language !== 'en' ? '报告文本线索' : 'Report text cues'}
                      </div>
                      <div className="space-y-2">
                        {getReportCues(result.tool_evidence.report).length ? getReportCues(result.tool_evidence.report).map((cue, idx) => (
                          <div key={`${cue.cue}-${idx}`} className="rounded-lg bg-black/25 px-3 py-2">
                            <div className="font-mono text-xs text-sky-200">{cue.cue}</div>
                            <div className="mt-1 text-[10px] text-slate-500">{formatUnknown(cue.matched_terms)}</div>
                          </div>
                        )) : (
                          <div className="text-xs text-slate-500">{language !== 'en' ? '暂无文本线索' : 'No report cues'}</div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
                        <RefreshCw size={16} className="text-violet-300" />
                        {language !== 'en' ? 'Memory / 轨迹' : 'Memory / trace'}
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="rounded-lg bg-black/25 px-3 py-2">
                          <div className="text-slate-500">{language !== 'en' ? '候选记忆' : 'Memory candidates'}</div>
                          <div className="mt-1 font-mono text-slate-100">{result.report.memory_update_candidates?.length ?? 0}</div>
                        </div>
                        {(result.report.memory_update_candidates ?? []).slice(0, 3).map((candidate, idx) => {
                          const recordId = String(candidate.record_id ?? '');
                          return (
                            <div key={`mem-trace-${recordId || idx}`} className="rounded-lg bg-black/25 px-3 py-2">
                              <div className="text-[10px] text-violet-100 line-clamp-2">
                                {formatUnknown(candidate.title ?? candidate.record_type ?? candidate)}
                              </div>
                              {recordId && (
                                <div className="mt-2 flex gap-1">
                                  {(['accept', 'reject', 'defer'] as const).map((action) => (
                                    <button
                                      key={`trace-${recordId}-${action}`}
                                      type="button"
                                      disabled={memoryActionPending === recordId}
                                      onClick={() => submitMemoryCandidateAction(recordId, action)}
                                      className="rounded border border-violet-300/25 px-2 py-0.5 text-[9px] text-violet-100"
                                    >
                                      {action}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                        <div className="rounded-lg bg-black/25 px-3 py-2">
                          <div className="text-slate-500">{language !== 'en' ? '工具调用轨迹' : 'Tool traces'}</div>
                          <div className="mt-1 font-mono text-slate-100">{result.traces?.length ?? 0}</div>
                        </div>
                        {result.trajectory_ref?.path && (
                          <div className="rounded-lg bg-black/25 px-3 py-2">
                            <div className="text-slate-500">{language !== 'en' ? '轨迹文件' : 'Trace file'}</div>
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
                            {language !== 'en' ? '可复制动态报告草稿' : 'Copy-ready dynamic report draft'}
                          </div>
                          <div className="mt-1 text-xs text-emerald-100/60">{result.report.dynamic_report_draft.title}</div>
                        </div>
                        <button
                          onClick={copyDraft}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100 transition hover:bg-emerald-400/20"
                        >
                          {copiedDraft ? <CheckCircle2 size={13} /> : <Clipboard size={13} />}
                          {copiedDraft ? (language !== 'en' ? '已复制' : 'Copied') : (language !== 'en' ? '复制报告' : 'Copy report')}
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
                    <div className="mt-3 text-sm font-bold text-white">{language !== 'en' ? '准备对当前病例进行智能分析' : 'Ready to analyze this case'}</div>
                    <button
                      onClick={runAnalysis}
                      className="mt-4 inline-flex items-center gap-2 rounded-lg bg-emerald-300 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-emerald-200"
                    >
                      <Sparkles size={15} />
                      {language !== 'en' ? '开始分析' : 'Start analysis'}
                    </button>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
    {imageLightbox && (
      <ImageLightboxModal
        payload={imageLightbox}
        onClose={() => setImageLightbox(null)}
        language={language}
      />
    )}
      </>
    </ImageZoomContext.Provider>
  );
}
