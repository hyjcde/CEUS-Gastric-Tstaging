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
} from '@/components/InteractiveSegPanel';
import { ReaderAgentResultCard } from '@/components/ReaderAgentResultCard';
import { ReaderStudyQueuePanel } from '@/components/ReaderStudyQueuePanel';
import { ReaderEvidencePanel } from '@/components/reader/ReaderEvidencePanel';
import { BenignTissueObservationCard } from '@/components/BenignTissueObservationCard';
import { AssistHub } from '@/components/AssistHub';
import { GcUsImagingReportCard } from '@/components/GcUsImagingReportCard';
import { GcUsEvidencePanel } from '@/components/GcUsEvidencePanel';
// VideoAnalysisUpload 暂隐藏（质量选帧上传入口）
import { ConceptState, DEFAULT_STATE, Patient, AgentAnalysisResponse, LumenOverride, MaskBoundaryOverride, ReaderStudyMode } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import toast from 'react-hot-toast';
import type { SamReport } from '@/lib/reader/types';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import { lumenOverrideToAnalyzePayload } from '@/lib/lumen-override';
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
    if (result?.available) setIsEvidencePanelOpen(true);
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
  const [readerReportOpen, setReaderReportOpen] = useState(false);
  const [maskOverride, setMaskOverride] = useState<MaskBoundaryOverride | null>(null);
  const [lumenOverride, setLumenOverride] = useState<LumenOverride | null>(null);
  const [imagingAssist, setImagingAssist] = useState<ImagingAssistPayload | null>(null);
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
  const conceptStateRef = useRef(conceptState);
  const saveConceptStateRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    conceptStateRef.current = conceptState;
  }, [conceptState]);

  useEffect(() => {
    patientConceptStatesRef.current = patientConceptStates;
  }, [patientConceptStates]);

  const syncFieldSourcesForPatient = useCallback((patientId: string, sources: ConceptFieldSources) => {
    fieldSourcesRef.current.set(patientId, sources);
    setFieldSources(sources);
  }, []);

  useEffect(() => {
    setAgentAnalysis(null);
    setReaderUnifiedAgentResult(null);
    setReaderUnifiedAgentError(null);
    setReaderReportOpen(false);
    setAgentFilledCount(0);
    setSaveStatus('idle');
    setIsDirty(false);
    setImagingAssist(null);
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
  }, [selectedPatient?.id, syncFieldSourcesForPatient]);

  useEffect(() => {
    gcUsActionIdsRef.current.clear();
    gcUsAuditSessionRef.current = selectedPatient
      ? `gcus-${selectedPatient.id}-${Date.now()}`
      : null;
  }, [selectedPatient?.id]);

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
      setGcUsReport(null);
      setConceptState(DEFAULT_STATE);
      setAgentFilledCount(0);
      setIsDirty(false);
      setSaveStatus('idle');
    }
  }, [selectedPatient]);

  const handleReaderUnifiedAgent = useCallback(async (capture: UnifiedAgentCapture) => {
    if (!selectedPatient || !isReaderStudyQueue) return;
    setReaderUnifiedAgentBusy(true);
    setReaderUnifiedAgentError(null);
    try {
      const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
      const response = await fetch('/api/reader/agent/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: selectedPatient.id,
          patient_id: selectedPatient.patient_id,
          reader_id: params?.get('reader_id') || 'workbench_reader',
          round: params?.get('round') || 'round2',
          study_mode: selectedPatient.study_mode || readerStudyMode,
          frame_id: selectedPatient.id,
          frame_time: capture.current_time,
          frame_png_b64: capture.frames[0]?.frame_png_b64,
          frames: capture.frames,
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
      if (!response.ok || !data.ok || !data.result) {
        throw new Error(data.error || `Unified Agent HTTP ${response.status}`);
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
      setReaderReportOpen(true);
      setIsEvidencePanelOpen(true);
      toast.success(language !== 'en' ? '辅助诊断意见已更新' : 'Assisted diagnosis updated');
    } catch (error) {
      const message = error instanceof Error ? error.message : '统一 Agent 分析失败';
      setReaderUnifiedAgentError(message);
      toast.error(message);
    } finally {
      setReaderUnifiedAgentBusy(false);
    }
  }, [gcUsReport, isReaderStudyQueue, language, lumenOverride, readerStudyMode, selectedPatient]);

  const handleGcUsEvidenceState = useCallback((next: GcUsReportState) => {
    setGcUsReport(next);
    if (!selectedPatient || !isReaderStudyQueue) return;
    const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
    const sessionId = gcUsAuditSessionRef.current || `gcus-${selectedPatient.id}`;
    const readerId = params?.get('reader_id') || 'workbench_reader';
    const round = params?.get('round') || 'round2';
    for (const action of next.doctor_actions || []) {
      if (gcUsActionIdsRef.current.has(action.action_id)) continue;
      gcUsActionIdsRef.current.add(action.action_id);
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: action.action_id,
          event_type: 'doctor_action',
          session_id: sessionId,
          case_id: selectedPatient.id,
          reader_id: readerId,
          round,
          patient_id: selectedPatient.patient_id,
          payload: {
            action,
            report_schema_version: next.schema_version,
            template_id: next.template_id,
            reference_stage: next.reference_stage,
            signs: next.signs,
            doctor_actions: next.doctor_actions,
          },
          client_recorded_at: new Date().toISOString(),
        }),
      }).catch(() => {
        // Audit failure must not interrupt the reading workflow.
      });
    }
  }, [isReaderStudyQueue, selectedPatient]);

  const handleImagingAssist = useCallback((next: ImagingAssistPayload | null) => {
    setImagingAssist(next);
    if (!next) setGcUsReport(null);
  }, []);

  const siblingImages = useMemo(() => {
    if (!selectedPatient || !allPatients.length) return [];
    const patientId = selectedPatient.patient_id;
    return allPatients.filter((p) => p.patient_id === patientId);
  }, [selectedPatient, allPatients]);

  const imagingNarrative = gcUsReport?.report.prose || null;
  const readerAssistantStage = getReaderAgentStage(readerUnifiedAgentResult);
  const readerAssistantConfidence = getReaderAgentConfidence(readerUnifiedAgentResult);
  const readerClinical = useMemo(() => {
    const clinical = selectedPatient?.clinical;
    if (!clinical) return EMPTY_READER_CLINICAL;
    // Patient.clinical.tumorSize is stored in cm; evidence panel expects mm.
    const lengthCm = clinical.tumorSize?.length;
    const thicknessCm = clinical.tumorSize?.thickness;
    return {
      location: clinical.location,
      tumorSize: clinical.tumorSize,
      biomarkers: clinical.biomarkers,
      tumor_size_mm: lengthCm != null && Number(lengthCm) > 0 ? Number(lengthCm) * 10 : undefined,
      tumor_thickness_mm: thicknessCm != null && Number(thicknessCm) > 0 ? Number(thicknessCm) * 10 : undefined,
      length_cm: lengthCm ?? undefined,
      thickness_cm: thicknessCm ?? undefined,
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
  }, [conceptState, isDirty, selectedPatient?.id]);

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
  }, [selectedPatient?.id, applyConceptState, syncFieldSourcesForPatient]);

  useEffect(() => {
    if (!selectedPatient) {
      setMaskOverride(null);
      setLumenOverride(null);
      return;
    }
    let cancelled = false;
    const patientId = selectedPatient.patient_id;
    const frameId = selectedPatient.id;
    (async () => {
      try {
        const qs = new URLSearchParams({ patientId, frameId });
        const res = await fetch(`/api/patients/mask-overrides?${qs.toString()}`);
        if (!res.ok) {
          if (!cancelled) setMaskOverride(null);
          return;
        }
        const data = await res.json() as { override?: MaskBoundaryOverride | null };
        if (!cancelled) setMaskOverride(data.override ?? null);
      } catch {
        if (!cancelled) setMaskOverride(null);
      }
    })();
    (async () => {
      try {
        const qs = new URLSearchParams({ patientId, frameId });
        const res = await fetch(`/api/patients/lumen-overrides?${qs.toString()}`);
        if (!res.ok) {
          if (!cancelled) setLumenOverride(null);
          return;
        }
        const data = await res.json() as { override?: LumenOverride | null };
        if (!cancelled) setLumenOverride(data.override ?? null);
      } catch {
        if (!cancelled) setLumenOverride(null);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedPatient?.id, selectedPatient?.patient_id]);

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
              gcUsReport={gcUsReport}
              onAnalysisComplete={setAgentAnalysis}
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
            onExplainableComplete={handleExplainableComplete}
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
                caseId={selectedPatient.id}
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
                initialState={null}
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
                    onApplyCtStage={(stage) => {
                      handleExplainableComplete({
                        success: true,
                        predicted_stage: stage.startsWith('T') ? stage : `T${stage.replace(/^T/, '')}`,
                        confidence: 'gc-us-tscore',
                        composite_score: 0.6,
                      });
                    }}
                    onEvidenceStateChange={setGcUsReport}
                  />
                </div>
                <DiagnosisPanel
                  state={conceptState}
                  patient={selectedPatient}
                  agentAnalysis={agentAnalysis}
                  systemReport={systemReport}
                  dinoFeature={dinoFeature}
                  gcUsReport={gcUsReport}
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
              <div className="fixed inset-0 z-[200000] flex flex-col bg-[#05080c]/95 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={language !== 'en' ? '病例报告工作台' : 'Case report workspace'}>
                <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 bg-[#0b1118]/95 px-5">
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
