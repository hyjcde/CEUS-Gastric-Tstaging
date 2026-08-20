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
import { BmEvidencePanel } from '@/components/BmEvidencePanel';
import {
  commitBmUsTemplateReport,
  createBmUsReportState,
  type BmUsReportState,
} from '@/lib/bm-us-report-template';
// VideoAnalysisUpload 暂隐藏（质量选帧上传入口）
import { ConceptState, DEFAULT_STATE, Patient, AgentAnalysisResponse, LumenOverride, MaskBoundaryOverride, ReaderStudyMode } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import toast from 'react-hot-toast';
import type { SamReport } from '@/lib/reader/types';
import {
  buildGcUsTemplateReport,
  commitGcUsTemplateReport,
  createGcUsReportState,
  isConcreteGcUsStage,
  normalizeLesionSite,
  createGcUsField,
  deriveGcUsSigns,
  resolveGcUsReportLocale,
  type GcUsReportImage,
  type GcUsReportState,
  type GcUsSigns,
  type GcUsStageBand,
} from '@/lib/gc-us-report-template';
import {
  hasLumenOrientation,
  mapLayerResultToGcUsDerive,
} from '@/lib/human-assist/map-layer-to-gc-us';
import { reportImageFromBase64 } from '@/lib/report-evidence-images';
import { estimateAxesMm } from '@/lib/gc-us-tscore';
import { isRenderableReportImageUrl, sanitizeReportImages } from '@/lib/report-image-url';
import { lumenOverrideToAnalyzePayload } from '@/lib/lumen-override';
import {
  compactReaderSigns,
  readerEnvironmentFromSearchParams,
  readerEvidenceIds,
  READER_ROUND2_VERSION_FIELDS,
} from '@/lib/reader/study-contract';
import { getAssistFiveClass, getAssistOpinionStage } from '@/lib/reader/assist-display-stage';
import { coerceAssistSignValue, defaultAssistSigns, type AssistSignKey } from '@/lib/reader/assist-sign-defaults';
import { CaseGoldReveal } from '@/components/CaseGoldReveal';
import { ChevronLeft, ChevronRight, Users, BarChart2, FileText, X, Layers } from 'lucide-react';
import { MobilePaneNav, MobileSheetHeader, type WorkbenchMobilePane } from '@/components/MobilePaneNav';
import { useMobileLayout } from '@/lib/reader/use-mobile-layout';
import { getConceptStateFromPatient, countPopulatedConceptFields } from '@/lib/patient-utils';
import { patientDisplayLabel } from '@/lib/patient-display';
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

import {
  WORKBENCH_EVIDENCE_WIDTH,
  WORKBENCH_PATIENT_LIST_REM,
} from '@/lib/reader/layout';

const EMPTY_READER_CLINICAL: Record<string, unknown> = {};
const EMPTY_POLYGON: number[][] = [];
const EVIDENCE_PANEL_WIDTH = WORKBENCH_EVIDENCE_WIDTH;
const PATIENT_LIST_WIDTH = `${WORKBENCH_PATIENT_LIST_REM}rem`;

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
  return getAssistFiveClass(result) || getAssistOpinionStage(result) || 'T2';
}

function getReaderAgentConfidence(result: AgentAnalysisResponse | null): number | null {
  if (!result) return null;
  const hypotheses = (result.belief_state?.hypotheses || [])
    .filter((item) => normalizeAgentStage(item.label) && typeof item.probability === 'number')
    .sort((a, b) => Number(b.probability) - Number(a.probability));
  const beliefConfidence = hypotheses[0]?.probability;
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
  const reportLocale = resolveGcUsReportLocale(language !== 'en');
  const { readerId: accountReaderId, authHeaders } = useDoctorAccount();
  const [conceptState, setConceptState] = useState<ConceptState>(DEFAULT_STATE);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [readerStudyMode, setReaderStudyMode] = useState<ReaderStudyMode>('benign_malignancy');
  const [systemReport, setSystemReport] = useState<SamReport | null>(null);
  const [dinoFeature, setDinoFeature] = useState<DinoFeatureResult | null>(null);
  const [researchInitialJudgmentReady, setResearchInitialJudgmentReady] = useState(false);
  const isReaderStudyQueue = selectedPatient?.phase === 'reader_v150';
  const isBenignQueue = selectedPatient?.phase === 'benign';
  const researchAiLocked = (() => {
    if (typeof window === 'undefined') return false;
    return readerEnvironmentFromSearchParams(new URLSearchParams(window.location.search)) === 'research'
      && !researchInitialJudgmentReady;
  })();
  const handleDinoFeatures = useCallback((result: DinoFeatureResult | null) => {
    setDinoFeature(result);
    if (result?.available) {
      setIsEvidencePanelOpen(true);
      const en = language === 'en';
      const dinoImages: GcUsReportImage[] = [];
      // Prefer the green wall-evidence overlay as the DINO figure.
      if (result.wall_evidence_overlay_png) {
        dinoImages.push({
          ...reportImageFromBase64(
            'dino-wall-evidence-overlay',
            en ? 'DINO wall-evidence visualization' : 'DINO 胃壁证据可视化（绿）',
            result.wall_evidence_overlay_png,
            en ? 'DINO wall-evidence heatmap (green)' : 'DINO 壁层证据热图（绿）',
            'analysis',
          ),
          selected: true,
        });
      }
      if (result.feature_overlay_png) {
        dinoImages.push({
          ...reportImageFromBase64(
            'dino-feature-overlay',
            en ? 'DINO regional feature visualization' : 'DINO 区域特征可视化',
            result.feature_overlay_png,
            en ? 'DINO feature overlay for the current case' : '当前病例 DINO 特征叠加图',
            'analysis',
          ),
          selected: false,
        });
      }
      if (dinoImages.length) {
        setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, dinoImages));
      }
    }
  }, [language]);

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
  const isMobile = useMobileLayout();
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => (
    typeof window === 'undefined' || window.innerWidth >= 768
  ));
  // Evidence drawer overlays the canvas; keep middle imaging dominant by default.
  // Default open on desktop so assist/evidence is findable; phones use a sheet.
  const [isEvidencePanelOpen, setIsEvidencePanelOpen] = useState(() => (
    typeof window === 'undefined' || window.innerWidth >= 768
  ));
  const [isWallLayerDockOpen, setIsWallLayerDockOpen] = useState(false);
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
  const [generatedReport, setGeneratedReport] = useState<GcUsReportState | null>(null);
  const [bmReport, setBmReport] = useState<BmUsReportState | null>(null);
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
    // Rebuild template prose when UI language switches so EN mode yields English report body.
    setGcUsReport((previous) => {
      if (!previous) return previous;
      if (previous.report.status === 'finalized') return previous;
      return buildGcUsTemplateReport(previous, reportLocale);
    });
  }, [reportLocale]);

  useEffect(() => {
    if (!isMobile) return;
    setIsSidebarOpen(false);
    setIsEvidencePanelOpen(false);
  }, [isMobile]);

  const mobilePane: WorkbenchMobilePane = isSidebarOpen
    ? 'cases'
    : isEvidencePanelOpen
      ? 'evidence'
      : 'viewer';

  const setMobilePane = useCallback((pane: WorkbenchMobilePane) => {
    setIsSidebarOpen(pane === 'cases');
    setIsEvidencePanelOpen(pane === 'evidence');
  }, []);

  const selectPatient = useCallback((patient: Patient) => {
    setSelectedPatient(patient);
    if (isMobile) {
      setIsSidebarOpen(false);
      setIsEvidencePanelOpen(false);
    }
  }, [isMobile]);

  useEffect(() => {
    const handler = (event: Event) => {
      const open = Boolean((event as CustomEvent<{ open?: boolean }>).detail?.open);
      setIsWallLayerDockOpen(open);
      if (open) setIsEvidencePanelOpen(true);
    };
    window.addEventListener('gastric:open-wall-layers', handler);
    return () => window.removeEventListener('gastric:open-wall-layers', handler);
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
  const handleAgentAnalysisRef = useRef<(next: AgentAnalysisResponse | null) => void>(() => {});
  const selectedPatientRef = useRef<Patient | null>(null);
  const gcUsReportRef = useRef<GcUsReportState | null>(null);
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
    gcUsReportRef.current = gcUsReport;
  }, [gcUsReport]);

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
    setGeneratedReport(null);
    setBmReport(null);
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
    setResearchInitialJudgmentReady(false);
    setReaderUnifiedAgentResult(null);
    setReaderUnifiedAgentError(null);
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
    const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
    if (readerEnvironmentFromSearchParams(params) === 'research' && !researchInitialJudgmentReady) {
      const message = language === 'en'
        ? 'Record the physician initial judgment before running AI analysis.'
        : '请先记录医生初始判断，再运行 AI 分析。';
      setReaderUnifiedAgentError(message);
      toast.error(message);
      return;
    }
    const lesionReady = capture.mask_polygon.length >= 3 || Boolean(capture.roi_bbox);
    if (!lesionReady) {
      const message = '请先标记关键帧并框选病灶';
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
      const environment = readerEnvironmentFromSearchParams(params);
      const readerId = environment === 'research'
        ? undefined
        : (accountReaderId || params?.get('reader_id') || 'workbench_reader');
      const response = await fetch('/api/reader/agent/analyze', {
        method: 'POST',
        signal: controller.signal,
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          ...READER_ROUND2_VERSION_FIELDS,
          case_id: selectedPatient.id,
          patient_id: selectedPatient.patient_id,
          ...(readerId ? { reader_id: readerId } : {}),
          condition: 'ai_assisted',
          round: params?.get('round') || 'round2',
          environment,
          study_mode: selectedPatient.study_mode || readerStudyMode,
          cohort_phase: selectedPatient.phase || null,
          frame_id: primaryFrame?.frame_id || selectedPatient.id,
          frame_time: primaryFrame?.timestamp_sec ?? capture.current_time,
          frame_png_b64: primaryFrame?.frame_png_b64,
          frames: capture.frames,
          clinical: selectedPatient.clinical || {},
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
          contour_context: capture.contour_context || {
            lesion_confirmed: lesionReady,
            lumen_optional: !(capture.lumen_polygon && capture.lumen_polygon.length >= 3) && !capture.lumen_bbox,
            lumen_mask_type: capture.lumen_polygon && capture.lumen_polygon.length >= 3
              ? 'sam31_polygon'
              : (capture.lumen_bbox ? 'bbox_proxy' : 'missing'),
            layer_label: imagingAssist?.layerResult?.layer?.label || null,
            layer_pixel_based: Boolean(imagingAssist?.layerResult?.pixelBased),
            in_contact: imagingAssist?.layerResult?.inContact ?? null,
          },
          assist_profile: capture.assist_profile || 'contour_anchored_fast',
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
            undefined,
            language !== 'en',
          ),
        );
      }
      setReaderUnifiedAgentResult(data.result);
      try {
        handleAgentAnalysisRef.current(data.result);
      } catch (renderError) {
        // Do not let a downstream render/parse failure mask a successful Assist result.
        console.error('assist post-process failed', renderError);
      }
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
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
      // Keep evidence panel open, but do not auto-popup the full report window
      // while CN/EN draft mixing is still being cleaned up.
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
  }, [accountReaderId, authHeaders, gcUsReport, imagingAssist, isReaderStudyQueue, language, lumenOverride, readerStudyMode, readerWorkflowTrace, researchInitialJudgmentReady, selectedPatient]);

  const handleGcUsEvidenceState = useCallback((next: GcUsReportState) => {
    const currentPatient = selectedPatientRef.current;
    const currentCaseIds = currentPatient
      ? new Set([currentPatient.id, currentPatient.patient_id].filter(Boolean))
      : new Set<string>();
    if (!currentPatient || (next.case_id && !currentCaseIds.has(next.case_id))) return;
    setGcUsReport((previous) => {
      const merged = mergeFreshEvidence(previous, next);
      const templated = buildGcUsTemplateReport(merged, reportLocale);
      const nextOwnsReport = next.report.doctor_edited || next.report.source === 'doctor' || next.report.status === 'finalized';
      const previousOwnsReport = previous?.report.status === 'finalized'
        || previous?.report.doctor_edited
        || previous?.report.source === 'doctor';
      return {
        ...templated,
        report: nextOwnsReport
          ? next.report
          : previousOwnsReport
            ? previous!.report
            : {
                ...templated.report,
                status: 'draft',
                source: 'template',
              },
      };
    });
    if (currentPatient.phase !== 'reader_v150') return;
    const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
    const sessionId = gcUsAuditSessionRef.current || `gcus-${currentPatient.id}`;
    const environment = readerEnvironmentFromSearchParams(params);
    const readerId = environment === 'research'
      ? undefined
      : (accountReaderId || params?.get('reader_id') || 'workbench_reader');
    const round = params?.get('round') || 'round2';
    for (const action of next.doctor_actions || []) {
      if (gcUsActionIdsRef.current.has(action.action_id)) continue;
      gcUsActionIdsRef.current.add(action.action_id);
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
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
  }, [accountReaderId, authHeaders, readerStudyMode]);

  const handleGenerateFullReport = useCallback(() => {
    if (!selectedPatient) return;
    if (readerStudyMode === 'benign_malignancy') {
      const current = bmReport || createBmUsReportState({
        case_id: selectedPatient.patient_id || selectedPatient.id,
        clinical: selectedPatient.clinical as Record<string, unknown> | undefined,
      });
      setBmReport(commitBmUsTemplateReport(current, reportLocale === 'en' ? 'en' : 'zh'));
      setReaderReportOpen(true);
      return;
    }
    if (!readerUnifiedAgentResult && !gcUsReport) {
      toast.error(language !== 'en' ? '请先点「辅助分析」，再生成完整报告' : 'Generate assist first, then the full report');
      return;
    }
    const current = gcUsReport || createGcUsReportState({
      case_id: selectedPatient.patient_id || selectedPatient.id,
      frame_id: selectedPatient.id,
    });
    const committed = commitGcUsTemplateReport(current, reportLocale);
    setGeneratedReport({
      ...committed,
      report: {
        ...committed.report,
        status: 'finalized',
        source: 'template',
      },
    });
    setReaderReportOpen(true);
  }, [bmReport, gcUsReport, language, readerStudyMode, readerUnifiedAgentResult, reportLocale, selectedPatient]);

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
      // Reports must never show blank measurements: fall back to mask-derived
      // axis estimates when clinical length/thickness are unavailable.
      if (
        (clinical.tumor_size_mm == null || clinical.tumor_thickness_mm == null)
        && next.lesionPolygon.length >= 3
        && next.frameSize
      ) {
        const estimated = estimateAxesMm(next.lesionPolygon, next.frameSize);
        if (estimated) {
          if (clinical.tumor_size_mm == null) clinical.tumor_size_mm = estimated.lengthMm;
          if (clinical.tumor_thickness_mm == null) clinical.tumor_thickness_mm = estimated.thicknessMm;
        }
      }
      const lumenOriented = hasLumenOrientation({
        lumenPolygon: next.lumenPolygon,
        lumenBBox: next.lumenBBox,
        wallPolygon: next.wallPolygon,
      });
      const mapped = mapLayerResultToGcUsDerive(next.layerResult, {
        lesionPolygon: next.lesionPolygon,
        wallPolygon: next.wallPolygon,
        frameSize: next.frameSize,
        lumenOriented,
        irregularityFn: contourIrregularity,
        caseId: currentPatient.patient_id || currentPatient.id,
        frameId: currentPatient.id,
      });
      const derivedSigns = deriveGcUsSigns({
        caseId: currentPatient.patient_id || currentPatient.id,
        frameId: currentPatient.id,
        clinical,
        layer: mapped.layer,
        pixel: mapped.pixel,
        evidenceRef: mapped.evidenceRef,
      });
      if (next.lesionPolygon.length >= 3) {
        // Report-template phrasing (no raw placeholder sentence embedded mid-prose).
        if (derivedSigns.layer_structure.value == null) {
          derivedSigns.layer_structure = createGcUsField(
            '层次显示欠清',
            { status: 'pending', source: 'live_contour', confidence: lumenOriented ? 0.25 : 0.18 },
          );
        }
        if (derivedSigns.perigastric_tissue.value == null) {
          derivedSigns.perigastric_tissue = createGcUsField(
            '胃周组织显示欠清',
            { status: 'pending', source: 'live_contour', confidence: 0.25 },
          );
        }
      }
      // Boss wall-layer template is the only doctor-facing formal output.
      // Imaging assist fills signs → template_fields → template prose; never Agent free text.
      const existingStage = gcUsReportRef.current?.reference_stage;
      const keepAssistStage = isConcreteGcUsStage(existingStage);
      const priorBand = keepAssistStage
        ? (existingStage?.requested_band || existingStage?.band || 'uncertain')
        : 'uncertain';
      const derived = buildGcUsTemplateReport(createGcUsReportState({
        case_id: currentPatient.patient_id || currentPatient.id,
        frame_id: currentPatient.id,
        frame_time: null,
        clinical,
        signs: derivedSigns,
        reference_stage: {
          band: priorBand,
          requested_band: priorBand,
          raw: keepAssistStage ? (existingStage?.raw || priorBand) : priorBand,
          source: keepAssistStage
            ? (existingStage?.source === 'doctor' || existingStage?.source === 'model'
              ? existingStage.source
              : 'product_score')
            : 'product_score',
          conflicts: existingStage?.conflicts || [],
        },
      }), reportLocale);
      setGcUsReport((previous) => {
        const merged = mergeFreshEvidence(previous, derived);
        const withTemplate = buildGcUsTemplateReport(merged, reportLocale);
        const keepDoctorReport = previous?.report.status === 'finalized'
          || previous?.report.doctor_edited
          || previous?.report.source === 'doctor';
        return {
          ...withTemplate,
          report: keepDoctorReport
            ? previous!.report
            : {
                ...withTemplate.report,
                status: 'draft',
                source: 'template',
              },
        };
      });
    }
  }, []);

  const handleReportEvidenceImages = useCallback((images: GcUsReportImage[], caseId?: string | null) => {
    if (caseId && selectedPatientRef.current?.id !== caseId) return;
    setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, images));
  }, []);

  const handleAgentAnalysis = useCallback((next: AgentAnalysisResponse | null) => {
    setAgentAnalysis(next);
    if (!next) return;
    const currentPatient = selectedPatientRef.current;
    if (currentPatient) {
      const signsRoot = asRecord(next.tool_evidence?.gc_us_signs) || {};
      const signsMap = asRecord(signsRoot.signs) || signsRoot;
      const reportSigns = asRecord((next.report as { signs?: unknown } | undefined)?.signs) || {};
      const contour = asRecord(next.report?.contour_diagnosis);
      const pickRaw = (value: unknown) => {
        if (value == null) return null;
        const text = String(value).trim();
        return text && text !== '未评估' && text.toLowerCase() !== 'not assessed' ? text : null;
      };
      const pickSign = (key: string) => {
        const field = asRecord(signsMap[key]) || asRecord(reportSigns[key]);
        const fromField = pickRaw(field?.value ?? field?.raw_value ?? field?.label);
        if (fromField) return fromField;
        if (typeof signsMap[key] === 'string') {
          const direct = pickRaw(signsMap[key]);
          if (direct) return direct;
        }
        const items = Array.isArray(signsRoot.items) ? signsRoot.items as Array<Record<string, unknown>> : [];
        const item = items.find((entry) => String(entry.id || entry.name || entry.field) === key);
        const fromItem = pickRaw(item?.value ?? item?.status ?? item?.label);
        if (fromItem) return fromItem;
        return pickRaw(contour?.[key]);
      };
      const clinical = {
        ...(currentPatient.clinical || {}),
      } as Record<string, unknown>;
      const lesionSite = normalizeLesionSite(
        clinical.location
        || clinical.site
        || clinical.lesion_site
        || clinical.tumor_location,
      );
      const assistSigns: Partial<GcUsSigns> = {};
      const agentSignKeys = [
        'layer_structure',
        'serosa_change',
        'boundary',
        'morphology',
        'growth_pattern',
        'perigastric_tissue',
        'lesion_echo',
      ] as const;
      const assistStage = getAssistOpinionStage(next) || getAssistFiveClass(next) || 'T2';
      const stageDefaults = defaultAssistSigns(assistStage);
      for (const key of agentSignKeys) {
        const signKey = key as AssistSignKey;
        const value = (
          signKey in stageDefaults
            ? coerceAssistSignValue(signKey, pickSign(key)) || stageDefaults[signKey]
            : pickSign(key)
        );
        if (value == null) continue;
        assistSigns[key] = createGcUsField(value, {
          status: 'suggested',
          source: 'model',
          note: language === 'en'
            ? 'Assist suggestion; physician review required'
            : '辅助分析建议，需医生复核',
        });
      }
      if (!assistSigns.lesion_echo) {
        assistSigns.lesion_echo = createGcUsField('低回声', {
          status: 'suggested',
          source: 'model',
          note: language === 'en'
            ? 'Assist suggestion; physician review required'
            : '辅助分析建议，需医生复核',
        });
      }
      const assistBand = ((): GcUsStageBand | null => {
        if (!assistStage) return null;
        if (assistStage === 'benign') return 'benign';
        if (assistStage === 'T4+' || assistStage === 'T4') return 'T4a';
        if (assistStage === 'T1' || assistStage === 'T2' || assistStage === 'T3' || assistStage === 'T4a' || assistStage === 'T4b') {
          return assistStage;
        }
        return null;
      })();
      if (Object.keys(assistSigns).length || assistBand) {
        setGcUsReport((previous) => {
          const derivedOnPrevious = createGcUsReportState({
            ...previous,
            case_id: currentPatient.patient_id || currentPatient.id,
            frame_id: currentPatient.id,
            clinical: { ...(previous?.clinical || {}), ...clinical },
            signs: {
              ...(previous?.signs || {}),
              ...assistSigns,
            },
            reference_stage: assistBand
              ? {
                  band: assistBand,
                  requested_band: assistBand,
                  raw: assistStage,
                  source: 'model',
                  conflicts: previous?.reference_stage?.conflicts || [],
                }
              : previous?.reference_stage,
            template_fields: previous?.template_fields,
          });
          const merged = mergeFreshEvidence(previous, derivedOnPrevious);
          const withProse = buildGcUsTemplateReport(merged, reportLocale);
          const keepDoctorReport = previous?.report.status === 'finalized'
            || previous?.report.doctor_edited
            || previous?.report.source === 'doctor';
          const keepDoctorStage = previous?.reference_stage.source === 'doctor'
            && isConcreteGcUsStage(previous.reference_stage);
          const staged: GcUsReportState = {
            ...withProse,
            template_fields: {
              ...withProse.template_fields,
              ...(lesionSite && withProse.template_fields.lesion_site?.source !== 'doctor'
                ? {
                    lesion_site: createGcUsField(lesionSite, {
                      status: 'suggested',
                      source: 'clinical',
                      note: language === 'en'
                        ? 'Site from the ultrasound report'
                        : '部位来自超声报告',
                    }),
                  }
                : {}),
            },
            reference_stage: keepDoctorStage
              ? previous!.reference_stage
              : assistBand
                ? {
                    band: assistBand,
                    requested_band: assistBand,
                    raw: assistStage,
                    source: 'model',
                    conflicts: previous?.reference_stage?.conflicts || [],
                  }
                : withProse.reference_stage,
          };
          const rewritten = buildGcUsTemplateReport(staged, reportLocale);
          const nextState: GcUsReportState = {
            ...rewritten,
            report: keepDoctorReport
              ? previous!.report
              : {
                  ...rewritten.report,
                  status: 'draft',
                  source: 'template',
                },
          };
          gcUsReportRef.current = nextState;
          if (typeof window !== 'undefined') {
            window.setTimeout(() => {
              window.dispatchEvent(new CustomEvent('gastric:template-report-updated', { detail: nextState }));
            }, 0);
          }
          return nextState;
        });
      }
    }
    const artifacts = asRecord(next.prediction_artifacts);
    if (!artifacts) return;
    const en = language === 'en';
    const artifactCatalog: Array<[string, string, string, unknown, 'wall' | 'curvature' | 'analysis']> = [
      // Wall analysis must use the boundary-analysis visualization, not DINO / penetration proxy.
      ['agent-wall-analysis', en ? 'Wall boundary analysis' : '胃壁边界分析', en ? 'Boundary-analysis visualization used for wall assessment' : '用于胃壁分析的边界分析可视化', artifacts.boundary_analysis_panel_url || artifacts.real_wall_analysis_panel_url, 'wall'],
      ['agent-curvature-analysis', en ? 'Curvature / boundary analysis' : '曲率/边界分析', en ? 'Curvature / boundary analysis from the current-case Agent output' : '曲率/边界分析, 来自当前病例 Agent 产物', artifacts.boundary_analysis_panel_url || artifacts.wall_penetration_heatmap_url, 'curvature'],
      // Prefer the green DINO wall-evidence single map over the composite feature panel.
      ['agent-dino-analysis', en ? 'DINO wall-evidence (green)' : 'DINO 壁层证据（绿）', en ? 'DINO wall-evidence heatmap (green)' : 'DINO 壁层证据热图（绿）', artifacts.dino_wall_evidence_map_url || artifacts.current_image_dino_feature_panel_url, 'analysis'],
      ['agent-core-signs', en ? 'Core imaging-sign analysis' : '核心征象分析', en ? 'Core imaging-sign analysis from the current-case Agent output' : '核心征象分析, 来自当前病例 Agent 产物', artifacts.gc_us_sign_panel_url, 'analysis'],
    ];
    const artifactImages = sanitizeReportImages(
      artifactCatalog
        .filter((item): item is [string, string, string, string, 'wall' | 'curvature' | 'analysis'] => isRenderableReportImageUrl(item[3]))
        .map(([id, label, caption, url, kind]) => ({
          id,
          label,
          url,
          kind,
          caption,
          // Prefer wall/boundary + green DINO wall-evidence.
          selected: id === 'agent-wall-analysis' || id === 'agent-curvature-analysis' || id === 'agent-dino-analysis',
        })),
    );
    if (artifactImages.length) {
      setReportEvidenceImages((previous) => mergeReportEvidenceImages(previous, artifactImages));
    }
  }, [language]);
  handleAgentAnalysisRef.current = handleAgentAnalysis;

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
            label: language === 'en' ? 'Current key-frame original image' : '当前关键帧原始图像',
            url: readerFrameImage,
            kind: 'original',
            caption: language === 'en'
              ? 'Current key frame used by the unified Agent analysis'
              : '统一 Agent 分析使用的当前关键帧',
            selected: true,
            frame_time: readerFrameImageMeta?.frame_time ?? null,
            source_frame_id: readerFrameImageMeta?.frame_id ?? null,
            source_video_url: readerFrameImageMeta?.source_video_url ?? null,
          }]
        : [],
    ),
    [language, readerFrameImage, readerFrameImageMeta, reportEvidenceImages],
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
      location: clinical.location
        || String(clinicalRecord.tumor_location || clinicalRecord.site || '').trim()
        || '',
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
          language === 'en' ? 'Wall boundary-analysis map' : '胃壁边界分析图',
          visualizationBase64,
          language === 'en'
            ? 'Boundary/curvature visualization from the current contour; used for wall analysis'
            : '基于当前分割轮廓的边界/曲率可视化，用作胃壁分析主图',
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
  }, [language, selectedPatient]);

  return (
    <main className="workbench-shell flex h-screen w-screen min-w-0 flex-col overflow-hidden bg-[#08090a] text-gray-200 selection:bg-blue-500/30">
      <div className="workbench-header h-12 min-h-0 shrink-0 border-b border-white/10 z-50 sm:h-14 lg:h-16">
        <Header
          onShowStatistics={() => setShowStatistics(true)}
          selectedPatient={selectedPatient}
        />
      </div>

      <div className="relative flex min-w-0 flex-1 overflow-hidden">
        <aside
          className={`workbench-aside-cases relative z-20 flex min-h-0 shrink-0 flex-col overflow-hidden border-r border-white/10 bg-[#0b0b0d] transition-[width,transform] duration-300 ease-in-out ${
            isSidebarOpen ? (isMobile ? 'mobile-open' : '') : 'pointer-events-none w-0 border-none'
          }`}
          style={isMobile ? undefined : { width: isSidebarOpen ? PATIENT_LIST_WIDTH : 0 }}
          aria-hidden={!isSidebarOpen}
        >
          <div className="flex h-full min-h-0 flex-col" style={{ width: isMobile ? '100%' : PATIENT_LIST_WIDTH }}>
            <MobileSheetHeader
              title={language === 'en' ? 'Cases' : (language === 'zh-HK' ? '病例' : '病例')}
              onClose={() => setMobilePane('viewer')}
              language={language}
            />
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <PatientList
              key={`${dataset}-${queueId}-${cohortYear}-${readerStudyMode}`}
              readerStudyMode={readerStudyMode}
              onReaderStudyModeChange={setReaderStudyMode}
              onSelect={selectPatient}
              selectedId={selectedPatient?.id || null}
              onPatientsLoaded={handlePatientsLoaded}
            />
            </div>
          </div>
        </aside>

        <button
          type="button"
          onClick={() => setIsSidebarOpen((value) => !value)}
          className="workbench-desktop-toggle absolute top-1/2 z-50 -translate-y-1/2 rounded-r-lg border border-white/15 bg-neutral-800/95 p-1.5 text-gray-200 shadow-lg backdrop-blur transition-[left] duration-300 hover:border-blue-500 hover:bg-blue-600 hover:text-white"
          style={{ left: isSidebarOpen ? PATIENT_LIST_WIDTH : '0px', zIndex: 100 }}
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
            onUnifiedAgentRun={isReaderStudyQueue && !researchAiLocked ? handleReaderUnifiedAgent : undefined}
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
          className={`workbench-aside-evidence relative z-20 flex min-h-0 shrink-0 flex-col overflow-hidden border-l border-white/10 bg-panel-bg shadow-[-12px_0_40px_rgba(0,0,0,0.35)] transition-[width,transform] duration-300 ease-in-out ${
            isEvidencePanelOpen ? (isMobile ? 'mobile-open' : '') : 'pointer-events-none border-none'
          }`}
          style={isMobile ? undefined : {
            width: isEvidencePanelOpen ? EVIDENCE_PANEL_WIDTH : '0px',
          }}
          aria-hidden={!isEvidencePanelOpen}
        >
          <div className="flex min-w-0 shrink-0 flex-col gap-2 border-b border-white/10 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-1.5 text-[12px] font-semibold text-gray-200">
                {isWallLayerDockOpen ? <Layers size={13} className="shrink-0 text-orange-300" /> : null}
                {isWallLayerDockOpen
                  ? (language === 'en' ? 'Wall layers' : (language === 'zh-HK' ? '壁層' : '壁层'))
                  : (language === 'en' ? 'Evidence' : (language === 'zh-HK' ? '證據面板' : '证据面板'))}
              </div>
              <div className="flex items-center gap-1.5">
              {isWallLayerDockOpen ? (
              <button
                type="button"
                onClick={() => {
                  window.dispatchEvent(new CustomEvent('gastric:open-wall-layers', { detail: { open: false } }));
                }}
                className="rounded border border-white/10 px-2 py-1 text-[11px] text-gray-300 hover:bg-white/5 hover:text-white"
              >
                {language === 'en' ? 'Close' : (language === 'zh-HK' ? '收起' : '收起')}
              </button>
              ) : null}
              <button
                type="button"
                onClick={() => setMobilePane('viewer')}
                className="workbench-sheet-bar items-center rounded border border-white/15 px-2 py-1 text-[11px] text-gray-200"
              >
                {language === 'en' ? 'Done' : (language === 'zh-HK' ? '完成' : '完成')}
              </button>
              </div>
            </div>
            {!isBenignQueue && !isWallLayerDockOpen ? (
              <button
                type="button"
                disabled={!selectedPatient}
                onClick={() => {
                  if (isReaderStudyQueue) handleGenerateFullReport();
                  else window.dispatchEvent(new CustomEvent('gastric:open-full-report'));
                }}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded border border-emerald-400/50 bg-emerald-500/20 px-3 py-2.5 text-[13px] font-bold text-emerald-50 transition hover:bg-emerald-500/30 disabled:cursor-not-allowed disabled:opacity-40"
                title={language === 'en' ? 'Confirm and open the full report' : (language === 'zh-HK' ? '確認並打開完整報告' : '确认并打开完整报告')}
              >
                <FileText size={14} />
                {language === 'en' ? 'Generate report' : (language === 'zh-HK' ? '生成報告' : '生成报告')}
              </button>
            ) : null}
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {isWallLayerDockOpen ? (
            <div id="wall-layer-dock" className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3" />
          ) : !selectedPatient ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-xs text-gray-500">
              {language !== 'en' ? '当前队列没有可用病例；请选择其他队列或检查数据入口。' : 'No cases in this queue. Pick another queue or check the data source.'}
            </div>
          ) : isReaderStudyQueue ? (
            <div className="flex-1 overflow-y-auto p-3">
              {researchAiLocked ? (
                <div className="mb-3 rounded-lg border border-sky-500/30 bg-sky-500/[0.08] p-2.5 text-[10px] leading-relaxed text-sky-100">
                  {language === 'en'
                    ? 'Research mode: AI evidence panels and Agent analysis stay hidden until the physician initial judgment is recorded below.'
                    : '研究模式：请先在下方记录医生初始判断；完成前不展示 AI 证据面板，也不运行 Agent 分析。'}
                </div>
              ) : (
                <>
                  <ReaderEvidencePanel
                    result={readerUnifiedAgentResult}
                    loading={readerUnifiedAgentBusy}
                    zh={language !== 'en'}
                    onOpenFullReport={handleGenerateFullReport}
                    goldPatientId={selectedPatient.patient_id}
                    goldCaseId={selectedPatient.id}
                    goldPhase={selectedPatient.phase}
                    goldGroup={selectedPatient.group}
                    studyMode={selectedPatient.study_mode || readerStudyMode}
                  />
                  {readerStudyMode === 'benign_malignancy' ? (
                    <BmEvidencePanel
                      caseId={selectedPatient.patient_id || selectedPatient.id}
                      clinical={readerClinical}
                      assistNature={
                        readerUnifiedAgentResult
                          ? (getAssistFiveClass(readerUnifiedAgentResult) === 'benign' ? 'benign' : 'malignant')
                          : null
                      }
                      compact
                      onStateChange={setBmReport}
                    />
                  ) : (
                    <GcUsEvidencePanel
                      caseId={selectedPatient.patient_id || selectedPatient.id}
                      showBiomarkers
                      frameId={selectedPatient.id}
                      frameTime={maskOverride?.video_time_sec ?? 0}
                      clinical={readerClinical}
                      lesionPolygon={imagingAssist?.lesionPolygon || maskOverride?.mask_polygon || EMPTY_POLYGON}
                      wallPolygon={imagingAssist?.wallPolygon || maskOverride?.wall_polygon || EMPTY_POLYGON}
                      lumenPolygon={imagingAssist?.lumenPolygon || EMPTY_POLYGON}
                      lumenBBox={imagingAssist?.lumenBBox || null}
                      frameSize={imagingAssist?.frameSize || (maskOverride ? { width: maskOverride.imageWidth, height: maskOverride.imageHeight } : null)}
                      layerResult={imagingAssist?.layerResult || null}
                      productStage={null}
                      assistantStage={readerAssistantStage}
                      assistantConfidence={readerAssistantConfidence}
                      signAnalysis={readerUnifiedAgentResult?.tool_evidence?.gc_us_signs || null}
                      initialState={gcUsReport}
                      zh={language !== 'en'}
                      compact
                      onStateChange={handleGcUsEvidenceState}
                    />
                  )}
                </>
              )}
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
                systemReport={researchAiLocked ? null : systemReport}
                onSystemReportChange={setSystemReport}
                onInitialJudgmentChange={setResearchInitialJudgmentReady}
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
                    signAnalysis={agentAnalysis?.tool_evidence?.gc_us_signs || null}
                    agentResult={agentAnalysis}
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
          className="workbench-desktop-toggle absolute right-0 top-1/2 z-50 -translate-y-1/2 rounded-l-lg border border-white/20 bg-neutral-800/95 px-1.5 py-2 text-gray-100 shadow-lg backdrop-blur transition-[right] duration-300 hover:border-orange-400/50 hover:bg-orange-500/20 hover:text-white"
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
        {/* Top-right text entry survives browser translation widgets that cover the mid-right chevron. */}
        <button
          type="button"
          onClick={() => setIsEvidencePanelOpen((value) => !value)}
          className="workbench-assist-chip absolute top-3 z-[120] inline-flex items-center gap-1.5 rounded-lg border border-sky-300/50 bg-sky-500/25 px-3 py-1.5 text-[11px] font-semibold text-sky-50 shadow-lg backdrop-blur transition hover:bg-sky-500/40"
          style={{ right: isEvidencePanelOpen ? `calc(${EVIDENCE_PANEL_WIDTH} + 0.75rem)` : '0.75rem' }}
          title={language === 'en' ? 'Toggle assisted evidence panel' : '打开/收起辅助分析与证据面板'}
        >
          <FileText size={13} />
          {isEvidencePanelOpen
            ? (language === 'en' ? 'Hide assist' : '收起辅助分析')
            : (language === 'en' ? 'Show assist' : '打开辅助分析')}
        </button>

        {showStatistics && (
          <div
            className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 p-3 sm:p-8"
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
                className="fixed inset-0 z-[200000] flex flex-col bg-black"
                role="dialog"
                aria-modal="true"
                aria-label={language !== 'en' ? '病例报告工作台' : 'Case report workspace'}
              >
                <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-black px-4 pt-[env(safe-area-inset-top)] sm:px-5">
                  <div>
                    <div className="text-sm font-bold text-white">
                      {language !== 'en' ? '病例报告工作台' : 'Case report workspace'}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                      <span>{patientDisplayLabel(selectedPatient, language)}</span>
                      <CaseGoldReveal
                        patientId={selectedPatient.patient_id}
                        caseId={selectedPatient.id}
                        recordId={selectedPatient.id}
                        phase={selectedPatient.phase}
                        group={selectedPatient.group}
                        available={selectedPatient.gold_available !== false}
                        zh={language !== 'en'}
                        compact
                      />
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
                <div className="min-h-0 flex-1 overflow-hidden bg-black">
                  <DoctorReportStudio
                    patient={selectedPatient}
                    analysis={readerUnifiedAgentResult}
                    gcUsReport={generatedReport || gcUsReport}
                    bmReport={bmReport}
                    studyMode={selectedPatient.study_mode || readerStudyMode}
                    systemReport={systemReport}
                    extraImages={readerReportImages}
                    readOnly
                  />
                </div>
              </div>,
              document.body,
            )
          : null}
      </div>
      <MobilePaneNav
        pane={mobilePane}
        onChange={setMobilePane}
        language={language}
        caseLabel={selectedPatient ? patientDisplayLabel(selectedPatient, language) : null}
      />
    </main>
  );
}
