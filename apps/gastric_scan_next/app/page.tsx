"use client";

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Header } from '@/components/Header';
import { PatientList } from '@/components/PatientList';
import { UltrasoundViewer } from '@/components/UltrasoundViewer';
import { ConceptReasoning } from '@/components/ConceptReasoning';
import { DiagnosisPanel } from '@/components/DiagnosisPanel';
import { StatisticsPanel } from '@/components/StatisticsPanel';
import { AgentWorkbenchPanel } from '@/components/AgentWorkbenchPanel';
import { ConceptState, DEFAULT_STATE, Patient, AgentAnalysisResponse } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import { ChevronLeft, Users, BarChart2, X } from 'lucide-react';
import { getConceptStateFromPatient, countPopulatedConceptFields } from '@/lib/patient-utils';
import {
  mergeAgentIntoConceptState,
  mergeExplainableIntoConceptState,
  countAgentFilledFields,
  ExplainableAnalysisResult,
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
  const [agentFilledCount, setAgentFilledCount] = useState(0);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [isDirty, setIsDirty] = useState(false);

  const clinicalBaselinesRef = useRef<Map<string, ConceptState>>(new Map());
  const userEditedRef = useRef<Set<string>>(new Set());
  const lastMergedAgentSessionRef = useRef<string | null>(null);
  const lastMergedExplainableRef = useRef<string | null>(null);
  const patientConceptStatesRef = useRef<Map<string, ConceptState>>(new Map());
  const conceptLoadTokenRef = useRef(0);

  useEffect(() => {
    patientConceptStatesRef.current = patientConceptStates;
  }, [patientConceptStates]);

  useEffect(() => {
    setAgentAnalysis(null);
    setAgentFilledCount(0);
    setSaveStatus('idle');
    setIsDirty(false);
    lastMergedAgentSessionRef.current = null;
    lastMergedExplainableRef.current = null;
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
  }, []);

  const siblingImages = useMemo(() => {
    if (!selectedPatient || !allPatients.length) return [];
    const patientId = selectedPatient.patient_id;
    return allPatients.filter((p) => p.patient_id === patientId);
  }, [selectedPatient, allPatients]);

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
        body: JSON.stringify({ patientId: selectedPatient.id, state: conceptState }),
      });
      if (!response.ok) throw new Error('Save failed');
      setSaveStatus('saved');
      setIsDirty(false);
    } catch {
      setSaveStatus('error');
    }
  }, [selectedPatient, conceptState]);

  const handleResetConceptState = useCallback(async () => {
    if (!selectedPatient) return;
    const baseline = getConceptStateFromPatient(selectedPatient);
    clinicalBaselinesRef.current.set(selectedPatient.id, baseline);
    userEditedRef.current.delete(selectedPatient.id);
    applyConceptState(selectedPatient.id, baseline, false);
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
  }, [selectedPatient, applyConceptState]);

  useEffect(() => {
    if (!selectedPatient) return;
    const patient: Patient = selectedPatient;
    const patientId = patient.id;
    const loadToken = ++conceptLoadTokenRef.current;

    async function loadPatientConceptState() {
      const baseline = getConceptStateFromPatient(patient);
      clinicalBaselinesRef.current.set(patientId, baseline);

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
        applyConceptState(patientId, loaded, Boolean(data.state));
        setIsDirty(Boolean(data.state));
      } catch {
        if (loadToken !== conceptLoadTokenRef.current) return;
        applyConceptState(patientId, baseline, false);
      }
    }

    loadPatientConceptState();
  }, [selectedPatient?.id, applyConceptState]);

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
        <Header onShowStatistics={() => setShowStatistics(true)} />
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
          <UltrasoundViewer
            key={`${selectedPatient?.id}-${dataset}`}
            patient={selectedPatient}
            siblingImages={siblingImages}
            onSelectSibling={setSelectedPatient}
            onExplainableComplete={handleExplainableComplete}
          />
          <AgentWorkbenchPanel patient={selectedPatient} onAnalysisComplete={setAgentAnalysis} />
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
              hasClinicalData={Boolean(selectedPatient?.clinical)}
              isDirty={isDirty}
              saveStatus={saveStatus}
            />
          </div>

          <div className="flex-1 flex flex-col min-h-0 bg-bg-dark relative">
            <DiagnosisPanel
              state={conceptState}
              patient={selectedPatient}
              agentAnalysis={agentAnalysis}
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
