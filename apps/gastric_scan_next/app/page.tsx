"use client";

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Header } from '@/components/Header';
import { PatientList } from '@/components/PatientList';
import { UltrasoundViewer } from '@/components/UltrasoundViewer';
import { ConceptReasoning } from '@/components/ConceptReasoning';
import { DiagnosisPanel } from '@/components/DiagnosisPanel';
import { StatisticsPanel } from '@/components/StatisticsPanel';
import { AgentWorkbenchPanel } from '@/components/AgentWorkbenchPanel';
import {
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
// VideoAnalysisUpload 暂隐藏（质量选帧上传入口）
import { ConceptState, DEFAULT_STATE, Patient, AgentAnalysisResponse, MaskBoundaryOverride, ReaderStudyMode } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import toast from 'react-hot-toast';
import type { SamReport } from '@/lib/reader/types';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import { ChevronLeft, ChevronRight, Users, BarChart2, X } from 'lucide-react';
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

export default function Home() {
  const { dataset, cohortYear, queueId, language, readerOnly } = useSettings();
  const [conceptState, setConceptState] = useState<ConceptState>(DEFAULT_STATE);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [readerStudyMode, setReaderStudyMode] = useState<ReaderStudyMode>('benign_malignancy');
  const [systemReport, setSystemReport] = useState<SamReport | null>(null);
  const [dinoFeature, setDinoFeature] = useState<DinoFeatureResult | null>(null);
  const isReaderStudyQueue = selectedPatient?.phase === 'reader_v150';
  const isBenignQueue = selectedPatient?.phase === 'benign';

  useEffect(() => {
    setSelectedPatient(null);
    setAllPatients([]);
    setAgentAnalysis(null);
    setMaskOverride(null);
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
  const [isEvidencePanelOpen, setIsEvidencePanelOpen] = useState(true);
  const [isReportExpanded, setIsReportExpanded] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);
  const [allPatients, setAllPatients] = useState<Patient[]>([]);
  const [patientConceptStates, setPatientConceptStates] = useState<Map<string, ConceptState>>(new Map());
  const [agentAnalysis, setAgentAnalysis] = useState<AgentAnalysisResponse | null>(null);
  const [readerUnifiedAgentResult, setReaderUnifiedAgentResult] = useState<AgentAnalysisResponse | null>(null);
  const [readerUnifiedAgentBusy, setReaderUnifiedAgentBusy] = useState(false);
  const [readerUnifiedAgentError, setReaderUnifiedAgentError] = useState<string | null>(null);
  const [maskOverride, setMaskOverride] = useState<MaskBoundaryOverride | null>(null);
  const [imagingAssist, setImagingAssist] = useState<ImagingAssistPayload | null>(null);
  const [gcUsReport, setGcUsReport] = useState<GcUsReportState | null>(null);
  const [agentFilledCount, setAgentFilledCount] = useState(0);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isDirty, setIsDirty] = useState(false);
  const [fieldSources, setFieldSources] = useState<ConceptFieldSources>(createDefaultFieldSources());

  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 1180) {
      setIsSidebarOpen(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 900) {
      setIsEvidencePanelOpen(false);
    }
  }, []);

  const clinicalBaselinesRef = useRef<Map<string, ConceptState>>(new Map());
  const fieldSourcesRef = useRef<Map<string, ConceptFieldSources>>(new Map());
  const userEditedRef = useRef<Set<string>>(new Set());
  const lastMergedAgentSessionRef = useRef<string | null>(null);
  const lastMergedExplainableRef = useRef<string | null>(null);
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
      setReaderUnifiedAgentResult(data.result);
      toast.success('统一科研 Agent 已完成当前视频窗口分析');
    } catch (error) {
      const message = error instanceof Error ? error.message : '统一 Agent 分析失败';
      setReaderUnifiedAgentError(message);
      toast.error(message);
    } finally {
      setReaderUnifiedAgentBusy(false);
    }
  }, [gcUsReport, isReaderStudyQueue, readerStudyMode, selectedPatient]);

  const siblingImages = useMemo(() => {
    if (!selectedPatient || !allPatients.length) return [];
    const patientId = selectedPatient.patient_id;
    return allPatients.filter((p) => p.patient_id === patientId);
  }, [selectedPatient, allPatients]);

  const imagingNarrative = gcUsReport?.report.prose || null;

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
        <div
          className={`z-40 flex min-h-0 shrink-0 flex-col overflow-hidden border-r border-white/10 bg-[#0b0b0d] transition-all duration-300 ease-in-out ${
            isSidebarOpen ? 'w-72 translate-x-0' : 'w-0 -translate-x-full opacity-0 border-none'
          }`}
        >
          <div className="w-72 h-full">
            <PatientList
              key={`${dataset}-${queueId}-${cohortYear}-${readerStudyMode}`}
              readerStudyMode={readerStudyMode}
              onSelect={setSelectedPatient}
              selectedId={selectedPatient?.id || null}
              onPatientsLoaded={handlePatientsLoaded}
            />
          </div>
        </div>

        {!isReportExpanded && (
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className={`absolute top-1/2 z-[200600] -translate-y-1/2 rounded-r-lg border border-white/10 bg-neutral-800/90 p-1.5 text-gray-400 shadow-lg backdrop-blur transition-all duration-300 hover:border-blue-500 hover:bg-blue-600 hover:text-white ${
              isSidebarOpen ? 'left-72' : 'left-0'
            }`}
            title={isSidebarOpen
              ? (language === 'zh' ? '收起病例列表' : 'Collapse patient list')
              : (language === 'zh' ? '展开病例列表' : 'Expand patient list')}
          >
            {isSidebarOpen ? <ChevronLeft size={16} /> : <Users size={16} />}
          </button>
        )}

        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-black shadow-[inset_0_0_20px_rgba(0,0,0,0.5)]">
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
              gcUsReport={gcUsReport}
              onAnalysisComplete={setAgentAnalysis}
            />
          ) : null}
          <InteractiveSegPanel
            patient={selectedPatient}
            override={maskOverride}
            onOverrideChange={setMaskOverride}
            onImagingAssist={(next) => {
              setImagingAssist(next);
              if (!next) setGcUsReport(null);
            }}
            onSystemReport={setSystemReport}
            onDinoFeatures={setDinoFeature}
            onUnifiedAgentRun={isReaderStudyQueue ? handleReaderUnifiedAgent : undefined}
            unifiedAgentBusy={readerUnifiedAgentBusy}
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

        {isEvidencePanelOpen && (
        <div className="z-40 flex min-h-0 w-[min(420px,34vw)] min-w-[18rem] shrink-0 flex-col border-l border-white/10 bg-panel-bg transition-all duration-300">
          {!selectedPatient ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-xs text-gray-500">
              当前队列没有可用病例；请选择其他队列或检查数据入口。
            </div>
          ) : isReaderStudyQueue ? (
            <div className="flex-1 overflow-y-auto p-4">
              <ReaderEvidencePanel
                result={readerUnifiedAgentResult}
                loading={readerUnifiedAgentBusy}
                zh={language === 'zh'}
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
                publicReaderOnly={readerOnly}
              />
            </div>
          ) : isBenignQueue ? (
            <div className="flex-1 overflow-y-auto p-4">
              <BenignTissueObservationCard patient={selectedPatient} />
            </div>
          ) : (
            <>
              <div className="h-[35%] shrink-0 border-b border-white/10 flex flex-col min-h-0 bg-panel-bg">
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

              <div className="flex-1 flex flex-col min-h-0 bg-bg-dark relative">
                <div className="shrink-0 border-b border-white/10 p-2">
                  <GcUsImagingReportCard
                    patient={selectedPatient}
                    assist={imagingAssist}
                    zh={language === 'zh'}
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
        )}
        <button
          type="button"
          onClick={() => setIsEvidencePanelOpen((value) => !value)}
          className={`absolute top-1/2 z-[200600] -translate-y-1/2 rounded-l-lg border border-white/10 bg-neutral-800/90 p-1.5 text-gray-400 shadow-lg backdrop-blur transition-all hover:border-white/30 hover:bg-neutral-700 hover:text-white ${
            isEvidencePanelOpen ? 'right-[min(420px,34vw)]' : 'right-0'
          }`}
          title={isEvidencePanelOpen
            ? (language === 'zh' ? '收起证据面板' : 'Collapse evidence panel')
            : (language === 'zh' ? '展开证据面板' : 'Expand evidence panel')}
          aria-label={isEvidencePanelOpen
            ? (language === 'zh' ? '收起证据面板' : 'Collapse evidence panel')
            : (language === 'zh' ? '展开证据面板' : 'Expand evidence panel')}
        >
          {isEvidencePanelOpen ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>

        {showStatistics && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-8">
            <div className="bg-[#0b0b0d] border border-white/10 rounded-xl w-full max-w-4xl h-[90vh] flex flex-col shadow-2xl">
              <div className="h-14 shrink-0 border-b border-white/10 flex items-center justify-between px-6">
                <div className="flex items-center gap-3">
                  <BarChart2 size={20} className="text-purple-400" />
                  <span className="text-sm font-bold text-gray-200 uppercase tracking-wider">
                    {language === 'zh' ? '队列统计分析' : 'Cohort Statistics'}
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
      </div>
    </main>
  );
}
