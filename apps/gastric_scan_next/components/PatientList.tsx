"use client";

import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Patient, ReaderStudyMode } from '@/types';
import { Search, Database, ChevronDown, ChevronRight, Folder, FileImage } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import {
  DEFAULT_WORKBENCH_QUEUE,
  isInternalQueue,
  isLocalWallLabQueue,
  isReaderPackageQueue,
  parseWorkbenchQueueId,
} from '@/lib/cohort';
import { canBrowseWorkbenchQueues } from '@/lib/reader/queue-access';
import { QueueTreeSelect } from './QueueTreeSelect';
import toast from 'react-hot-toast';
import { PatientListGroupSkeleton } from './Skeleton';
import type { Language } from '@/lib/i18n';
import { localizeCenterLabel, patientDisplayLabel } from '@/lib/patient-display';
import { isPublicDemoStill } from '@/lib/public-demo-stills';
import { decodePT } from '@/lib/clinical-history-display';
import { formatFiveClass } from '@/lib/reader/five-class';
import { canRevealCaseGold } from '@/lib/reader/gold-reveal-access';

function matchesOpenPatient(patient: Patient, token: string): boolean {
  const wanted = token.trim().toLowerCase();
  if (!wanted) return false;
  const digits = wanted.replace(/^z/i, '').replace(/^0+/, '') || wanted;
  const keys = [patient.id, patient.patient_id, patient.id_short]
    .map((value) => String(value || '').trim().toLowerCase())
    .filter(Boolean);
  return keys.some((key) => {
    if (key === wanted) return true;
    const keyDigits = key.replace(/^z/i, '').replace(/^0+/, '') || key;
    return keyDigits === digits;
  });
}

function groupStageLabel(group: PatientGroup): string {
  if (group.groupType === 'Benign') return '';
  const first = group.items[0];
  if (!first) return '';
  const fromTable = decodePT(first.clinical?.pT);
  if (fromTable) return fromTable;
  if (first.gold_five_class && first.gold_five_class !== 'benign') return first.gold_five_class;
  return '';
}

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
  demo_stills?: Patient[];
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
  authHeaders?: (extra?: HeadersInit) => HeadersInit,
): Promise<PatientPage> {
  const params = new URLSearchParams({
    dataset,
    queue: queueId,
    treatment,
    offset: String(offset),
    limit: String(isReaderPackageQueue(queueId) ? 200 : PATIENT_PAGE_SIZE),
  });
  if (isReaderPackageQueue(queueId) && typeof window !== 'undefined') {
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
  const response = await fetch(`/api/patients?${params.toString()}`, {
    signal,
    headers: authHeaders ? authHeaders() : undefined,
  });
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
  const { dataset, cohortYear, queueId, setQueueId, language, readerOnly, queuesLocked, t } = useSettings();
  const { account, authHeaders } = useDoctorAccount();
  const zh = language !== 'en';
  const canBrowseQueues = !queuesLocked && (!readerOnly || canBrowseWorkbenchQueues(account?.account_id));
  const showGold = canRevealCaseGold(account?.account_id);
  const publicQueueLabel = zh ? '阅片任务, 第一轮' : 'Reader task, Round 1';
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [loadingMore, setLoadingMore] = useState(false);
  const [totalFrames, setTotalFrames] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [progressByCase, setProgressByCase] = useState<Record<string, 'in_progress' | 'completed'>>({});
  const onSelectRef = useRef(onSelect);
  const onPatientsLoadedRef = useRef(onPatientsLoaded);
  const selectedIdRef = useRef(selectedId);
  const hasAutoSelectedRef = useRef(false);
  const pendingOpenIdRef = useRef<string>('');
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
    const onOpenReference = (event: Event) => {
      const detail = (event as CustomEvent<{ queue_id?: string; patient_id?: string }>).detail || {};
      const nextQueue = detail.queue_id ? parseWorkbenchQueueId(detail.queue_id) : '';
      const patientId = String(detail.patient_id || '').trim();
      if (!patientId || !canBrowseQueues) return;
      pendingOpenIdRef.current = patientId;
      if (nextQueue && nextQueue !== queueId) {
        setQueueId(nextQueue);
        return;
      }
      const found = patientsRef.current.find((patient) => matchesOpenPatient(patient, patientId));
      if (found) {
        pendingOpenIdRef.current = '';
        onSelectRef.current(found);
      }
    };
    window.addEventListener('gastric:open-reference-case', onOpenReference);
    return () => window.removeEventListener('gastric:open-reference-case', onOpenReference);
  }, [canBrowseQueues, queueId, setQueueId]);

  useEffect(() => {
    if (!canBrowseQueues && queueId !== DEFAULT_WORKBENCH_QUEUE) {
      setQueueId(DEFAULT_WORKBENCH_QUEUE);
    }
  }, [canBrowseQueues, queueId, setQueueId]);

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
        fetchPatientPage(dataset, queueId, 'surgery', 0, controller.signal, language, authHeaders),
        shouldFetchNac
          ? fetchPatientPage(dataset, queueId, 'nac', 0, controller.signal, language, authHeaders)
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

      const visiblePatients = isLocalWallLabQueue(queueId)
        ? merged.filter((patient) => !isPublicDemoStill(patient))
        : queueId === 'reader:reader_v150' && readerStudyMode
        ? merged.filter((patient) => !isPublicDemoStill(patient) && patient.study_mode === readerStudyMode)
        : merged.filter((patient) => !isPublicDemoStill(patient));
      const currentSelectedId = selectedIdRef.current;
      const requestedCase = typeof window !== 'undefined'
        ? new URLSearchParams(window.location.search).get('case_id')
        : null;
      const pendingOpen = pendingOpenIdRef.current;
      const requested = pendingOpen
        ? visiblePatients.find((patient) => matchesOpenPatient(patient, pendingOpen))
        : requestedCase
          ? visiblePatients.find((patient) => patient.id === requestedCase || patient.patient_id === requestedCase)
          : undefined;
      if (requested && pendingOpen) pendingOpenIdRef.current = '';
      // Keep API presentation order (per-reader shuffle). Do not re-sort by CASE number.
      const orderedVisible = visiblePatients;
      const autoPick = requested
        || orderedVisible.find((patient) => !isPublicDemoStill(patient))
        || orderedVisible[0];

      // Auto-expand the group of the selected patient if exists
      if (currentSelectedId) {
          const p = visiblePatients.find((x: Patient) => x.id === currentSelectedId);
          if (p) {
              const groupKey = getPatientGroupKey(p);
              setExpandedGroups(new Set([groupKey]));
          } else if (autoPick && !hasAutoSelectedRef.current) {
              hasAutoSelectedRef.current = true;
              onSelectRef.current(autoPick);
          }
      } else if (autoPick && !hasAutoSelectedRef.current) {
          hasAutoSelectedRef.current = true;
          onSelectRef.current(autoPick);
          const groupKey = getPatientGroupKey(autoPick);
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
  }, [authHeaders, dataset, language, queueId, readerStudyMode]);

  useEffect(() => {
    hasAutoSelectedRef.current = false;
  }, [dataset, queueId]);

  useEffect(() => {
    const accountId = account?.account_id;
    if (!accountId || !isReaderPackageQueue(queueId)) {
      setProgressByCase({});
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const studyMode = readerStudyMode || 't_staging';
        const response = await fetch(
          `/api/reader/case-state?study_mode=${encodeURIComponent(studyMode)}`,
          { cache: 'no-store', headers: authHeaders() },
        );
        if (!response.ok || cancelled) return;
        const data = await response.json() as {
          states?: Array<{ case_id?: string; progress?: string; completed?: boolean }>;
        };
        if (!Array.isArray(data.states)) return;
        const map: Record<string, 'in_progress' | 'completed'> = {};
        for (const row of data.states) {
          const id = String(row.case_id || '').trim();
          if (!id) continue;
          map[id] = row.completed || row.progress === 'completed' ? 'completed' : 'in_progress';
        }
        if (!cancelled) setProgressByCase(map);
      } catch {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [account?.account_id, authHeaders, queueId, readerStudyMode]);
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
          fetchPatientPage(dataset, queueId, 'surgery', nextOffsetsRef.current.surgery, controller.signal, language, authHeaders),
        ]);
      }
      if (shouldFetchNac && hasMoreRef.current.nac) {
        pageRequests.push([
          'nac',
          fetchPatientPage(dataset, queueId, 'nac', nextOffsetsRef.current.nac, controller.signal, language, authHeaders),
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
  }, [authHeaders, dataset, language, queueId]);

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
    const visiblePatients = isLocalWallLabQueue(queueId)
      ? patients.filter((patient) => !isPublicDemoStill(patient))
      : queueId === 'reader:reader_v150' && readerStudyMode
      ? patients.filter((patient) => !isPublicDemoStill(patient) && patient.study_mode === readerStudyMode)
      : patients.filter((patient) => !isPublicDemoStill(patient));
    
    visiblePatients.forEach(p => {
        const patientId = p.patient_id || p.id_short.split('(')[0].trim();
        const treatmentType = getTreatmentType(p);
        const groupKey = getPatientGroupKey(p);
        if (!groups[groupKey]) {
            groups[groupKey] = {
                key: groupKey,
                baseId: patientId,
                groupType: treatmentType,
                scopeLabel: isPublicDemoStill(p)
                  ? (language === 'en' ? 'Demo stills, not scored' : '演示静图, 不进评分')
                  : (
                    localizeCenterLabel(p.center_label, language)
                    || (p.phase && p.phase !== 'external' ? p.phase : undefined)
                  ),
                items: [],
            };
        }
        groups[groupKey].items.push(p);
    });

    const sortedGroups = Object.values(groups).sort((a, b) => {
        const aDemo = a.items.some((item) => isPublicDemoStill(item));
        const bDemo = b.items.some((item) => isPublicDemoStill(item));
        if (aDemo && !bDemo) return -1;
        if (!aDemo && bDemo) return 1;

        if (isReaderPackageQueue(queueId)) {
          // Preserve API order (per-account shuffle), not CASE-001 numeric order.
          const indexOf = (group: PatientGroup) => {
            for (const item of group.items) {
              const idx = patients.findIndex((row) => row.id === item.id);
              if (idx >= 0) return idx;
            }
            return Number.MAX_SAFE_INTEGER;
          };
          return indexOf(a) - indexOf(b);
        }

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
  }, [patients, searchTerm, queueId, readerStudyMode, language]);

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
      <div className="min-w-0 shrink-0 border-b border-white/5 px-2.5 py-1.5 bg-[#0b0b0d]">
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2 text-[11px] font-bold text-gray-300 uppercase tracking-widest">
            <Database size={12} className="shrink-0 text-blue-500" />
            <span className="truncate">{t.cohort.title}</span>
          </span>
          <span className="shrink-0 text-[9px] font-mono text-gray-500">
            {!canBrowseQueues || isReaderPackageQueue(queueId)
              ? (zh ? '当前队列' : 'Current queue')
              : (zh
                ? `已加载 ${groupedPatients.length} 例 / 共 ${totalFrames} 帧`
                : `Loaded ${groupedPatients.length} cases / ${totalFrames} frames`)}
          </span>
        </div>
        {!canBrowseQueues ? (
          <div className="mt-0.5 truncate text-[8px] font-mono text-cyan-300/70" title={publicQueueLabel}>
            {publicQueueLabel}
          </div>
        ) : (
          <div className="relative mt-1.5 min-w-0">
            <QueueTreeSelect value={queueId} onChange={setQueueId} />
          </div>
        )}
        {isLocalWallLabQueue(queueId) ? (
          <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-2 py-1.5 text-[10px] leading-snug text-amber-100">
            {zh ? '本地壁层实验, 4例: P008 T1, P019 T2, P040 T3, P076 T4' : 'Local wall-lab, 4 cases: P008 T1, P019 T2, P040 T3, P076 T4'}
          </div>
        ) : null}
        {queueId === 'reader:reader_v150' && readerStudyMode && onReaderStudyModeChange ? (
          <div className="mt-2 grid grid-cols-2 gap-1 rounded-md border border-white/10 bg-black/30 p-1">
            <button
              type="button"
              onClick={() => onReaderStudyModeChange('benign_malignancy')}
              className={`rounded px-2 py-1 text-[10px] font-semibold transition max-md:min-h-10 ${readerStudyMode === 'benign_malignancy' ? 'bg-amber-300/15 text-amber-100' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}
            >
              {zh ? '良恶性' : 'Benignity'}
            </button>
            <button
              type="button"
              onClick={() => onReaderStudyModeChange('t_staging')}
              className={`rounded px-2 py-1 text-[10px] font-semibold transition max-md:min-h-10 ${readerStudyMode === 't_staging' ? 'bg-amber-300/15 text-amber-100' : 'text-slate-500 hover:bg-white/5 hover:text-slate-300'}`}
            >
              {zh ? 'T 分期' : 'T staging'}
            </button>
          </div>
        ) : null}
      </div>

      {/* Search */}
      <div className="border-b border-white/5 bg-[#0b0b0d] px-2.5 py-2">
        <div className="relative group">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-600 group-focus-within:text-blue-500 transition-colors" size={12} />
          <input 
            type="text" 
            placeholder={t.cohort.search} 
            className="w-full bg-[#18181b] border border-border-col text-gray-200 text-xs rounded pl-8 pr-2 py-1.5 focus:outline-none focus:border-blue-500/50 focus:bg-[#202024] transition-all placeholder:text-gray-600 font-mono max-md:py-2.5 max-md:text-base"
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
            {visibleGroups.map((group, index) => {
              const groupKey = group.key;
              const isExpanded = expandedGroups.has(groupKey);
              const isGroupSelected = group.items.some(i => i.id === selectedId);
              const isDemoGroup = group.items.some((item) => isPublicDemoStill(item));
              const showDemoHeader = isDemoGroup && (
                index === 0 || !visibleGroups[index - 1].items.some((item) => isPublicDemoStill(item))
              );
              
              return (
                <div key={groupKey} className="bg-[#0b0b0d]">
                  {showDemoHeader ? (
                    <div className="px-3 py-1.5 text-[9px] font-semibold uppercase tracking-widest text-cyan-300/80">
                      {zh ? '演示静图, 不进评分' : 'Demo stills, not scored'}
                    </div>
                  ) : null}
                  {/* Group Header */}
                  <div 
                    onClick={() => toggleGroup(groupKey)}
                    className={`
                        flex items-center justify-between px-3 py-2 cursor-pointer select-none transition-colors max-md:min-h-11 max-md:py-2.5
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
                          {group.scopeLabel && (canBrowseQueues || isDemoGroup) ? (
                            <span className="block truncate text-[8px] font-mono text-gray-600">{group.scopeLabel}</span>
                          ) : null}
                        </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {isDemoGroup ? (
                        <span className="text-[8px] font-bold uppercase text-cyan-300 bg-cyan-500/10 px-1 py-0.5 rounded-sm">
                          {zh ? '演示' : 'DEMO'}
                        </span>
                      ) : null}
                      {canBrowseQueues && queueId !== 'reader:reader_v150' && groupStageLabel(group) ? (
                        <span className="font-mono text-[10px] font-semibold text-amber-200">
                          {groupStageLabel(group)}
                        </span>
                      ) : null}
                      {(() => {
                        const statuses = group.items
                          .map((item) => progressByCase[item.id])
                          .filter(Boolean);
                        if (!statuses.length) {
                          return (
                            <span className="text-[8px] font-bold uppercase px-1 py-0.5 rounded-sm text-slate-400 bg-white/5">
                              {zh ? '未评' : 'Open'}
                            </span>
                          );
                        }
                        const done = statuses.every((s) => s === 'completed');
                        const label = done
                          ? (zh ? '已完成' : 'Done')
                          : (zh ? '半途' : 'Partial');
                        return (
                          <span className={`text-[8px] font-bold uppercase px-1 py-0.5 rounded-sm ${
                            done
                              ? 'text-emerald-300 bg-emerald-500/15'
                              : 'text-amber-200 bg-amber-500/15'
                          }`}>
                            {label}
                          </span>
                        );
                      })()}
                      <span className="font-mono text-[10px] text-gray-500">
                        {group.items.length}
                      </span>
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
                                        flex items-center gap-3 pl-8 pr-3 py-2 cursor-pointer border-l-2 transition-all max-md:min-h-11 max-md:py-2.5
                                        ${isSelected 
                                            ? 'border-blue-500 bg-blue-500/10 text-blue-100' 
                                            : 'border-transparent text-gray-500 hover:text-gray-300 hover:bg-white/5'}
                                    `}
                                >
                                    <FileImage size={10} />
                                    <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
                                        <span className="text-[10px] font-mono truncate">
                                            {patientDisplayLabel(p, language)}
                                        </span>
                                        {showGold && p.gold_five_class ? (
                                          <span className="shrink-0 rounded bg-amber-400/15 px-1 py-0.5 font-mono text-[8px] font-bold text-amber-100">
                                            {formatFiveClass(p.gold_five_class, zh)}
                                          </span>
                                        ) : null}
                                        {(() => {
                                          const status = progressByCase[p.id];
                                          const label = status === 'completed'
                                            ? (zh ? '已完成' : 'Done')
                                            : status === 'in_progress'
                                              ? (zh ? '半途' : 'Partial')
                                              : (zh ? '未评' : 'Open');
                                          return (
                                            <span className={`shrink-0 text-[8px] font-bold uppercase px-1 py-0.5 rounded-sm ${
                                              status === 'completed'
                                                ? 'text-emerald-300 bg-emerald-500/15'
                                                : status === 'in_progress'
                                                  ? 'text-amber-200 bg-amber-500/15'
                                                  : 'text-slate-400 bg-white/5'
                                            }`}>
                                              {label}
                                            </span>
                                          );
                                        })()}
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
