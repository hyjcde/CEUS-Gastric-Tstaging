"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from 'react';
import { Language, dictionary, resolveDictionary } from '@/lib/i18n';
import { convertDomToTraditionalHK, toTraditionalHK } from '@/lib/zh-convert';
import {
  CohortYear,
  DatasetType,
  DEFAULT_DATASET,
  DEFAULT_WORKBENCH_QUEUE,
  isLocalWallLabQueue,
  parseWorkbenchQueueId,
  queueToCohortYear,
  TreatmentType,
  WorkbenchQueueId,
} from '@/lib/cohort';
import { isEvaluationBrowserSession } from '@/lib/reader/evaluation-session';

interface SettingsContextType {
  language: Language;
  readerOnly: boolean;
  /** Evaluation / research session: stay on the reader-study queue only. */
  queuesLocked: boolean;
  setLanguage: (lang: Language) => void;
  dataset: DatasetType;
  setDataset: (ds: DatasetType) => void;
  cohortYear: CohortYear;
  setCohortYear: (year: CohortYear) => void;
  queueId: WorkbenchQueueId;
  setQueueId: (queueId: WorkbenchQueueId) => void;
  treatmentType: TreatmentType;
  setTreatmentType: (type: TreatmentType) => void;
  t: typeof dictionary['en'];
  /** Convert a Simplified UI string to Traditional when locale is zh-HK. */
  tr: (text: string) => string;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);
const READER_ONLY_MODE = process.env.NEXT_PUBLIC_READER_ONLY === '1';

function readStoredDataset(): DatasetType {
  if (typeof window === 'undefined') return DEFAULT_DATASET;
  const stored = window.localStorage.getItem('gastric_dataset');
  if (stored === 'original' || stored === 'cropped') return stored;
  return DEFAULT_DATASET;
}

function readStoredLanguage(): Language {
  if (typeof window === 'undefined') return 'zh';
  const stored = window.localStorage.getItem('gastric_language');
  if (stored === 'en' || stored === 'zh' || stored === 'zh-HK') return stored;
  // Legacy aliases → Hong Kong Traditional
  if (
    stored === 'zh-TW'
    || stored === 'zh_TW'
    || stored === 'zh-Hant'
    || stored === 'tw'
    || stored === 'hk'
  ) {
    return 'zh-HK';
  }
  return 'zh';
}

function readQueueFromSearch(): WorkbenchQueueId | null {
  if (typeof window === 'undefined') return null;
  const raw = new URLSearchParams(window.location.search).get('queue');
  if (!raw) return null;
  const parsed = parseWorkbenchQueueId(raw);
  if (isLocalWallLabQueue(parsed) && READER_ONLY_MODE) return null;
  return parsed;
}

function readStoredQueue(): WorkbenchQueueId {
  if (typeof window === 'undefined') return DEFAULT_WORKBENCH_QUEUE;
  if (isEvaluationBrowserSession()) return DEFAULT_WORKBENCH_QUEUE;
  const fromSearch = readQueueFromSearch();
  if (fromSearch) return fromSearch;
  // Public doctors stay on the reader-study queue until a privileged account switches in the UI.
  if (READER_ONLY_MODE) return DEFAULT_WORKBENCH_QUEUE;
  return parseWorkbenchQueueId(window.localStorage.getItem('gastric_queue'));
}

export const SettingsProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguageState] = useState<Language>('zh');
  const [dataset, setDatasetState] = useState<DatasetType>(DEFAULT_DATASET);

  useEffect(() => {
    const storedLanguage = readStoredLanguage();
    if (storedLanguage === 'zh') return;
    const timer = window.setTimeout(() => setLanguageState(storedLanguage), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('gastric_language', nextLanguage);
    }
  };

  useEffect(() => {
    const storedDataset = readStoredDataset();
    if (storedDataset === DEFAULT_DATASET) return;
    const timer = window.setTimeout(() => setDatasetState(storedDataset), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setDataset = (ds: DatasetType) => {
    setDatasetState(ds);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('gastric_dataset', ds);
    }
  };
  const [cohortYear, setCohortYear] = useState<CohortYear>('reader_v150');
  const [queueId, setQueueIdState] = useState<WorkbenchQueueId>(DEFAULT_WORKBENCH_QUEUE);
  const [treatmentType, setTreatmentType] = useState<TreatmentType>('surgery');
  const [queuesLocked, setQueuesLocked] = useState(false);

  useEffect(() => {
    const locked = isEvaluationBrowserSession();
    setQueuesLocked(locked);
    if (locked) {
      setQueueIdState(DEFAULT_WORKBENCH_QUEUE);
      setCohortYear('reader_v150');
      return;
    }
    const storedQueue = readStoredQueue();
    if (storedQueue === DEFAULT_WORKBENCH_QUEUE) return;
    const timer = window.setTimeout(() => {
      setQueueIdState(storedQueue);
      setCohortYear(queueToCohortYear(storedQueue));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setQueueId = (nextQueueId: WorkbenchQueueId) => {
    if (queuesLocked && nextQueueId !== DEFAULT_WORKBENCH_QUEUE) return;
    setQueueIdState(nextQueueId);
    setCohortYear(queueToCohortYear(nextQueueId));
    if (typeof window !== 'undefined' && !isEvaluationBrowserSession()) {
      window.localStorage.setItem('gastric_queue', nextQueueId);
    }
  };

  const t = useMemo(() => resolveDictionary(language), [language]);
  const tr = useCallback(
    (text: string) => (language === 'zh-HK' ? toTraditionalHK(text) : text),
    [language],
  );

  // Auto-convert inline Simplified UI copy when locale is Hong Kong Traditional.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.lang = language === 'en' ? 'en' : language === 'zh-HK' ? 'zh-HK' : 'zh-CN';
    if (language !== 'zh-HK') return;

    let scheduled = 0;
    const run = () => {
      scheduled = 0;
      convertDomToTraditionalHK(document.body);
    };
    const schedule = () => {
      if (scheduled) return;
      scheduled = window.requestAnimationFrame(run);
    };

    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => {
      observer.disconnect();
      if (scheduled) window.cancelAnimationFrame(scheduled);
    };
  }, [language]);

  return (
    <SettingsContext.Provider value={{
      language,
      readerOnly: READER_ONLY_MODE,
      queuesLocked,
      setLanguage,
      dataset,
      setDataset,
      cohortYear,
      setCohortYear,
      queueId,
      setQueueId,
      treatmentType,
      setTreatmentType,
      t,
      tr,
    }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
