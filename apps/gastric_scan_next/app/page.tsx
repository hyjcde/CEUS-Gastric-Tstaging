"use client";

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Header } from '@/components/Header';
import { PatientList } from '@/components/PatientList';
import { UltrasoundViewer } from '@/components/UltrasoundViewer';
import { ConceptReasoning } from '@/components/ConceptReasoning';
import { DiagnosisPanel } from '@/components/DiagnosisPanel';
import { StatisticsPanel } from '@/components/StatisticsPanel';
import { AgentWorkbenchPanel } from '@/components/AgentWorkbenchPanel';
import { InteractiveSegPanel, type ImagingAssistPayload } from '@/components/InteractiveSegPanel';
import { ReaderAgentResultCard } from '@/components/ReaderAgentResultCard';
import { AssistHub } from '@/components/AssistHub';
import { GcUsImagingReportCard } from '@/components/GcUsImagingReportCard';
import {
  bboxShortAxisRatio,
  buildImagingNarrative,
  computeGcUsTscore,
  estimateAxesMm,
  polygonIrregularity,
} from '@/lib/gc-us-tscore';
// VideoAnalysisUpload 暂隐藏（质量选帧上传入口）
import { ConceptState, DEFAULT_STATE, Patient, AgentAnalysisResponse, MaskBoundaryOverride } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import { ChevronLeft, Users, BarChart2, X } from 'lucide-react';
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
  const { dataset, cohortYear, language } = useSettings();
  const [conceptState, setConceptState] = useState<ConceptState>(DEFAULT_STATE);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isReportExpanded, setIsReportExpanded] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);
  const [allPatients, setAllPatients] = useState<Patient[]>([]);
  const [patientConceptStates, setPatientConceptStates] = useState<Map<string, ConceptState>>(new Map());
  const [agentAnalysis, setAgentAnalysis] = useState<AgentAnalysisResponse | null>(null);
  const [maskOverride, setMaskOverride] = useState<MaskBoundaryOverride | null>(null);
  const [imagingAssist, setImagingAssist] = useState<ImagingAssistPayload | null>(null);
  const [agentFilledCount, setAgentFilledCount] = useState(0);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isDirty, setIsDirty] = useState(false);
  const [fieldSources, setFieldSources] = useState<ConceptFieldSources>(createDefaultFieldSources());

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
    setAgentFilledCount(0);
    setSaveStatus('idle');
    setIsDirty(false);
    setImagingAssist(null);
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
  }, []);

  const siblingImages = useMemo(() => {
    if (!selectedPatient || !allPatients.length) return [];
    const patientId = selectedPatient.patient_id;
    return allPatients.filter((p) => p.patient_id === patientId);
  }, [selectedPatient, allPatients]);

  const imagingNarrative = useMemo(() => {
    if (!selectedPatient || !imagingAssist?.layerResult) return null;
    const clin = selectedPatient.clinical;
    const poly = imagingAssist.lesionPolygon || [];
    const layer = imagingAssist.layerResult;
    const label = layer?.layer?.label || null;
    const tHint = layer?.layer?.tHint || null;
    const occ = layer?.pen?.ratio ?? layer?.analysis?.ratioHint ?? null;
    const irreg = polygonIrregularity(poly);
    const axes =
      poly.length >= 3 && imagingAssist.frameSize
        ? estimateAxesMm(poly, imagingAssist.frameSize)
        : null;
    const lengthCm = clin?.tumorSize?.length ?? (axes ? axes.lengthMm / 10 : null);
    const thicknessCm = clin?.tumorSize?.thickness ?? (axes ? axes.thicknessMm / 10 : null);
    const tscore = computeGcUsTscore({
      lengthCm,
      thicknessCm,
      irregularity: irreg,
      shortAxisRatio: bboxShortAxisRatio(poly),
      layerLabel: label,
      tHint,
      inContact: layer?.inContact ?? null,
      occupationRatio: typeof occ === 'number' ? occ : null,
      serosaDisrupted: /L5|浆膜|T4|T3–T4|T3-T4/i.test(`${label || ''} ${tHint || ''}`),
    });
    return buildImagingNarrative({
      location: clin?.location || null,
      lengthMm: clin?.tumorSize?.length ? clin.tumorSize.length * 10 : axes?.lengthMm ?? null,
      thicknessMm: clin?.tumorSize?.thickness ? clin.tumorSize.thickness * 10 : axes?.thicknessMm ?? null,
      irregularity: irreg,
      inContact: layer?.inContact ?? null,
      layerLabel: label,
      tHint,
      occupationRatio: typeof occ === 'number' ? occ : null,
      serosaDisrupted: /L5|浆膜|T4|T3–T4|T3-T4/i.test(`${label || ''} ${tHint || ''}`),
      tscore,
      zh: language === 'zh',
    });
  }, [selectedPatient, imagingAssist, language]);

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
    <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200 overflow-hidden selection:bg-blue-500/30">
      <div className="h-16 shrink-0 border-b border-white/10 z-50">
        <Header
          onShowStatistics={() => setShowStatistics(true)}
          selectedPatient={selectedPatient}
        />
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        <div
          className={`shrink-0 border-r border-white/10 bg-[#0b0b0d] flex flex-col min-h-0 z-40 transition-all duration-300 ease-in-out ${
            isSidebarOpen ? 'w-72 translate-x-0' : 'w-0 -translate-x-full opacity-0 border-none'
          }`}
        >
          <div className="w-72 h-full">
            <PatientList
              key={`${dataset}-${cohortYear}`}
              onSelect={setSelectedPatient}
              selectedId={selectedPatient?.id || null}
              onPatientsLoaded={handlePatientsLoaded}
            />
          </div>
        </div>

        {!isReportExpanded && (
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className={`absolute top-1/2 -translate-y-1/2 z-40 bg-neutral-800/80 backdrop-blur border border-white/10 text-gray-400 hover:text-white p-1.5 rounded-r-lg shadow-lg transition-all duration-300 hover:bg-blue-600 hover:border-blue-500 ${
              isSidebarOpen ? 'left-72' : 'left-0'
            }`}
            title={isSidebarOpen ? 'Collapse Patient List' : 'Expand Patient List'}
          >
            {isSidebarOpen ? <ChevronLeft size={16} /> : <Users size={16} />}
          </button>
        )}

        <div className="flex-1 flex flex-col min-h-0 bg-black relative min-w-0 shadow-[inset_0_0_20px_rgba(0,0,0,0.5)]">
          {/* 视频综合分析入口（上传选帧）暂隐藏；病例视频 SAM 走 InteractiveSegPanel「视频 SAM」 */}
          {/* <VideoAnalysisUpload onAnalysisComplete={setAgentAnalysis} /> */}
          <UltrasoundViewer
            key={`${selectedPatient?.id}-${dataset}`}
            patient={selectedPatient}
            siblingImages={siblingImages}
            onSelectSibling={setSelectedPatient}
            onExplainableComplete={handleExplainableComplete}
          />
          <AssistHub patient={selectedPatient} />
          <AgentWorkbenchPanel
            patient={selectedPatient}
            maskOverride={maskOverride}
            onAnalysisComplete={setAgentAnalysis}
          />
          <InteractiveSegPanel
            patient={selectedPatient}
            override={maskOverride}
            onOverrideChange={setMaskOverride}
            onImagingAssist={setImagingAssist}
          />
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
        </div>

        <div className="w-[420px] shrink-0 border-l border-white/10 bg-panel-bg flex flex-col min-h-0 z-40 transition-all duration-300">
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
              />
            </div>
            <DiagnosisPanel
              state={conceptState}
              patient={selectedPatient}
              agentAnalysis={agentAnalysis}
              imagingNarrative={imagingNarrative}
              onExpandedChange={setIsReportExpanded}
            />
          </div>
        </div>

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
