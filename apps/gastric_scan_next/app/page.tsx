"use client";

import React, { useState, useMemo, useCallback } from 'react';
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

  // 切换患者时清空 Agent 分析结果
  React.useEffect(() => {
    setAgentAnalysis(null);
  }, [selectedPatient?.id]);

  const conceptPopulatedCount = useMemo(
    () => countPopulatedConceptFields(conceptState),
    [conceptState],
  );

  const siblingImages = useMemo(() => {
    if (!selectedPatient || !allPatients.length) return [];
    const patientId = selectedPatient.patient_id;
    return allPatients.filter((p) => p.patient_id === patientId);
  }, [selectedPatient, allPatients]);

  const handleStateChange = useCallback((key: keyof ConceptState, value: number) => {
    setConceptState(prev => {
      const newState = {
        ...prev,
        [key]: value
      };
      // 更新当前患者的概念状态
      if (selectedPatient) {
        setPatientConceptStates(prevMap => {
          const newMap = new Map(prevMap);
          newMap.set(selectedPatient.id, newState);
          return newMap;
        });
      }
      return newState;
    });
  }, [selectedPatient]);

  // 当选择新患者时，加载或使用默认状态
  React.useEffect(() => {
    if (selectedPatient) {
      const savedState = patientConceptStates.get(selectedPatient.id);
      if (savedState) {
        setConceptState(savedState);
      } else {
        // 尝试从患者临床数据中加载
        const fromPatient = getConceptStateFromPatient(selectedPatient);
        setConceptState(fromPatient);
        // 保存到状态中
        setPatientConceptStates(prevMap => {
          const newMap = new Map(prevMap);
          newMap.set(selectedPatient.id, fromPatient);
          return newMap;
        });
      }
    }
  }, [selectedPatient, patientConceptStates]);

  return (
    <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200 overflow-hidden selection:bg-blue-500/30">
      {/* Header: Fixed Height */}
      <div className="h-16 shrink-0 border-b border-white/10 z-50">
        <Header onShowStatistics={() => setShowStatistics(true)} />
      </div>

      {/* Main Layout: Flex Row */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        
        {/* Left: Patient List (Collapsible) */}
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
            onPatientsLoaded={setAllPatients}
          />
          </div>
        </div>

        {/* Sidebar Toggle Button (Floating) - Hidden when report is expanded */}
        {!isReportExpanded && (
          <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className={`absolute top-1/2 -translate-y-1/2 z-40 bg-neutral-800/80 backdrop-blur border border-white/10 text-gray-400 hover:text-white p-1.5 rounded-r-lg shadow-lg transition-all duration-300 hover:bg-blue-600 hover:border-blue-500 ${
                  isSidebarOpen ? 'left-72' : 'left-0'
              }`}
              title={isSidebarOpen ? "Collapse Patient List" : "Expand Patient List"}
          >
              {isSidebarOpen ? <ChevronLeft size={16} /> : <Users size={16} />}
          </button>
        )}

        {/* Middle: Viewer (Flexible, Darkest Background) */}
        <div className="flex-1 flex flex-col min-h-0 bg-black relative min-w-0 shadow-[inset_0_0_20px_rgba(0,0,0,0.5)]">
          <UltrasoundViewer
            key={`${selectedPatient?.id}-${dataset}`}
            patient={selectedPatient}
            siblingImages={siblingImages}
            onSelectSibling={setSelectedPatient}
          />
          <AgentWorkbenchPanel patient={selectedPatient} onAnalysisComplete={setAgentAnalysis} />
        </div>

        {/* Right: Analysis (Fixed Width, Split Vertically) */}
        <div className="w-[420px] shrink-0 border-l border-white/10 bg-panel-bg flex flex-col min-h-0 z-40 transition-all duration-300">
          
          {/* Top Right: Reasoning (35% Height) - Reduced from 45% to give more space to diagnosis */}
          <div className="h-[35%] shrink-0 border-b border-white/10 flex flex-col min-h-0 bg-panel-bg">
             <ConceptReasoning
               state={conceptState}
               onChange={handleStateChange}
               onReset={() => setConceptState(getConceptStateFromPatient(selectedPatient))}
               populatedCount={conceptPopulatedCount}
               hasClinicalData={Boolean(selectedPatient?.clinical)}
             />
          </div>
          
          {/* Bottom Right: Report (Rest Height - 65%) */}
          <div className="flex-1 flex flex-col min-h-0 bg-bg-dark relative">
             <DiagnosisPanel state={conceptState} patient={selectedPatient} agentAnalysis={agentAnalysis} onExpandedChange={setIsReportExpanded} />
          </div>
          
        </div>

        {/* Statistics Panel Modal */}
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
