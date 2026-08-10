"use client";

import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Patient, ReaderStudyMode } from '@/types';
import { Search, Database, ChevronDown, ChevronRight, Folder, FileImage } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import { getQueueDisplayLabel, isInternalQueue } from '@/lib/cohort';
import { QueueTreeSelect } from './QueueTreeSelect';
import toast from 'react-hot-toast';
import { PatientListGroupSkeleton } from './Skeleton';
import type { Language } from '@/lib/i18n';

interface PatientListProps {
  onSelect: (patient: Patient) => void;
  selectedId: string | null;
  onPatientsLoaded?: (patients: Patient[]) => void;
  readerStudyMode?: ReaderStudyMode;
  onReaderStudyModeChange?: (mode: ReaderStudyMode) => void;
}

// Helper type for grouped patients
interface PatientGroup {
  key: string;
  baseId: string; // e.g., 1MC_1424711
  groupType: string; // Chemo/Surgery
  scopeLabel?: string;
  items: Patient[];
}

type TreatmentKey = 'surgery' | 'nac';

interface PatientPage {
  items: Patient[];
  total: number;
  offset: number;
  limit: number;
  hasMore: boolean;
  has_more?: boolean;
}

const PATIENT_PAGE_SIZE = 80;

function getTreatmentType(patient: Patient): 'NAC' | 'Benign' | 'Surgery' {
  if (patient.group === 'Benign') return 'Benign';
  return patient.group === 'NAC' || patient.id.startsWith('NAC_') ? 'NAC' : 'Surgery';
}

function getPatientGroupKey(patient: Patient): string {
  const patientId = patient.patient_id || patient.id_short.split('(')[0].trim();
  const scope = patient.center_id || patient.phase || patient.queue_id || 'queue';
  return `${scope}::${patientId}::${getTreatmentType(patient)}`;
}

function emptyPatientPage(offset = 0): PatientPage {
  return {
    items: [],
    total: 0,
    offset,
    limit: PATIENT_PAGE_SIZE,
    hasMore: false,
  };
}

function mergePatients(current: Patient[], additions: Patient[]): Patient[] {
  const seen = new Set(current.map((patient) => patient.id));
  const next = [...current];
  for (const patient of additions) {
    if (seen.has(patient.id)) continue;
    seen.add(patient.id);
    next.push(patient);
  }
  return next;
}

async function fetchPatientPage(
  dataset: string,
  queueId: string,
  treatment: TreatmentKey,
  offset: number,
  signal: AbortSignal,
  language: Language,
): Promise<PatientPage> {
  const params = new URLSearchParams({
    dataset,
    queue: queueId,
    treatment,
    offset: String(offset),
    limit: String(PATIENT_PAGE_SIZE),
  });
  if (queueId === 'reader:reader_v150' && typeof window !== 'undefined') {
    const searchParams = new URLSearchParams(window.location.search);
    const environment = searchParams.get('environment') || searchParams.get('env') || (
      searchParams.get('round') === 'qa' ? 'qa' : 'staging'
    );
    params.set('environment', environment);
    if (environment !== 'research') {
      const readerId = searchParams.get('reader_id');
      if (readerId) params.set('reader_id', readerId);
    }
  }
  const response = await fetch(`/api/patients?${params.toString()}`, { signal });
  if (!response.ok) {
    throw new Error(language === 'en'
      ? `${treatment === 'nac' ? 'NAC' : 'Surgery'} queue request failed (HTTP ${response.status})`
      : `${treatment === 'nac' ? 'NAC' : 'surgery'} 队列请求失败（HTTP ${response.status}）`);
  }
  const data = await response.json() as Partial<PatientPage> | Patient[];
  if (Array.isArray(data)) {
    return {
      items: data,
      total: data.length,
      offset,
      limit: PATIENT_PAGE_SIZE,
      hasMore: false,
    };
  }
  if (!Array.isArray(data.items)) {
    throw new Error(language === 'en'
      ? `${treatment === 'nac' ? 'NAC' : 'Surgery'} queue returned an invalid format`
      : `${treatment === 'nac' ? 'NAC' : 'surgery'} 队列返回格式错误`);
  }
  return {
    items: data.items,
    total: typeof data.total === 'number' ? data.total : data.items.length,
    offset: typeof data.offset === 'number' ? data.offset : offset,
    limit: typeof data.limit === 'number' ? data.limit : PATIENT_PAGE_SIZE,
    hasMore: Boolean(data.has_more),
  };
}

export const PatientList: React.FC<PatientListProps> = ({ onSelect, selectedId, onPatientsLoaded, readerStudyMode, onReaderStudyModeChange }) => {
  const { dataset, cohortYear, queueId, setQueueId, language, readerOnly, t } = useSettings();
  const zh = language !== 'en';
  const publicQueueLabel = zh ? '阅片任务 · 第一轮' : 'Reader task · Round 1';
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [loadingMore, setLoadingMore] = useState(false);
  const [totalFrames, setTotalFrames] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const onSelectRef = useRef(onSelect);
  const onPatientsLoadedRef = useRef(onPatientsLoaded);
  const selectedIdRef = useRef(selectedId);
  const hasAutoSelectedRef = useRef(false);
  const patientsRef = useRef<Patient[]>([]);
  const nextOffsetsRef = useRef<Record<TreatmentKey, number>>({ surgery: 0, nac: 0 });
  const hasMoreRef = useRef<Record<TreatmentKey, boolean>>({ surgery: true, nac: false });
  const loadingMoreRef = useRef(false);
  const loadMoreControllerRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    onPatientsLoadedRef.current = onPatientsLoaded;
  }, [onPatientsLoaded]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();
    const shouldFetchNac = isInternalQueue(queueId);

    const loadPatients = async () => {
      setLoading(true);
      setLoadingMore(false);
      setPatients([]);
      patientsRef.current = [];
      nextOffsetsRef.current = { surgery: 0, nac: 0 };
      hasMoreRef.current = { surgery: true, nac: shouldFetchNac };
      setTotalFrames(0);
      setHasMore(false);

      const [surgeryData, nacData] = await Promise.all([
        fetchPatientPage(dataset, queueId, 'surgery', 0, controller.signal, language),
        shouldFetchNac
          ? fetchPatientPage(dataset, queueId, 'nac', 0, controller.signal, language)
          : Promise.resolve(emptyPatientPage(0)),
      ]);

      if (!isMounted) return;

      const merged = mergePatients([], [...surgeryData.items, ...nacData.items]);
      patientsRef.current = merged;
      nextOffsetsRef.current = {
        surgery: surgeryData.offset + surgeryData.limit,
        nac: nacData.offset + nacData.limit,
      };
      hasMoreRef.current = {
        surgery: surgeryData.hasMore,
        nac: nacData.hasMore,
      };

      setPatients(merged);
      setTotalFrames(surgeryData.total + nacData.total);
      setHasMore(surgeryData.hasMore || nacData.hasMore);
      setLoading(false);
      onPatientsLoadedRef.current?.(merged);

      const visiblePatients = queueId === 'reader:reader_v150' && readerStudyMode
        ? merged.filter((patient) => patient.study_mode === readerStudyMode)
        : merged;
      const currentSelectedId = selectedIdRef.current;

      // Auto-expand the group of the selected patient if exists
      if (currentSelectedId) {
          const p = visiblePatients.find((x: Patient) => x.id === currentSelectedId);
          if (p) {
              const groupKey = getPatientGroupKey(p);
              setExpandedGroups(new Set([groupKey]));
          } else if (visiblePatients.length > 0 && !hasAutoSelectedRef.current) {
              hasAutoSelectedRef.current = true;
              onSelectRef.current(visiblePatients[0]);
          }
      } else if (visiblePatients.length > 0 && !hasAutoSelectedRef.current) {
          hasAutoSelectedRef.current = true;
          onSelectRef.current(visiblePatients[0]);
          const groupKey = getPatientGroupKey(visiblePatients[0]);
          setExpandedGroups(new Set([groupKey]));
      }
    };

    loadPatients().catch(error => {
      if (!isMounted || (error instanceof DOMException && error.name === 'AbortError')) return;
      console.error('Failed to load patients', error);
      setLoading(false);
      toast.error(error instanceof Error ? error.message : (language === 'en' ? 'Failed to load the case queue' : '病例队列加载失败'));
    });

    return () => {
      isMounted = false;
      controller.abort();
      loadMoreControllerRef.current?.abort();
    };
  }, [dataset, language, queueId, readerStudyMode]);

  useEffect(() => {
    hasAutoSelectedRef.current = false;
  }, [dataset, queueId]);

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || (!hasMoreRef.current.surgery && !hasMoreRef.current.nac)) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const controller = new AbortController();
    loadMoreControllerRef.current = controller;
    try {
      const shouldFetchNac = isInternalQueue(queueId);
      const pageRequests: Array<[TreatmentKey, Promise<PatientPage>]> = [];
      if (hasMoreRef.current.surgery) {
        pageRequests.push([
          'surgery',
          fetchPatientPage(dataset, queueId, 'surgery', nextOffsetsRef.current.surgery, controller.signal, language),
        ]);
      }
      if (shouldFetchNac && hasMoreRef.current.nac) {
        pageRequests.push([
          'nac',
          fetchPatientPage(dataset, queueId, 'nac', nextOffsetsRef.current.nac, controller.signal, language),
        ]);
      }
      const pages = await Promise.all(pageRequests.map(async ([treatment, request]) => (
        [treatment, await request] as const
      )));

      const additions = pages.flatMap(([, page]) => page.items);
      for (const [treatment, page] of pages) {
        nextOffsetsRef.current[treatment] = page.offset + page.limit;
        hasMoreRef.current[treatment] = page.hasMore;
      }
      const merged = mergePatients(patientsRef.current, additions);
      patientsRef.current = merged;
      setPatients(merged);
      setHasMore(hasMoreRef.current.surgery || hasMoreRef.current.nac);
      onPatientsLoadedRef.current?.(merged);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        console.error('Failed to load more patients', error);
        toast.error(error instanceof Error ? error.message : (language === 'en' ? 'Failed to load more cases' : '更多病例加载失败'));
      }
    } finally {
      loadingMoreRef.current = false;
      loadMoreControllerRef.current = null;
      setLoadingMore(false);
    }
  }, [dataset, language, queueId]);

  useEffect(() => {
    loadMoreRef.current = loadMore;
  }, [loadMore]);

  const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const remaining = target.scrollHeight - target.scrollTop - target.clientHeight;
    if (remaining < 240) void loadMoreRef.current();
  }, []);

  // Grouping Logic - Group by patient_id and treatment type
  const groupedPatients = useMemo(() => {
    const groups: Record<string, PatientGroup> = {};
    const visiblePatients = queueId === 'reader:reader_v150' && readerStudyMode
      ? patients.filter((patient) => patient.study_mode === readerStudyMode)
      : patients;
    
    visiblePatients.forEach(p => {
        const patientId = p.patient_id || p.id_short.split('(')[0].trim();
        const treatmentType = getTreatmentType(p);
        const groupKey = getPatientGroupKey(p);
        if (!groups[groupKey]) {
            groups[groupKey] = {
                key: groupKey,
                baseId: patientId,
                groupType: treatmentType,
                scopeLabel: p.center_label || (p.phase && p.phase !== 'external' ? p.phase : undefined),
                items: [],
            };
        }
        groups[groupKey].items.push(p);
    });

    // Sort groups: first by clinical data presence (any item in group has clinical), then by patient_id, then by treatment type
    const sortedGroups = Object.values(groups).sort((a, b) => {
        // 1. Clinical data presence
        const hasClinicalA = a.items.some(i => i.clinical);
        const hasClinicalB = b.items.some(i => i.clinical);

        if (hasClinicalA && !hasClinicalB) return -1;
        if (!hasClinicalA && hasClinicalB) return 1;

        const aPatientId = a.baseId;
        const bPatientId = b.baseId;
        
        const aNum = parseInt(aPatientId) || 0;
        const bNum = parseInt(bPatientId) || 0;
        
        // 2. Sort by patient ID
        if (aNum > 0 && bNum > 0) {
            if (aNum !== bNum) {
                return aNum - bNum;
            }
        } else if (aNum === 0 && bNum === 0) {
            const strCompare = aPatientId.localeCompare(bPatientId);
            if (strCompare !== 0) {
                return strCompare;
            }
        } else {
            return aNum - bNum;
        }
        
        // 3. If same patient ID, sort by treatment type: Surgery before NAC
        if (a.groupType === 'Surgery' && b.groupType === 'NAC') {
            return -1;
        }
        if (a.groupType === 'NAC' && b.groupType === 'Surgery') {
            return 1;
        }
        return 0;
    });

    // Filter groups based on search
    const term = searchTerm.toLowerCase();
    const result = sortedGroups.filter(g => 
        g.baseId.toLowerCase().includes(term) || 
        g.scopeLabel?.toLowerCase().includes(term) ||
        g.items.some(i => i.id.toLowerCase().includes(term) || i.patient_id?.toLowerCase().includes(term))
    );

    return result;
  }, [patients, searchTerm, queueId, readerStudyMode]);

  const visibleGroups = groupedPatients;

  const toggleGroup = useCallback((groupKey: string) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupKey)) {
        newSet.delete(groupKey);
      } else {
        newSet.add(groupKey);
      }
      return newSet;
    });
  }, []);

  return (
    <div className="flex flex-col h-full w-full bg-[#0b0b0d]">
      {/* Sidebar Header */}
      <div className="min-h-12 shrink-0 border-b border-white/5 px-3 py-1.5 bg-[#0b0b0d]">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-[11px] font-bold text-gray-300 uppercase tracking-widest">
            <Database size={12} className="text-blue-500" />
            {t.cohort.title}
          </span>
          <span className="text-[9px] font-mono text-gray-500">
            {readerOnly
              ? (zh ? '当前队列' : 'Current queue')
              : (zh ? `${groupedPatients.length}组 / ${totalFrames}帧` : `${groupedPatients.length} groups / ${totalFrames} frames`)}
          </span>
        </div>
        <div className="mt-0.5 truncate text-[8px] font-mono text-cyan-300/70" title={readerOnly ? publicQueueLabel : getQueueDisplayLabel(queueId, language)}>
          {readerOnly ? publicQueueLabel : getQueueDisplayLabel(queueId, language)}
        </div>
        {!readerOnly ? (
          <div className="relative z-[60] mt-1.5">
            <QueueTreeSelect value={queueId} onChange={setQueueId} />
          </div>
        ) : null}
        {queueId === 'reader:reader_v150' && readerStudyMode && onReaderStudyModeChange ? (
          <div className="mt-2 grid grid-cols-2 gap-1 rounded-md border border-white/10 bg-black/30 p-1">
            <button
              type="button"
              onClick={() => onReaderStudyModeChange('benign_malignancy')}
              className={`rounded px-2 py-1 text-[10px] font-semibold transition ${readerStudyMode === 'benign_malignancy' ? 'bg-amber-300/15 text-amber-100' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}
            >
              {zh ? '良恶性' : 'Benignity'}
            </button>
            <button
              type="button"
              onClick={() => onReaderStudyModeChange('t_staging')}
              className={`rounded px-2 py-1 text-[10px] font-semibold transition ${readerStudyMode === 't_staging' ? 'bg-amber-300/15 text-amber-100' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}
            >
              {zh ? 'T 分期' : 'T staging'}
            </button>
          </div>
        ) : null}
      </div>

      {/* Search */}
      <div className="p-3 border-b border-white/5 bg-[#0b0b0d]">
        <div className="relative group">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-600 group-focus-within:text-blue-500 transition-colors" size={12} />
          <input 
            type="text" 
            placeholder={t.cohort.search} 
            className="w-full bg-[#18181b] border border-border-col text-gray-200 text-xs rounded pl-8 pr-2 py-1.5 focus:outline-none focus:border-blue-500/50 focus:bg-[#202024] transition-all placeholder:text-gray-600 font-mono"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Grouped List */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto min-h-0 scrollbar-thin scrollbar-thumb-neutral-700 scrollbar-track-transparent pb-4"
      >
        {loading ? (
          <div className="divide-y divide-white/5">
            {[...Array(5)].map((_, i) => (
              <PatientListGroupSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {visibleGroups.map(group => {
              const groupKey = group.key;
              const isExpanded = expandedGroups.has(groupKey);
              const isGroupSelected = group.items.some(i => i.id === selectedId);
              
              return (
                <div key={groupKey} className="bg-[#0b0b0d]">
                  {/* Group Header */}
                  <div 
                    onClick={() => toggleGroup(groupKey)}
                    className={`
                        flex items-center justify-between px-3 py-2 cursor-pointer select-none transition-colors
                        ${isGroupSelected ? 'bg-blue-500/5' : 'hover:bg-white/5'}
                    `}
                  >
                    <div className="flex min-w-0 items-center gap-2 overflow-hidden">
                        {isExpanded ? <ChevronDown size={12} className="text-gray-500" /> : <ChevronRight size={12} className="text-gray-500" />}
                        <Folder size={12} className={isGroupSelected ? "text-blue-400" : "text-gray-600"} />
                        <div className="min-w-0">
                          <span className={`block truncate text-[11px] font-mono ${isGroupSelected ? 'text-gray-200' : 'text-gray-400'}`}>
                              {cohortYear === 'gist' ? `Patient ${group.baseId}` : group.baseId}
                          </span>
                          {group.scopeLabel && !readerOnly ? (
                            <span className="block truncate text-[8px] font-mono text-gray-600">{group.scopeLabel}</span>
                          ) : null}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {!readerOnly ? (
                        <>
                        <span className={`
                            text-[8px] font-bold px-1 py-0.5 rounded-sm uppercase
                            ${group.groupType === 'NAC'
                              ? 'text-pink-500 bg-pink-500/10'
                              : group.groupType === 'Benign'
                                ? 'text-emerald-400 bg-emerald-500/10'
                                : 'text-indigo-500 bg-indigo-500/10'}
                        `}>
                            {group.groupType === 'NAC' ? 'NAC' : group.groupType === 'Benign' ? 'BENIGN' : 'SURG'}
                        </span>
                        {group.items.some(p => p.clinical) && (
                            <span className="text-[8px] bg-blue-500/20 text-blue-400 px-1 py-0.5 rounded border border-blue-500/30" title="Has clinical data">
                                CLIN
                            </span>
                        )}
                        <span className="text-[9px] text-gray-600 bg-white/5 px-1.5 rounded-full">
                            {group.items.length}
                        </span>
                        </>
                      ) : null}
                    </div>
                  </div>

                  {/* Group Items (Images) */}
                  {isExpanded && (
                    <div className="bg-[#08080a] shadow-inner">
                        {group.items.map((p, index) => {
                            const isSelected = selectedId === p.id;
                            // Use a more unique key: groupKey + index + id to ensure uniqueness
                            const uniqueKey = `${groupKey}_${index}_${p.id}`;
                            return (
                                <div 
                                    key={uniqueKey}
                                    onClick={() => onSelect(p)}
                                    className={`
                                        flex items-center gap-3 pl-8 pr-3 py-2 cursor-pointer border-l-2 transition-all
                                        ${isSelected 
                                            ? 'border-blue-500 bg-blue-500/10 text-blue-100' 
                                            : 'border-transparent text-gray-500 hover:text-gray-300 hover:bg-white/5'}
                                    `}
                                >
                                    <FileImage size={10} />
                                    <div className="flex flex-col min-w-0 flex-1">
                                        <span className="text-[10px] font-mono truncate">
                                            {p.id_short}
                                        </span>
                                        {p.clinical && (
                                            <div className="flex items-center gap-2 mt-0.5">
                                                {p.clinical.biomarkers.cea_positive && (
                                                    <span className="text-[8px] bg-red-500/20 text-red-400 px-1 rounded border border-red-500/30">CEA+</span>
                                                )}
                                                {p.clinical.biomarkers.ca199_positive && (
                                                    <span className="text-[8px] bg-red-500/20 text-red-400 px-1 rounded border border-red-500/30">CA199+</span>
                                                )}
                                                <span className="text-[8px] bg-white/10 text-gray-300 px-1 rounded border border-white/10">
                                                    F{p.frame_count}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                  )}
                </div>
              );
            })}
            {!loading && hasMore ? (
              <div className="flex flex-col items-center gap-1.5 px-3 py-4">
                <button
                  type="button"
                  onClick={() => void loadMoreRef.current()}
                  disabled={loadingMore}
                  className="rounded border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[10px] font-semibold text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {loadingMore
                    ? (zh ? '正在加载下一页...' : 'Loading next page...')
                    : (zh ? `继续加载 ${PATIENT_PAGE_SIZE} 帧` : `Load next ${PATIENT_PAGE_SIZE} frames`)}
                </button>
                <span className="text-[9px] font-mono text-gray-600">
                  {zh
                    ? `已加载 ${patients.length} / ${totalFrames} 帧`
                    : `${patients.length} / ${totalFrames} frames loaded`}
                </span>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
};
