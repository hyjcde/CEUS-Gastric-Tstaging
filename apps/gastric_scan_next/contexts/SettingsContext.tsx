"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Language, dictionary } from '@/lib/i18n';
import { CohortYear, DatasetType, DEFAULT_DATASET, TreatmentType } from '@/lib/cohort';

interface SettingsContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  dataset: DatasetType;
  setDataset: (ds: DatasetType) => void;
  cohortYear: CohortYear;
  setCohortYear: (year: CohortYear) => void;
  treatmentType: TreatmentType;
  setTreatmentType: (type: TreatmentType) => void;
  t: typeof dictionary['en'];
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

function readStoredDataset(): DatasetType {
  if (typeof window === 'undefined') return DEFAULT_DATASET;
  const stored = window.localStorage.getItem('gastric_dataset');
  if (stored === 'original' || stored === 'cropped') return stored;
  return DEFAULT_DATASET;
}

export const SettingsProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguage] = useState<Language>('zh'); // Default to Chinese per request
  const [dataset, setDatasetState] = useState<DatasetType>(DEFAULT_DATASET);

  useEffect(() => {
    setDatasetState(readStoredDataset());
  }, []);

  const setDataset = (ds: DatasetType) => {
    setDatasetState(ds);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('gastric_dataset', ds);
    }
  };
  const [cohortYear, setCohortYear] = useState<CohortYear>('2025');
  const [treatmentType, setTreatmentType] = useState<TreatmentType>('surgery'); // Default to surgery (can be 'surgery' or 'nac')

  const t = dictionary[language];

  return (
    <SettingsContext.Provider value={{ language, setLanguage, dataset, setDataset, cohortYear, setCohortYear, treatmentType, setTreatmentType, t }}>
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

