"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Language, dictionary } from '@/lib/i18n';
import {
  CohortYear,
  DatasetType,
  DEFAULT_DATASET,
  DEFAULT_WORKBENCH_QUEUE,
  parseWorkbenchQueueId,
  queueToCohortYear,
  TreatmentType,
  WorkbenchQueueId,
} from '@/lib/cohort';

interface SettingsContextType {
  language: Language;
  readerOnly: boolean;
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
  return stored === 'en' || stored === 'zh' ? stored : 'zh';
}

function readStoredQueue(): WorkbenchQueueId {
  if (READER_ONLY_MODE) return DEFAULT_WORKBENCH_QUEUE;
  if (typeof window === 'undefined') return DEFAULT_WORKBENCH_QUEUE;
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
  const [treatmentType, setTreatmentType] = useState<TreatmentType>('surgery'); // Default to surgery (can be 'surgery' or 'nac')

  useEffect(() => {
    const storedQueue = readStoredQueue();
    if (storedQueue === DEFAULT_WORKBENCH_QUEUE) return;
    const timer = window.setTimeout(() => {
      setQueueIdState(storedQueue);
      setCohortYear(queueToCohortYear(storedQueue));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setQueueId = (nextQueueId: WorkbenchQueueId) => {
    if (READER_ONLY_MODE && nextQueueId !== DEFAULT_WORKBENCH_QUEUE) return;
    setQueueIdState(nextQueueId);
    setCohortYear(queueToCohortYear(nextQueueId));
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('gastric_queue', nextQueueId);
    }
  };

  const t = dictionary[language];

  return (
    <SettingsContext.Provider value={{ language, readerOnly: READER_ONLY_MODE, setLanguage, dataset, setDataset, cohortYear, setCohortYear, queueId, setQueueId, treatmentType, setTreatmentType, t }}>
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

