import fs from 'fs';
import path from 'path';
import { PROJECT_ROOT } from '@/lib/config';
import type { ReaderCase, ReaderCasesBundle, ReaderCohort } from '@/lib/reader/types';

const BUNDLE_PATH = path.join(
  PROJECT_ROOT,
  'docs/clinical_validation/reader_study_v150/cases.bundle.js',
);

export function loadReaderCasesBundle(): ReaderCasesBundle {
  if (!fs.existsSync(BUNDLE_PATH)) {
    return { cases: [] };
  }
  const raw = fs.readFileSync(BUNDLE_PATH, 'utf-8');
  const jsonText = raw.replace(/^window\.READER_CASES\s*=\s*/, '').replace(/;\s*$/, '');
  return JSON.parse(jsonText) as ReaderCasesBundle;
}

export function filterReaderCases(cases: ReaderCase[], cohort: ReaderCohort): ReaderCase[] {
  const all = cases.filter((item) => item.has_video !== false);
  if (cohort === 't_staging') {
    return all.filter(
      (item) => item.study_mode === 't_staging' || String(item.case_id || '').startsWith('CASE-'),
    );
  }
  if (cohort === 'benign_malignancy') {
    return all.filter(
      (item) =>
        item.study_mode === 'benign_malignancy' || String(item.case_id || '').startsWith('BM-'),
    );
  }
  const bm = all.filter(
    (item) => item.study_mode === 'benign_malignancy' || String(item.case_id || '').startsWith('BM-'),
  );
  const ts = all.filter(
    (item) => item.study_mode === 't_staging' || String(item.case_id || '').startsWith('CASE-'),
  );
  const rest = all.filter((item) => !bm.includes(item) && !ts.includes(item));
  return [...bm, ...ts, ...rest];
}

export function findReaderCase(cases: ReaderCase[], caseId: string): ReaderCase | undefined {
  const norm = caseId.trim().toUpperCase();
  return cases.find((c) => String(c.case_id || '').toUpperCase() === norm);
}

export function findReaderCaseByPatientId(
  cases: ReaderCase[],
  patientId: string,
): ReaderCase | undefined {
  const norm = patientId.trim().toUpperCase();
  return cases.find((c) => String(c.patient_id || '').trim().toUpperCase() === norm);
}
