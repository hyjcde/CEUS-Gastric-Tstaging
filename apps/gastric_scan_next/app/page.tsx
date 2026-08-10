"use client";

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Header } from '@/components/Header';
import { PatientList } from '@/components/PatientList';
import { UltrasoundViewer } from '@/components/UltrasoundViewer';
import { ConceptReasoning } from '@/components/ConceptReasoning';
import { DiagnosisPanel } from '@/components/DiagnosisPanel';
import { DoctorReportStudio } from '@/components/DoctorReportStudio';
import { StatisticsPanel } from '@/components/StatisticsPanel';
import { AgentWorkbenchPanel } from '@/components/AgentWorkbenchPanel';
import {
  buildModelAssistReport,
  InteractiveSegPanel,
  type DinoFeatureResult,
  type ImagingAssistPayload,
  type UnifiedAgentCapture,
  type WorkflowTraceStep,
} from '@/components/InteractiveSegPanel';
import { ReaderAgentResultCard } from '@/components/ReaderAgentResultCard';
import { ReaderStudyQueuePanel } from '@/components/ReaderStudyQueuePanel';
import { ReaderEvidencePanel } from '@/components/reader/ReaderEvidencePanel';
import { BenignTissueObservationCard } from '@/components/BenignTissueObservationCard';
import { AssistHub } from '@/components/AssistHub';
import { GcUsImagingReportCard } from '@/components/GcUsImagingReportCard';
import { GcUsEvidencePanel, mergeFreshEvidence } from '@/components/GcUsEvidencePanel';
// VideoAnalysisUpload 暂隐藏（质量选帧上传入口）
import { ConceptState, DEFAULT_STATE, Patient, AgentAnalysisResponse, LumenOverride, MaskBoundaryOverride, ReaderStudyMode } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import toast from 'react-hot-toast';
import type { SamReport } from '@/lib/reader/types';
import {
  createGcUsReportState,
  createGcUsField,
  deriveGcUsSigns,
  type GcUsReportImage,
  type GcUsReportState,
} from '@/lib/gc-us-report-template';
import { reportImageFromBase64 } from '@/lib/report-evidence-images';
import { lumenOverrideToAnalyzePayload } from '@/lib/lumen-override';
import {
  compactReaderSigns,
  readerEnvironmentFromSearchParams,
  readerEvidenceIds,
  READER_ROUND2_VERSION_FIELDS,
} from '@/lib/reader/study-contract';
import { ChevronLeft, ChevronRight, Users, BarChart2, FileText, X } from 'lucide-react';
import { getConceptStateFromPatient, countPopulatedConceptFields } from '@/lib/patient-utils';
import {
  mergeAgentIntoConceptState,
  mergeExplainableIntoConceptState,
  countAgentFilledFields,
  buildClinicalFieldSources,
  markAgentFilledSources,
  markManualFieldSource,
  createDefaultFieldSources,
  ExplainableAnalysisResult,
  ConceptFieldSources,
  CONCEPT_STATE_KEYS,
} from '@/lib/concept-agent-merge';

const EMPTY_READER_CLINICAL: Record<string, unknown> = {};
const EMPTY_POLYGON: number[][] = [];
const EVIDENCE_PANEL_WIDTH = 'clamp(20rem, 30vw, 32rem)';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function positiveClinicalNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
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
      const value = positiveClinicalNumber(record[key]);
      if (value != null) return value;
    }
    for (const key of cmKeys) {
      const value = positiveClinicalNumber(record[key]);
      if (value != null) return value * 10;
    }
  }
  const nested = asRecord(clinical.tumorSize);
  const value = positiveClinicalNumber(nested?.[nestedKey]);
  return value == null ? null : value * 10;
}

function mergeReportEvidenceImages(
  previous: GcUsReportImage[],
  incoming: GcUsReportImage[],
): GcUsReportImage[] {
  const merged = new Map<string, GcUsReportImage>();
  for (const image of [...previous, ...incoming]) {
    if (!image?.id || !image.url) continue;
    merged.set(image.id, image);
  }
  return [...merged.values()];
}

function contourIrregularity(points: number[][]): number | null {
  if (points.length < 3) return null;
  let area2 = 0;
  let perimeter = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area2 += current[0] * next[1] - next[0] * current[1];
    perimeter += Math.hypot(next[0] - current[0], next[1] - current[1]);
  }
  const area = Math.abs(area2) / 2;
  return area > 1e-3 && perimeter > 1e-3
    ? (perimeter * perimeter) / (4 * Math.PI * area)
    : null;
}

function reportStorageKey(caseId: string): string {
  return `next-gc-us-report:${caseId}`;
}

function readCachedReport(caseId: string): { state: GcUsReportState; updatedAt: number } | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(reportStorageKey(caseId));
    if (!raw) return null;
    const parsed = createGcUsReportState(JSON.parse(raw) as Partial<GcUsReportState>);
    const updatedAt = Number(window.localStorage.getItem(`${reportStorageKey(caseId)}:updated_at`) || 0);
    return { state: parsed, updatedAt: Number.isFinite(updatedAt) ? updatedAt : 0 };
  } catch {
    return null;
  }
}

function normalizeAgentStage(value: unknown): string | null {
  const raw = String(value || '').trim();
  const match = raw.toUpperCase().match(/\bT([1-4])(\+)?\b/);
  if (match) return `T${match[1]}${match[2] || ''}`;
  if (/^(benign|良性)$/i.test(raw)) return 'benign';
  if (/^(malignant|恶性)$/i.test(raw)) return 'malignant';
  return null;
}

function getReaderAgentStage(result: AgentAnalysisResponse | null): string | null {
  if (!result) return null;
  const hypotheses = result.belief_state?.hypotheses
    .filter((item) => normalizeAgentStage(item.label) && typeof item.probability === 'number')
    .sort((a, b) => Number(b.probability) - Number(a.probability));
  const beliefStage = normalizeAgentStage(hypotheses?.[0]?.label);
  if (beliefStage) return beliefStage;
  const classificationStage = normalizeAgentStage(result.tool_evidence?.classification?.top1_stage);
  if (classificationStage) return classificationStage;
  return normalizeAgentStage(result.report?.recommended_t_stage);
}

function getReaderAgentConfidence(result: AgentAnalysisResponse | null): number | null {
  if (!result) return null;
  const hypotheses = result.belief_state?.hypotheses
    .filter((item) => normalizeAgentStage(item.label) && typeof item.probability === 'number')
    .sort((a, b) => Number(b.probability) - Number(a.probability));
  const beliefConfidence = hypotheses?.[0]?.probability;
  if (typeof beliefConfidence === 'number' && Number.isFinite(beliefConfidence)) return beliefConfidence;
  const classifierConfidence = result.tool_evidence?.classification?.top1_prob;
  if (typeof classifierConfidence === 'number' && Number.isFinite(classifierConfidence)) {
    return classifierConfidence;
  }
  const answer = normalizeAgentStage(result.report?.recommended_t_stage);
  const binaryEvidence = (result.belief_state?.evidence || result.evidence || [])
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
  return binaryEvidence.find((item) => item.label === answer)?.confidence
    ?? binaryEvidence[0]?.confidence
    ?? null;
}

export default function Home() {
  const { dataset, cohortYear, queueId, language, readerOnly } = useSettings();
  const [conceptState, setConceptState] = useState<ConceptState>(DEFAULT_STATE);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [readerStudyMode, setReaderStudyMode] = useState<ReaderStudyMode>('benign_malignancy');
  const [systemReport, setSystemReport] = useState<SamReport | null>(null);
  const [dinoFeature, setDinoFeature] = useState<DinoFeatureResult | null>(null);
  const isReaderStudyQueue = selectedPatient?.phase === 'reader_v150';
  const isBenignQueue = selectedPatient?.phase === 'benign';
  const handleDinoFeatures = useCallback((result: DinoFeatureResult | null) => {
    setDinoFeature(result);
    if (result?.available) {
      setIsEvidencePanelOpen(true);
      const dinoImages = [
        result.feature_overlay_png
          ? reportImageFromBase64(
              'dino-feature-overlay',
              'DINO 区域特征可视化',
              result.feature_overlay_png,
              '当前病例 DINO 特征叠加图',
              'analysis',
            )
          : null,
        result.wall_evidence_overlay_png
          ? reportImageFromBase64(
              'dino-wall-evidence-overlay',
              'DINO 胃壁证据可视化',
              result.wall_evidence_overlay_png,
              '当前病例 DINO 胃壁证据叠加图',
              'wall',
            )
          : null,
      ].filter((image): image is GcUsReportImage => Boolean(image));
      if (dinoImages.length) {
        setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, dinoImages));
      }
    }
  }, []);

  useEffect(() => {
    setSelectedPatient(null);
    setAllPatients([]);
    setAgentAnalysis(null);
    setMaskOverride(null);
    setLumenOverride(null);
    setImagingAssist(null);
    setGcUsReport(null);
    setConceptState(DEFAULT_STATE);
    setAgentFilledCount(0);
    setIsDirty(false);
    setSaveStatus('idle');
    setSystemReport(null);
    setDinoFeature(null);
    deepLinkCaseAppliedRef.current = null;
    if (cohortYear === 'reader_v150') setReaderStudyMode('benign_malignancy');
  }, [cohortYear, dataset, queueId]);

  useEffect(() => {
    if (cohortYear === 'reader_v150') {
      setSelectedPatient(null);
      setSystemReport(null);
    }
  }, [readerStudyMode, cohortYear]);

  useEffect(() => {
    if (cohortYear !== 'reader_v150' || typeof window === 'undefined') return;
    const task = new URLSearchParams(window.location.search).get('reader_task');
    if (task === 'task2') setReaderStudyMode('t_staging');
    if (task === 'task1') setReaderStudyMode('benign_malignancy');
  }, [cohortYear]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  // Evidence drawer overlays the canvas; keep middle imaging dominant by default.
  const [isEvidencePanelOpen, setIsEvidencePanelOpen] = useState(false);
  const [, setIsReportExpanded] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);
  const [allPatients, setAllPatients] = useState<Patient[]>([]);
  const [patientConceptStates, setPatientConceptStates] = useState<Map<string, ConceptState>>(new Map());
  const [agentAnalysis, setAgentAnalysis] = useState<AgentAnalysisResponse | null>(null);
  const [readerUnifiedAgentResult, setReaderUnifiedAgentResult] = useState<AgentAnalysisResponse | null>(null);
  const [readerUnifiedAgentBusy, setReaderUnifiedAgentBusy] = useState(false);
  const [readerUnifiedAgentError, setReaderUnifiedAgentError] = useState<string | null>(null);
  const [readerWorkflowTrace, setReaderWorkflowTrace] = useState<WorkflowTraceStep[]>([]);
  const [readerReportOpen, setReaderReportOpen] = useState(false);
  const [readerFrameImage, setReaderFrameImage] = useState<string | null>(null);
  const [readerFrameImageMeta, setReaderFrameImageMeta] = useState<{
    frame_id?: string | null;
    frame_time?: number | null;
    source_video_url?: string | null;
  } | null>(null);
  const [maskOverride, setMaskOverride] = useState<MaskBoundaryOverride | null>(null);
  const [lumenOverride, setLumenOverride] = useState<LumenOverride | null>(null);
  const [imagingAssist, setImagingAssist] = useState<ImagingAssistPayload | null>(null);
  const [reportEvidenceImages, setReportEvidenceImages] = useState<GcUsReportImage[]>([]);
  const [gcUsReport, setGcUsReport] = useState<GcUsReportState | null>(null);
  const [agentFilledCount, setAgentFilledCount] = useState(0);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isDirty, setIsDirty] = useState(false);
  const [fieldSources, setFieldSources] = useState<ConceptFieldSources>(createDefaultFieldSources());

  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 720) {
      setIsSidebarOpen(false);
    }
  }, []);

  const clinicalBaselinesRef = useRef<Map<string, ConceptState>>(new Map());
  const fieldSourcesRef = useRef<Map<string, ConceptFieldSources>>(new Map());
  const userEditedRef = useRef<Set<string>>(new Set());
  const lastMergedAgentSessionRef = useRef<string | null>(null);
  const lastMergedExplainableRef = useRef<string | null>(null);
  const gcUsActionIdsRef = useRef<Set<string>>(new Set());
  const gcUsAuditSessionRef = useRef<string | null>(null);
  const patientConceptStatesRef = useRef<Map<string, ConceptState>>(new Map());
  const conceptLoadTokenRef = useRef(0);
  const reportLoadTokenRef = useRef(0);
  const reportLoadAbortRef = useRef<AbortController | null>(null);
  const readerAgentAbortRef = useRef<AbortController | null>(null);
  const selectedPatientRef = useRef<Patient | null>(null);
  const deepLinkCaseAppliedRef = useRef<string | null>(null);
  const conceptStateRef = useRef(conceptState);
  const saveConceptStateRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    conceptStateRef.current = conceptState;
  }, [conceptState]);

  useEffect(() => {
    patientConceptStatesRef.current = patientConceptStates;
  }, [patientConceptStates]);

  useEffect(() => {
    selectedPatientRef.current = selectedPatient;
  }, [selectedPatient]);

  useEffect(() => {
    if (typeof window === 'undefined' || !allPatients.length) return;
    const requestedCase = new URLSearchParams(window.location.search).get('case_id');
    if (!requestedCase || deepLinkCaseAppliedRef.current === requestedCase) return;
    const target = allPatients.find((patient) => (
      patient.id === requestedCase || patient.patient_id === requestedCase
    ));
    if (!target) return;
    deepLinkCaseAppliedRef.current = requestedCase;
    if (selectedPatientRef.current?.id !== target.id) setSelectedPatient(target);
  }, [allPatients]);

  const syncFieldSourcesForPatient = useCallback((patientId: string, sources: ConceptFieldSources) => {
    fieldSourcesRef.current.set(patientId, sources);
    setFieldSources(sources);
  }, []);

  useEffect(() => {
    setAgentAnalysis(null);
    setReaderUnifiedAgentResult(null);
    setReaderUnifiedAgentError(null);
    setReaderWorkflowTrace([]);
    setReaderReportOpen(false);
    setReaderFrameImage(null);
    setReaderFrameImageMeta(null);
    setAgentFilledCount(0);
    setSaveStatus('idle');
    setIsDirty(false);
    setImagingAssist(null);
    setReportEvidenceImages([]);
    setGcUsReport(null);
    setSystemReport(null);
    setDinoFeature(null);
    lastMergedAgentSessionRef.current = null;
    lastMergedExplainableRef.current = null;

    if (!selectedPatient) {
      setFieldSources(createDefaultFieldSources());
      return;
    }

    const cachedSources = fieldSourcesRef.current.get(selectedPatient.id);
    if (cachedSources) {
      setFieldSources(cachedSources);
      return;
    }

    const baseline = clinicalBaselinesRef.current.get(selectedPatient.id)
      ?? getConceptStateFromPatient(selectedPatient);
    syncFieldSourcesForPatient(selectedPatient.id, buildClinicalFieldSources(baseline));
  }, [selectedPatient, selectedPatient?.id, syncFieldSourcesForPatient]);

  useEffect(() => {
    const caseId = selectedPatient?.patient_id || selectedPatient?.id;
    reportLoadAbortRef.current?.abort();
    if (!caseId) {
      setGcUsReport(null);
      return;
    }
    const controller = new AbortController();
    reportLoadAbortRef.current = controller;
    const loadToken = reportLoadTokenRef.current + 1;
    reportLoadTokenRef.current = loadToken;
    const cached = readCachedReport(caseId);
    if (cached) {
      setGcUsReport(cached.state);
      setIsDirty(cached.updatedAt > 0);
    }
    void fetch(`/api/reports/template?case_id=${encodeURIComponent(caseId)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) return null;
        return await response.json() as {
          ok?: boolean;
          report?: GcUsReportState | null;
          metadata?: { updated_at?: string | null } | null;
        };
      })
      .then((payload) => {
        if (controller.signal.aborted || reportLoadTokenRef.current !== loadToken) return;
        if (!payload?.ok || !payload.report) {
          if (!cached) setGcUsReport(null);
          return;
        }
        const serverUpdatedAt = payload.metadata?.updated_at
          ? Date.parse(payload.metadata.updated_at)
          : 0;
        if (cached && cached.updatedAt > serverUpdatedAt) {
          setIsDirty(true);
          return;
        }
        setGcUsReport(createGcUsReportState(payload.report));
        setIsDirty(false);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || reportLoadTokenRef.current !== loadToken) return;
        if (!cached) setGcUsReport(null);
        // A missing report or a transient read failure must not block the case review.
        void error;
      });
    return () => {
      controller.abort();
      if (reportLoadAbortRef.current === controller) reportLoadAbortRef.current = null;
    };
  }, [selectedPatient, selectedPatient?.id, selectedPatient?.patient_id]);

  useEffect(() => {
    gcUsActionIdsRef.current.clear();
    readerAgentAbortRef.current?.abort();
    gcUsAuditSessionRef.current = selectedPatient
      ? `gcus-${selectedPatient.id}-${Date.now()}`
      : null;
  }, [selectedPatient, selectedPatient?.id]);

  const conceptPopulatedCount = useMemo(
    () => countPopulatedConceptFields(conceptState),
    [conceptState],
  );

  const handlePatientsLoaded = useCallback((patients: Patient[]) => {
    setAllPatients((prev) => {
      if (prev.length === patients.length && prev.every((item, index) => item.id === patients[index]?.id)) {
        return prev;
      }
      return patients;
    });
    if (!patients.length || (selectedPatient && !patients.some((item) => item.id === selectedPatient.id))) {
      setSelectedPatient(patients[0] || null);
      setAgentAnalysis(null);
      setMaskOverride(null);
      setLumenOverride(null);
      setImagingAssist(null);
    setReportEvidenceImages([]);
      setGcUsReport(null);
      setReaderFrameImage(null);
      setReaderFrameImageMeta(null);
      setConceptState(DEFAULT_STATE);
      setAgentFilledCount(0);
      setIsDirty(false);
      setSaveStatus('idle');
    }
  }, [selectedPatient]);

  const handleReaderUnifiedAgent = useCallback(async (capture: UnifiedAgentCapture) => {
    if (!selectedPatient || !isReaderStudyQueue) return;
    const lesionReady = capture.mask_polygon.length >= 3;
    const lumenReady = Boolean(
      (capture.lumen_polygon && capture.lumen_polygon.length >= 3)
      || capture.lumen_bbox,
    );
    if (!lesionReady || !lumenReady) {
      const message = !lesionReady
        ? '请先确认病灶分割轮廓'
        : '请先确认胃腔轮廓或胃腔框';
      setReaderUnifiedAgentError(`Agent 未运行：${message}`);
      toast.error(`Agent 未运行：${message}`);
      return;
    }
    const caseId = selectedPatient.id;
    readerAgentAbortRef.current?.abort();
    const controller = new AbortController();
    readerAgentAbortRef.current = controller;
    setReaderUnifiedAgentBusy(true);
    setReaderUnifiedAgentError(null);
    try {
      const primaryFrame = capture.frames.reduce((best, frame) => (
        Math.abs(frame.timestamp_sec - capture.current_time) < Math.abs(best.timestamp_sec - capture.current_time)
          ? frame
          : best
      ), capture.frames[0]);
      const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
      const environment = readerEnvironmentFromSearchParams(params);
      const readerId = environment === 'research'
        ? undefined
        : (params?.get('reader_id') || 'workbench_reader');
      const response = await fetch('/api/reader/agent/analyze', {
        method: 'POST',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...READER_ROUND2_VERSION_FIELDS,
          case_id: selectedPatient.id,
          patient_id: selectedPatient.patient_id,
          ...(readerId ? { reader_id: readerId } : {}),
          condition: 'ai_assisted',
          round: params?.get('round') || 'round2',
          environment,
          study_mode: selectedPatient.study_mode || readerStudyMode,
          frame_id: primaryFrame?.frame_id || selectedPatient.id,
          frame_time: primaryFrame?.timestamp_sec ?? capture.current_time,
          frame_png_b64: primaryFrame?.frame_png_b64,
          frames: capture.frames,
          workflow_trace: capture.workflow_trace?.length
            ? capture.workflow_trace
            : readerWorkflowTrace,
          gc_us_report: gcUsReport || undefined,
          mask_override: capture.mask_polygon.length
            ? {
                patientId: selectedPatient.patient_id,
                frameId: selectedPatient.id,
                imageWidth: capture.image_width,
                imageHeight: capture.image_height,
                mask_polygon: capture.mask_polygon,
                roi_bbox: capture.roi_bbox,
                source: 'sam',
                video_time_sec: capture.current_time,
              }
            : undefined,
          ...lumenOverrideToAnalyzePayload(
            capture.lumen_bbox
              ? {
                  patientId: selectedPatient.patient_id,
                  frameId: selectedPatient.id,
                  imageWidth: capture.image_width,
                  imageHeight: capture.image_height,
                  lumen_bbox: capture.lumen_bbox,
                  lumen_polygon: capture.lumen_polygon,
                  source: lumenOverride?.source || 'manual',
                  lumen_confidence: lumenOverride?.lumen_confidence,
                  lumen_mask_type: capture.lumen_polygon && capture.lumen_polygon.length >= 3
                    ? 'sam31_polygon'
                    : 'bbox_proxy',
                  detector_backend_id: lumenOverride?.detector_backend_id,
                  sam_backend_id: lumenOverride?.sam_backend_id,
                  sam_score: lumenOverride?.sam_score,
                  video_time_sec: capture.current_time,
                }
              : lumenOverride,
          ),
        }),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        result?: AgentAnalysisResponse;
      };
      if (controller.signal.aborted || selectedPatientRef.current?.id !== caseId) return;
      if (!response.ok || !data.ok || !data.result) {
        throw new Error(data.error || `Unified Agent HTTP ${response.status}`);
      }
      const frameImage = primaryFrame?.frame_png_b64;
      if (frameImage) {
        setReaderFrameImage(frameImage.startsWith('data:')
          ? frameImage
          : `data:image/png;base64,${frameImage}`);
        setReaderFrameImageMeta({
          frame_id: primaryFrame?.frame_id || selectedPatient.id,
          frame_time: primaryFrame?.timestamp_sec ?? capture.current_time,
          source_video_url: selectedPatient.video_urls?.[0]?.url || null,
        });
      }
      if (capture.mask_polygon.length >= 3) {
        setSystemReport(
          buildModelAssistReport(
            selectedPatient,
            capture.mask_polygon,
            capture.image_width,
            capture.image_height,
            'sabm_sam2_guided',
          ),
        );
      }
      setReaderUnifiedAgentResult(data.result);
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...READER_ROUND2_VERSION_FIELDS,
          event_type: 'ai_suggestion',
          session_id: `reader-unified-${caseId}`,
          case_id: caseId,
          ...(readerId ? { reader_id: readerId } : {}),
          condition: 'ai_assisted',
          study_mode: selectedPatient.study_mode || readerStudyMode,
          round: params?.get('round') || 'round2',
          environment,
          patient_id: selectedPatient.patient_id,
          payload: {
            source: 'unified_agent_bridge',
            recommended_t_stage: data.result.report?.recommended_t_stage || null,
            stage_distribution: data.result.report?.similar_case_summary?.stage_distribution || null,
            calibrated_confidence: data.result.report?.confidence || null,
            structured_signs: compactReaderSigns(data.result.report),
            evidence_ids: data.result.report?.supporting_evidence || readerEvidenceIds(data.result.report),
            report_status: data.result.report?.status || 'review_required',
            environment,
          },
          client_recorded_at: new Date().toISOString(),
        }),
      }).catch(() => {
        // Audit failure must not interrupt the reading workflow.
      });
      setReaderReportOpen(true);
      setIsEvidencePanelOpen(true);
      toast.success(language !== 'en' ? '辅助诊断意见已更新' : 'Assisted diagnosis updated');
    } catch (error) {
      if (controller.signal.aborted || selectedPatientRef.current?.id !== caseId) return;
      const message = error instanceof Error ? error.message : '统一 Agent 分析失败';
      setReaderUnifiedAgentError(message);
      toast.error(message);
    } finally {
      if (readerAgentAbortRef.current === controller) {
        readerAgentAbortRef.current = null;
        setReaderUnifiedAgentBusy(false);
      }
    }
  }, [gcUsReport, isReaderStudyQueue, language, lumenOverride, readerStudyMode, readerWorkflowTrace, selectedPatient]);

  const handleGcUsEvidenceState = useCallback((next: GcUsReportState) => {
    const currentPatient = selectedPatientRef.current;
    const currentCaseIds = currentPatient
      ? new Set([currentPatient.id, currentPatient.patient_id].filter(Boolean))
      : new Set<string>();
    if (!currentPatient || (next.case_id && !currentCaseIds.has(next.case_id))) return;
    setGcUsReport((previous) => mergeFreshEvidence(previous, next));
    if (currentPatient.phase !== 'reader_v150') return;
    const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
    const sessionId = gcUsAuditSessionRef.current || `gcus-${currentPatient.id}`;
    const environment = readerEnvironmentFromSearchParams(params);
    const readerId = environment === 'research'
      ? undefined
      : (params?.get('reader_id') || 'workbench_reader');
    const round = params?.get('round') || 'round2';
    for (const action of next.doctor_actions || []) {
      if (gcUsActionIdsRef.current.has(action.action_id)) continue;
      gcUsActionIdsRef.current.add(action.action_id);
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...READER_ROUND2_VERSION_FIELDS,
          event_id: action.action_id,
          event_type: 'doctor_action',
          session_id: sessionId,
          case_id: currentPatient.id,
          ...(readerId ? { reader_id: readerId } : {}),
          condition: 'ai_assisted',
          study_mode: currentPatient.study_mode || readerStudyMode,
          round,
          environment,
          patient_id: currentPatient.patient_id,
          payload: {
            action,
            report_schema_version: next.schema_version,
            template_id: next.template_id,
            reference_stage: next.reference_stage,
            signs: next.signs,
            template_fields: next.template_fields,
            report_status: next.report.status,
            doctor_actions: next.doctor_actions,
            structured_signs: compactReaderSigns({ signs: next.signs }),
            evidence_ids: next.report_images?.map((image) => image.id || image.label || image.kind).filter(Boolean) || [],
            environment,
          },
          client_recorded_at: new Date().toISOString(),
        }),
      }).catch(() => {
        // Audit failure must not interrupt the reading workflow.
      });
    }
  }, [readerStudyMode]);

  const handleWorkflowStep = useCallback((step: WorkflowTraceStep) => {
    setReaderWorkflowTrace((previous) => [...previous, step].slice(-160));
  }, []);

  const handleImagingAssist = useCallback((next: ImagingAssistPayload | null) => {
    setImagingAssist(next);
    if (!next) {
      setReportEvidenceImages([]);
      setGcUsReport(null);
      return;
    }
    const currentPatient = selectedPatientRef.current;
    if (currentPatient) {
      const clinical = {
        ...(currentPatient.clinical || {}),
        tumor_size_mm: currentPatient.clinical?.tumorSize?.length != null
          ? Number(currentPatient.clinical.tumorSize.length) * 10
          : undefined,
        tumor_thickness_mm: currentPatient.clinical?.tumorSize?.thickness != null
          ? Number(currentPatient.clinical.tumorSize.thickness) * 10
          : undefined,
      } as Record<string, unknown>;
      const layer = next.layerResult?.layer;
      const derivedSigns = deriveGcUsSigns({
        caseId: currentPatient.patient_id || currentPatient.id,
        frameId: currentPatient.id,
        clinical,
        layer: {
          label: next.layerResult?.inContact === false ? null : layer?.label,
          tHint: next.layerResult?.inContact === false ? null : layer?.tHint,
          inContact: next.layerResult?.inContact,
          confidence: typeof layer?.confidence === 'number' ? layer.confidence : null,
        },
        pixel: {
          irregularity: contourIrregularity(next.lesionPolygon),
        },
        evidenceRef: [
          currentPatient.id,
          next.frameSize ? `frame_size:${next.frameSize.width}x${next.frameSize.height}` : 'frame_size:unknown',
          next.wallPolygon.length >= 3 ? 'wall_polygon' : 'wall_unavailable',
        ],
      });
      if (next.lesionPolygon.length >= 3) {
        if (derivedSigns.layer_structure.value == null) {
          derivedSigns.layer_structure = createGcUsField(
            '当前帧层次显示有限，需多切面复核',
            { status: 'pending', source: 'live_contour', confidence: 0.25 },
          );
        }
        if (derivedSigns.serosa_change.value == null) {
          derivedSigns.serosa_change = createGcUsField(
            '当前帧浆膜连续性需多切面核对',
            { status: 'pending', source: 'live_contour', confidence: 0.25 },
          );
        }
        if (derivedSigns.perigastric_tissue.value == null) {
          derivedSigns.perigastric_tissue = createGcUsField(
            '当前帧胃周组织需多切面核对',
            { status: 'pending', source: 'live_contour', confidence: 0.25 },
          );
        }
      }
      const derived = createGcUsReportState({
        case_id: currentPatient.patient_id || currentPatient.id,
        frame_id: currentPatient.id,
        frame_time: null,
        clinical,
        signs: derivedSigns,
      });
      setGcUsReport((previous) => mergeFreshEvidence(previous, derived));
    }
  }, []);

  const handleReportEvidenceImages = useCallback((images: GcUsReportImage[], caseId?: string | null) => {
    if (caseId && selectedPatientRef.current?.id !== caseId) return;
    setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, images));
  }, []);

  const handleAgentAnalysis = useCallback((next: AgentAnalysisResponse | null) => {
    setAgentAnalysis(next);
    const artifacts = asRecord(next?.prediction_artifacts);
    if (!artifacts) return;
    const artifactImages = [
      ['agent-wall-analysis', '胃壁层次分析', artifacts.real_wall_analysis_panel_url],
      ['agent-curvature-analysis', '曲率/边界分析', artifacts.wall_penetration_heatmap_url || artifacts.boundary_analysis_panel_url],
      ['agent-dino-analysis', 'DINO 区域特征分析', artifacts.current_image_dino_feature_panel_url],
      ['agent-core-signs', '核心征象分析', artifacts.gc_us_sign_panel_url],
    ]
      .filter((item): item is [string, string, string] => typeof item[2] === 'string' && item[2].length > 0)
      .map(([id, label, url]) => ({
        id,
        label,
        url,
        kind: label.includes('曲率') ? 'curvature' as const : 'analysis' as const,
        caption: `${label}, 来自当前病例 Agent 产物`,
        selected: true,
      }));
    if (artifactImages.length) {
      setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, artifactImages));
    }
  }, []);

  const siblingImages = useMemo(() => {
    if (!selectedPatient || !allPatients.length) return [];
    const patientId = selectedPatient.patient_id;
    return allPatients.filter((p) => p.patient_id === patientId);
  }, [selectedPatient, allPatients]);

  const imagingNarrative = gcUsReport?.report.prose || null;
  const readerAssistantStage = getReaderAgentStage(readerUnifiedAgentResult);
  const readerAssistantConfidence = getReaderAgentConfidence(readerUnifiedAgentResult);
  const readerReportImages = useMemo<GcUsReportImage[]>(
    () => mergeReportEvidenceImages(
      reportEvidenceImages,
      readerFrameImage
        ? [{
            id: 'reader-current-frame',
            label: '当前关键帧原始图像',
            url: readerFrameImage,
            kind: 'original',
            caption: '统一 Agent 分析使用的当前关键帧',
            selected: true,
            frame_time: readerFrameImageMeta?.frame_time ?? null,
            source_frame_id: readerFrameImageMeta?.frame_id ?? null,
            source_video_url: readerFrameImageMeta?.source_video_url ?? null,
          }]
        : [],
    ),
    [readerFrameImage, readerFrameImageMeta, reportEvidenceImages],
  );
  const readerClinical = useMemo(() => {
    const clinical = selectedPatient?.clinical;
    if (!clinical) return EMPTY_READER_CLINICAL;
    const clinicalRecord = clinical as unknown as Record<string, unknown>;
    const lengthMm = clinicalMeasurementMm(
      clinicalRecord,
      ['tumor_size_mm', 'length_mm', 'tumorSizeMm', 'tumor_length_mm', 'long_diameter_mm', 'maximum_diameter_mm'],
      ['length_cm', 'tumor_size_cm', 'tumor_length_cm', 'long_diameter_cm', 'maximum_diameter_cm'],
      'length',
    );
    const thicknessMm = clinicalMeasurementMm(
      clinicalRecord,
      ['tumor_thickness_mm', 'thickness_mm', 'tumorThicknessMm', 'tumor_depth_mm', 'maximum_thickness_mm'],
      ['thickness_cm', 'tumor_thickness_cm', 'tumor_depth_cm', 'maximum_thickness_cm'],
      'thickness',
    );
    const nestedTumorSize = asRecord(clinicalRecord.tumorSize) || {};
    return {
      ...clinicalRecord,
      location: clinical.location,
      tumorSize: {
        ...nestedTumorSize,
        length: lengthMm == null ? nestedTumorSize.length : lengthMm / 10,
        thickness: thicknessMm == null ? nestedTumorSize.thickness : thicknessMm / 10,
      },
      biomarkers: clinical.biomarkers,
      tumor_size_mm: lengthMm ?? undefined,
      tumor_thickness_mm: thicknessMm ?? undefined,
      length_cm: lengthMm == null ? undefined : lengthMm / 10,
      thickness_cm: thicknessMm == null ? undefined : thicknessMm / 10,
      differentiation: clinical.differentiation,
      lauren: clinical.lauren,
      concept_features: clinical.concept_features,
      cea: clinical.biomarkers?.cea ?? undefined,
      cea_positive: clinical.biomarkers?.cea_positive ?? undefined,
      ca199: clinical.biomarkers?.ca199 ?? undefined,
      ca199_positive: clinical.biomarkers?.ca199_positive ?? undefined,
    };
  }, [selectedPatient?.clinical]);

  const applyConceptState = useCallback((patientId: string, state: ConceptState, markDirty = false) => {
    setConceptState(state);
    setPatientConceptStates((prevMap) => {
      const newMap = new Map(prevMap);
      newMap.set(patientId, state);
      patientConceptStatesRef.current = newMap;
      return newMap;
    });
    if (markDirty) {
      userEditedRef.current.add(patientId);
      setIsDirty(true);
      setSaveStatus('idle');
    }
  }, []);

  const handleStateChange = useCallback((key: keyof ConceptState, value: number) => {
    if (!selectedPatient) return;
    setConceptState((prev) => {
      const newState = { ...prev, [key]: value };
      setPatientConceptStates((prevMap) => {
        const newMap = new Map(prevMap);
        newMap.set(selectedPatient.id, newState);
        patientConceptStatesRef.current = newMap;
        return newMap;
      });
      userEditedRef.current.add(selectedPatient.id);
      setFieldSources((prevSources) => {
        const nextSources = markManualFieldSource(prevSources, key);
        fieldSourcesRef.current.set(selectedPatient.id, nextSources);
        return nextSources;
      });
      setIsDirty(true);
      setSaveStatus('idle');
      return newState;
    });
  }, [selectedPatient]);

  const handleSaveConceptState = useCallback(async () => {
    if (!selectedPatient) return;
    setSaveStatus('saving');
    try {
      const response = await fetch('/api/patients/concept-overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patientId: selectedPatient.id, state: conceptStateRef.current }),
      });
      if (!response.ok) throw new Error('Save failed');
      setSaveStatus('saved');
      setIsDirty(false);
    } catch {
      setSaveStatus('error');
    }
  }, [selectedPatient]);

  useEffect(() => {
    saveConceptStateRef.current = handleSaveConceptState;
  }, [handleSaveConceptState]);

  useEffect(() => {
    if (!selectedPatient || !isDirty) return;
    if (!userEditedRef.current.has(selectedPatient.id)) return;

    const timer = window.setTimeout(() => {
      void saveConceptStateRef.current?.();
    }, 1200);

    return () => window.clearTimeout(timer);
  }, [conceptState, isDirty, selectedPatient, selectedPatient?.id]);

  const handleResetConceptState = useCallback(async () => {
    if (!selectedPatient) return;
    const baseline = getConceptStateFromPatient(selectedPatient);
    clinicalBaselinesRef.current.set(selectedPatient.id, baseline);
    userEditedRef.current.delete(selectedPatient.id);
    fieldSourcesRef.current.delete(selectedPatient.id);
    applyConceptState(selectedPatient.id, baseline, false);
    syncFieldSourcesForPatient(selectedPatient.id, buildClinicalFieldSources(baseline));
    setIsDirty(false);
    setSaveStatus('idle');
    setAgentFilledCount(0);
    try {
      await fetch(`/api/patients/concept-overrides?patientId=${encodeURIComponent(selectedPatient.id)}`, {
        method: 'DELETE',
      });
    } catch {
      // 忽略删除失败，本地已恢复
    }
  }, [selectedPatient, applyConceptState, syncFieldSourcesForPatient]);

  useEffect(() => {
    if (!selectedPatient) return;
    const patient: Patient = selectedPatient;
    const patientId = patient.id;
    const loadToken = ++conceptLoadTokenRef.current;

    async function loadPatientConceptState() {
      const baseline = getConceptStateFromPatient(patient);
      clinicalBaselinesRef.current.set(patientId, baseline);
      if (!fieldSourcesRef.current.has(patientId)) {
        syncFieldSourcesForPatient(patientId, buildClinicalFieldSources(baseline));
      }

      const cached = patientConceptStatesRef.current.get(patientId);
      if (cached) {
        if (!userEditedRef.current.has(patientId)) {
          // 已有内存缓存（含 Agent 合并结果），直接复用，避免重复 fetch 导致界面闪动
          if (loadToken === conceptLoadTokenRef.current) {
            setConceptState(cached);
          }
          return;
        }
        if (loadToken === conceptLoadTokenRef.current) {
          setConceptState(cached);
        }
        return;
      }

      try {
        const response = await fetch(
          `/api/patients/concept-overrides?patientId=${encodeURIComponent(patientId)}`,
        );
        const data = await response.json() as { state?: ConceptState | null };
        if (loadToken !== conceptLoadTokenRef.current) return;

        const loaded = data.state ?? baseline;
        if (data.state) {
          const sources = buildClinicalFieldSources(baseline);
          for (const key of CONCEPT_STATE_KEYS) {
            if (loaded[key] !== baseline[key]) {
              sources[key] = 'manual';
            }
          }
          syncFieldSourcesForPatient(patientId, sources);
        }
        applyConceptState(patientId, loaded, Boolean(data.state));
        setIsDirty(Boolean(data.state));
      } catch {
        if (loadToken !== conceptLoadTokenRef.current) return;
        applyConceptState(patientId, baseline, false);
      }
    }

    loadPatientConceptState();
  }, [selectedPatient, selectedPatient?.id, applyConceptState, syncFieldSourcesForPatient]);

  useEffect(() => {
    if (!selectedPatient) {
      setMaskOverride(null);
      setLumenOverride(null);
      return;
    }
  }, [selectedPatient, selectedPatient?.id, selectedPatient?.patient_id]);

  useEffect(() => {
    if (!agentAnalysis || !selectedPatient) return;
    if (lastMergedAgentSessionRef.current === agentAnalysis.session_id) return;

    const patientId = selectedPatient.id;
    const baseline = clinicalBaselinesRef.current.get(patientId)
      ?? getConceptStateFromPatient(selectedPatient);

    setConceptState((prev) => {
      const merged = mergeAgentIntoConceptState(prev, baseline, agentAnalysis);
      const filled = countAgentFilledFields(prev, merged, baseline);
      setAgentFilledCount(filled);
      setFieldSources((prevSources) => {
        const nextSources = markAgentFilledSources(prevSources, prev, merged, baseline);
        fieldSourcesRef.current.set(patientId, nextSources);
        return nextSources;
      });
      setPatientConceptStates((prevMap) => {
        const newMap = new Map(prevMap);
        newMap.set(patientId, merged);
        patientConceptStatesRef.current = newMap;
        return newMap;
      });
      return merged;
    });

    lastMergedAgentSessionRef.current = agentAnalysis.session_id;
  }, [agentAnalysis?.session_id, selectedPatient?.id, agentAnalysis, selectedPatient]);

  const handleExplainableComplete = useCallback((result: ExplainableAnalysisResult) => {
    if (!selectedPatient || !result.success) return;

    const visualizationBase64 = result.visualization_base64;
    if (visualizationBase64) {
      setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, [
        reportImageFromBase64(
          'explainable-curvature-analysis',
          '曲率/边界风险分析',
          visualizationBase64,
          'Explainable 边界与曲率可视化, 基于当前分割轮廓',
          'curvature',
        ),
      ]));
    }

    const signature = `${selectedPatient.id}:${result.predicted_stage}:${result.composite_score}`;
    if (lastMergedExplainableRef.current === signature) return;

    const baseline = clinicalBaselinesRef.current.get(selectedPatient.id)
      ?? getConceptStateFromPatient(selectedPatient);

    setConceptState((prev) => {
      const merged = mergeExplainableIntoConceptState(prev, baseline, result);
      const filled = countAgentFilledFields(prev, merged, baseline);
      setAgentFilledCount((count) => count + filled);
      setFieldSources((prevSources) => {
        const nextSources = markAgentFilledSources(prevSources, prev, merged, baseline);
        fieldSourcesRef.current.set(selectedPatient.id, nextSources);
        return nextSources;
      });
      setPatientConceptStates((prevMap) => {
        const newMap = new Map(prevMap);
        newMap.set(selectedPatient.id, merged);
        patientConceptStatesRef.current = newMap;
        return newMap;
      });
      return merged;
    });

    lastMergedExplainableRef.current = signature;
  }, [selectedPatient]);

  return (
    <main className="flex h-screen w-screen min-w-0 flex-col overflow-hidden bg-[#08090a] text-gray-200 selection:bg-blue-500/30">
      <div className="h-16 min-h-0 shrink-0 border-b border-white/10 z-50">
        <Header
          onShowStatistics={() => setShowStatistics(true)}
          selectedPatient={selectedPatient}
        />
      </div>

      <div className="relative flex min-w-0 flex-1 overflow-hidden">
        <aside
          className={`relative z-20 flex min-h-0 shrink-0 flex-col overflow-hidden border-r border-white/10 bg-[#0b0b0d] transition-[width] duration-300 ease-in-out ${
            isSidebarOpen ? 'w-72' : 'pointer-events-none w-0 border-none'
          }`}
          aria-hidden={!isSidebarOpen}
        >
          <div className="h-full w-72">
            <PatientList
              key={`${dataset}-${queueId}-${cohortYear}-${readerStudyMode}`}
              readerStudyMode={readerStudyMode}
              onReaderStudyModeChange={setReaderStudyMode}
              onSelect={setSelectedPatient}
              selectedId={selectedPatient?.id || null}
              onPatientsLoaded={handlePatientsLoaded}
            />
          </div>
        </aside>

        <button
          type="button"
          onClick={() => setIsSidebarOpen((value) => !value)}
          className="absolute top-1/2 z-50 -translate-y-1/2 rounded-r-lg border border-white/15 bg-neutral-800/95 p-1.5 text-gray-200 shadow-lg backdrop-blur transition-[left] duration-300 hover:border-blue-500 hover:bg-blue-600 hover:text-white"
          style={{ left: isSidebarOpen ? '18rem' : '0px', zIndex: 100 }}
          title={isSidebarOpen
            ? (language !== 'en' ? '收起病例列表' : 'Collapse patient list')
            : (language !== 'en' ? '展开病例列表' : 'Expand patient list')}
          aria-label={isSidebarOpen
            ? (language !== 'en' ? '收起病例列表' : 'Collapse patient list')
            : (language !== 'en' ? '展开病例列表' : 'Expand patient list')}
        >
          {isSidebarOpen ? <ChevronLeft size={16} /> : <Users size={16} />}
        </button>

        <div className="relative z-[60] flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-black shadow-[inset_0_0_20px_rgba(0,0,0,0.5)]">
          {/* 视频综合分析入口（上传选帧）暂隐藏；病例视频分析走主工作台视频画布 */}
          {/* <VideoAnalysisUpload onAnalysisComplete={setAgentAnalysis} /> */}
          {!isReaderStudyQueue ? (
            <UltrasoundViewer
              key={`${selectedPatient?.id}-${dataset}`}
              patient={selectedPatient}
              siblingImages={siblingImages}
              onSelectSibling={setSelectedPatient}
              onExplainableComplete={handleExplainableComplete}
            />
          ) : null}
          {!isReaderStudyQueue && !isBenignQueue ? <AssistHub patient={selectedPatient} /> : null}
          {!isReaderStudyQueue && !isBenignQueue ? (
            <AgentWorkbenchPanel
              patient={selectedPatient}
              maskOverride={maskOverride}
              lumenOverride={lumenOverride}
              imagingAssist={imagingAssist}
              gcUsReport={gcUsReport}
              onAnalysisComplete={handleAgentAnalysis}
            />
          ) : null}
          <InteractiveSegPanel
            patient={selectedPatient}
            override={maskOverride}
            onOverrideChange={setMaskOverride}
            lumenOverride={lumenOverride}
            onLumenOverrideChange={setLumenOverride}
            onImagingAssist={handleImagingAssist}
            onSystemReport={setSystemReport}
            onDinoFeatures={handleDinoFeatures}
            onUnifiedAgentRun={isReaderStudyQueue ? handleReaderUnifiedAgent : undefined}
            unifiedAgentBusy={readerUnifiedAgentBusy}
            onWorkflowStep={isReaderStudyQueue ? handleWorkflowStep : undefined}
            onExplainableComplete={handleExplainableComplete}
            onReportEvidenceImages={handleReportEvidenceImages}
            inline={Boolean(selectedPatient)}
          />
          {!isReaderStudyQueue && !isBenignQueue && (
          <ReaderAgentResultCard
            patient={selectedPatient}
            onApplyStage={(stage) => {
              handleExplainableComplete({
                success: true,
                predicted_stage: stage,
                confidence: 'reader-agent',
                composite_score: 0.55,
              });
            }}
            onImportMaskPolygon={(polygon) => {
              if (!selectedPatient || !Array.isArray(polygon) || polygon.length < 3) return;
              const apply = (w: number, h: number) => {
                const next: MaskBoundaryOverride = {
                  patientId: selectedPatient.patient_id,
                  frameId: selectedPatient.id,
                  imageWidth: w,
                  imageHeight: h,
                  mask_polygon: polygon.map((p) => [Number(p[0]), Number(p[1])]),
                  wall_polygon: maskOverride?.wall_polygon,
                  source: 'imported',
                  updated_at: new Date().toISOString(),
                };
                void fetch('/api/patients/mask-overrides', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ override: next }),
                }).then(async (res) => {
                  if (!res.ok) return;
                  const data = await res.json();
                  if (data.override) setMaskOverride(data.override);
                });
              };
              const img = new Image();
              img.crossOrigin = 'anonymous';
              img.onload = () => apply(img.naturalWidth || 1024, img.naturalHeight || 768);
              img.onerror = () => apply(1024, 768);
              img.src = selectedPatient.image_url;
            }}
            onImportWallPolygon={(polygon) => {
              if (!selectedPatient || !Array.isArray(polygon) || polygon.length < 3) return;
              const existingMask = maskOverride?.mask_polygon;
              if (!existingMask || existingMask.length < 3) {
                // Need a lesion contour for schema; open editor so doctor can SAM/edit after wall import.
                window.dispatchEvent(new CustomEvent('gastric:open-boundary-edit', { detail: { sam: true } }));
              }
              const apply = (w: number, h: number) => {
                const next: MaskBoundaryOverride = {
                  patientId: selectedPatient.patient_id,
                  frameId: selectedPatient.id,
                  imageWidth: w,
                  imageHeight: h,
                  mask_polygon:
                    existingMask && existingMask.length >= 3
                      ? existingMask
                      : polygon.map((p) => [Number(p[0]), Number(p[1])]),
                  wall_polygon: polygon.map((p) => [Number(p[0]), Number(p[1])]),
                  source: 'imported',
                  updated_at: new Date().toISOString(),
                  note:
                    existingMask && existingMask.length >= 3
                      ? undefined
                      : 'wall_import_without_lesion — please edit green lesion contour',
                };
                void fetch('/api/patients/mask-overrides', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ override: next }),
                }).then(async (res) => {
                  if (!res.ok) return;
                  const data = await res.json();
                  if (data.override) setMaskOverride(data.override);
                });
              };
              const img = new Image();
              img.crossOrigin = 'anonymous';
              img.onload = () => apply(img.naturalWidth || 1024, img.naturalHeight || 768);
              img.onerror = () => apply(1024, 768);
              img.src = selectedPatient.image_url;
            }}
          />
          )}
        </div>

        {/* Right evidence drawer docks beside the canvas so the current frame stays visible */}
        <aside
          className={`relative z-20 flex min-h-0 shrink-0 flex-col overflow-hidden border-l border-white/10 bg-panel-bg shadow-[-12px_0_40px_rgba(0,0,0,0.35)] transition-[width] duration-300 ease-in-out ${
            isEvidencePanelOpen ? '' : 'pointer-events-none border-none'
          }`}
          style={{
            width: isEvidencePanelOpen ? EVIDENCE_PANEL_WIDTH : '0px',
          }}
          aria-hidden={!isEvidencePanelOpen}
        >
          <div className="flex min-w-72 shrink-0 flex-col gap-2 border-b border-white/10 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 text-[12px] font-semibold text-gray-200">
                {language === 'en' ? 'Evidence' : (language === 'zh-HK' ? '證據面板' : '证据面板')}
              </div>
              <button
                type="button"
                onClick={() => setIsEvidencePanelOpen(false)}
                className="rounded border border-white/10 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/5 hover:text-white"
              >
                {language === 'en' ? 'Close' : (language === 'zh-HK' ? '收起' : '收起')}
              </button>
            </div>
            {!isReaderStudyQueue && !isBenignQueue ? (
              <button
                type="button"
                disabled={!selectedPatient}
                onClick={() => window.dispatchEvent(new CustomEvent('gastric:open-full-report'))}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded border border-emerald-400/40 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-100 transition hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40"
                title={language === 'en' ? 'Open full report' : (language === 'zh-HK' ? '打開完整報告' : '打开完整报告')}
              >
                <FileText size={12} />
                {language === 'en' ? 'Full report' : (language === 'zh-HK' ? '完整報告' : '完整报告')}
              </button>
            ) : null}
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {!selectedPatient ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-xs text-gray-500">
              {language !== 'en' ? '当前队列没有可用病例；请选择其他队列或检查数据入口。' : 'No cases in this queue. Pick another queue or check the data source.'}
            </div>
          ) : isReaderStudyQueue ? (
            <div className="flex-1 overflow-y-auto p-3">
              <ReaderEvidencePanel
                result={readerUnifiedAgentResult}
                loading={readerUnifiedAgentBusy}
                zh={language !== 'en'}
                onOpenFullReport={() => setReaderReportOpen(true)}
              />
              <GcUsEvidencePanel
                caseId={selectedPatient.patient_id || selectedPatient.id}
                frameId={selectedPatient.id}
                frameTime={maskOverride?.video_time_sec ?? 0}
                clinical={readerClinical}
                lesionPolygon={imagingAssist?.lesionPolygon || maskOverride?.mask_polygon || EMPTY_POLYGON}
                wallPolygon={imagingAssist?.wallPolygon || maskOverride?.wall_polygon || EMPTY_POLYGON}
                lumenPolygon={imagingAssist?.lumenPolygon || EMPTY_POLYGON}
                lumenBBox={imagingAssist?.lumenBBox || null}
                frameSize={imagingAssist?.frameSize || (maskOverride ? { width: maskOverride.imageWidth, height: maskOverride.imageHeight } : null)}
                layerResult={imagingAssist?.layerResult || null}
                // Keep the unified stage display-only here; it must not silently
                // override the independent GC-US evidence state or doctor edits.
                productStage={null}
                assistantStage={readerAssistantStage}
                assistantConfidence={readerAssistantConfidence}
                signAnalysis={readerUnifiedAgentResult?.tool_evidence.gc_us_signs || null}
                initialState={gcUsReport}
                zh={language !== 'en'}
                compact
                onStateChange={handleGcUsEvidenceState}
              />
              {readerUnifiedAgentError ? (
                <div className="mt-2 rounded-lg border border-rose-400/20 bg-rose-400/5 px-2.5 py-2 text-[10px] leading-relaxed text-rose-200">
                  {readerUnifiedAgentError}
                </div>
              ) : null}
              <ReaderStudyQueuePanel
                patient={selectedPatient}
                patients={allPatients}
                compact
                studyMode={readerStudyMode}
                onStudyModeChange={setReaderStudyMode}
                onSelectPatient={setSelectedPatient}
                systemReport={systemReport}
                onSystemReportChange={setSystemReport}
                hideTaskChrome
                publicReaderOnly={readerOnly}
              />
            </div>
          ) : isBenignQueue ? (
            <div className="flex-1 overflow-y-auto p-3">
              <BenignTissueObservationCard patient={selectedPatient} />
            </div>
          ) : (
            <>
              <div className="flex h-[35%] min-h-0 shrink-0 flex-col border-b border-white/10 bg-panel-bg">
                <ConceptReasoning
                  state={conceptState}
                  onChange={handleStateChange}
                  onReset={handleResetConceptState}
                  onSave={handleSaveConceptState}
                  populatedCount={conceptPopulatedCount}
                  agentFilledCount={agentFilledCount}
                  fieldSources={fieldSources}
                  hasClinicalData={Boolean(selectedPatient?.clinical)}
                  isDirty={isDirty}
                  saveStatus={saveStatus}
                  autoSaveEnabled
                />
              </div>

              <div className="relative flex min-h-0 flex-1 flex-col bg-bg-dark">
                <div className="shrink-0 border-b border-white/10 p-2">
                  <GcUsImagingReportCard
                    patient={selectedPatient}
                    assist={imagingAssist}
                    zh={language !== 'en'}
                    signAnalysis={agentAnalysis?.tool_evidence.gc_us_signs || null}
                    initialState={gcUsReport}
                    onApplyCtStage={(stage) => {
                      handleExplainableComplete({
                        success: true,
                        predicted_stage: stage.startsWith('T') ? stage : `T${stage.replace(/^T/, '')}`,
                        confidence: 'gc-us-tscore',
                        composite_score: 0.6,
                      });
                    }}
                    onEvidenceStateChange={handleGcUsEvidenceState}
                  />
                </div>
                <DiagnosisPanel
                  state={conceptState}
                  patient={selectedPatient}
                  agentAnalysis={agentAnalysis}
                  systemReport={systemReport}
                  dinoFeature={dinoFeature}
                  gcUsReport={gcUsReport}
                    extraImages={reportEvidenceImages}
                  onGcUsReportChange={handleGcUsEvidenceState}
                  imagingNarrative={imagingNarrative}
                  onExpandedChange={setIsReportExpanded}
                />
              </div>
            </>
          )}
          </div>
        </aside>
        <button
          type="button"
          onClick={() => setIsEvidencePanelOpen((value) => !value)}
          className="absolute right-0 top-1/2 z-50 -translate-y-1/2 rounded-l-lg border border-white/20 bg-neutral-800/95 px-1.5 py-2 text-gray-100 shadow-lg backdrop-blur transition-[right] duration-300 hover:border-orange-400/50 hover:bg-orange-500/20 hover:text-white"
          style={{ right: isEvidencePanelOpen ? EVIDENCE_PANEL_WIDTH : '0px', zIndex: 100 }}
          title={isEvidencePanelOpen
            ? (language === 'en' ? 'Collapse evidence panel' : (language === 'zh-HK' ? '收起證據面板' : '收起证据面板'))
            : (language === 'en' ? 'Expand evidence panel' : (language === 'zh-HK' ? '展開證據面板' : '展开证据面板'))}
          aria-label={isEvidencePanelOpen
            ? (language === 'en' ? 'Collapse evidence panel' : (language === 'zh-HK' ? '收起證據面板' : '收起证据面板'))
            : (language === 'en' ? 'Expand evidence panel' : (language === 'zh-HK' ? '展開證據面板' : '展开证据面板'))}
        >
          {isEvidencePanelOpen ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>

        {showStatistics && (
          <div
            className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 p-8"
            style={{ zIndex: 200 }}
          >
            <div className="bg-[#0b0b0d] border border-white/10 rounded-xl w-full max-w-4xl h-[90vh] flex flex-col shadow-2xl">
              <div className="h-14 shrink-0 border-b border-white/10 flex items-center justify-between px-6">
                <div className="flex items-center gap-3">
                  <BarChart2 size={20} className="text-purple-400" />
                  <span className="text-sm font-bold text-gray-200 uppercase tracking-wider">
                    {language !== 'en' ? '队列统计分析' : 'Cohort Statistics'}
                  </span>
                </div>
                <button
                  onClick={() => setShowStatistics(false)}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-white"
                >
                  <X size={20} />
                </button>
              </div>
              <div className="flex-1 overflow-hidden">
                <StatisticsPanel patients={allPatients} conceptStates={patientConceptStates} />
              </div>
            </div>
          </div>
        )}
        {readerReportOpen && isReaderStudyQueue && selectedPatient && typeof document !== 'undefined'
          ? createPortal(
              <div
                className="fixed inset-0 z-[200000] flex flex-col backdrop-blur-md"
                style={{
                  backgroundColor: 'rgba(27, 33, 43, 0.92)',
                  WebkitBackdropFilter: 'blur(14px)',
                  backdropFilter: 'blur(14px)',
                }}
                role="dialog"
                aria-modal="true"
                aria-label={language !== 'en' ? '病例报告工作台' : 'Case report workspace'}
              >
                <div
                  className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 px-5 backdrop-blur-md"
                  style={{
                    backgroundColor: 'rgba(21, 27, 36, 0.9)',
                    WebkitBackdropFilter: 'blur(12px)',
                    backdropFilter: 'blur(12px)',
                  }}
                >
                  <div>
                    <div className="text-sm font-bold text-white">
                      {language !== 'en' ? '病例报告工作台' : 'Case report workspace'}
                    </div>
                    <div className="mt-1 text-[10px] text-slate-500">
                      {selectedPatient?.id_short || selectedPatient?.id || 'N/A'}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setReaderReportOpen(false)}
                    className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-[11px] text-slate-200 hover:border-rose-300/40 hover:bg-rose-300/10"
                    aria-label={language !== 'en' ? '关闭病例报告工作台' : 'Close case report workspace'}
                  >
                    {language !== 'en' ? '关闭' : 'Close'}
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-4 lg:p-6">
                  <div className="mx-auto max-w-7xl">
                    <DoctorReportStudio
                      patient={selectedPatient}
                      analysis={readerUnifiedAgentResult}
                      gcUsReport={gcUsReport}
                      systemReport={systemReport}
                      extraImages={readerReportImages}
                      onGcUsReportChange={handleGcUsEvidenceState}
                    />
                  </div>
                </div>
              </div>,
              document.body,
            )
          : null}
      </div>
    </main>
  );
}
