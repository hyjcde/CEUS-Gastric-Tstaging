import fs from 'fs';
import path from 'path';
import { PROJECT_ROOT } from '@/lib/config';
import type { ClinicalData } from '@/types';
import type { ReaderCase } from '@/lib/reader/types';

const ASSIST_US_CLINICAL_PATH = path.join(
  PROJECT_ROOT,
  'docs/clinical_validation/reader_study_v150/demo_assets/assist_us_clinical.js',
);
const COVERAGE_CSV_PATH = path.join(
  PROJECT_ROOT,
  'artifacts/eval/reader_study_v150_human_ai_comparison/static_image_coverage.csv',
);
const ULTIMATE_CLINICAL_PATH = path.join(
  PROJECT_ROOT,
  'apps/gastric_scan_next/data/clinical_data_ultimate.json',
);

type UsClinicalRow = {
  hospital_id?: string;
  case_id?: string;
  tumor_size_mm?: number | null;
  tumor_thickness_mm?: number | null;
  tumor_location?: string | null;
  cea?: number | null;
  cea_positive?: number | boolean | null;
  ca199?: number | null;
  ca199_positive?: number | boolean | null;
  source?: string | null;
  sheet?: string | null;
};

type AssistUsClinicalPack = {
  by_hospital?: Record<string, UsClinicalRow>;
  by_case?: Record<string, UsClinicalRow>;
};

let cachedPack: AssistUsClinicalPack | null | undefined;
let cachedCoverage: Map<string, string> | null | undefined;
let cachedUltimate: Record<string, Record<string, unknown>> | null | undefined;

function positiveNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function loadAssistUsClinicalPack(): AssistUsClinicalPack | null {
  if (cachedPack !== undefined) return cachedPack;
  if (!fs.existsSync(ASSIST_US_CLINICAL_PATH)) {
    cachedPack = null;
    return cachedPack;
  }
  try {
    const raw = fs.readFileSync(ASSIST_US_CLINICAL_PATH, 'utf-8');
    const jsonText = raw
      .replace(/^[\s\S]*?window\.ASSIST_US_CLINICAL\s*=\s*/, '')
      .replace(/;\s*$/, '');
    cachedPack = JSON.parse(jsonText) as AssistUsClinicalPack;
  } catch {
    cachedPack = null;
  }
  return cachedPack;
}

function hospitalIdCandidates(token: string): string[] {
  const out = new Set<string>();
  for (const match of String(token || '').matchAll(/(Z?\d{5,})/gi)) {
    const raw = match[1];
    const upper = raw.toUpperCase();
    const digits = upper.replace(/^Z/, '').replace(/^0+/, '') || '0';
    out.add(upper);
    out.add(digits);
    out.add(`Z${digits}`);
    out.add(digits.padStart(7, '0'));
    out.add(`Z${digits.padStart(7, '0')}`);
  }
  return Array.from(out);
}

function loadCoverageHospitalMap(): Map<string, string> {
  if (cachedCoverage !== undefined) return cachedCoverage || new Map();
  const map = new Map<string, string>();
  if (!fs.existsSync(COVERAGE_CSV_PATH)) {
    cachedCoverage = map;
    return map;
  }
  try {
    const lines = fs.readFileSync(COVERAGE_CSV_PATH, 'utf-8').split(/\r?\n/).filter(Boolean);
    const header = lines[0]?.split(',') || [];
    const caseIdx = header.indexOf('case_id');
    const tokenIdx = header.indexOf('media_tokens');
    const imageIdx = header.indexOf('example_image_source');
    const videoIdx = header.indexOf('example_crop_video');
    for (const line of lines.slice(1)) {
      const cols = line.split(',');
      const caseId = cols[caseIdx]?.trim();
      if (!caseId) continue;
      const blob = [cols[tokenIdx], cols[imageIdx], cols[videoIdx]].filter(Boolean).join('|');
      const hid = hospitalIdCandidates(blob)[0];
      if (hid) map.set(caseId, hid);
    }
  } catch {
    // Optional enrichment only.
  }
  cachedCoverage = map;
  return map;
}

function loadUltimateClinical(): Record<string, Record<string, unknown>> {
  if (cachedUltimate !== undefined) return cachedUltimate || {};
  if (!fs.existsSync(ULTIMATE_CLINICAL_PATH)) {
    cachedUltimate = {};
    return cachedUltimate;
  }
  try {
    cachedUltimate = JSON.parse(
      fs.readFileSync(ULTIMATE_CLINICAL_PATH, 'utf-8'),
    ) as Record<string, Record<string, unknown>>;
  } catch {
    cachedUltimate = {};
  }
  return cachedUltimate;
}

function ultimateRowToUs(entry: Record<string, unknown>, hospitalId: string): UsClinicalRow | null {
  const tumorSize = entry.tumorSize as Record<string, unknown> | undefined;
  const lengthCm = positiveNumber(tumorSize?.length);
  const thicknessCm = positiveNumber(tumorSize?.thickness);
  const biomarkers = entry.biomarkers as Record<string, unknown> | undefined;
  if (lengthCm == null && thicknessCm == null && !entry.location) return null;
  return {
    hospital_id: hospitalId,
    tumor_size_mm: lengthCm == null ? null : lengthCm * 10,
    tumor_thickness_mm: thicknessCm == null ? null : thicknessCm * 10,
    tumor_location: entry.location ? String(entry.location) : null,
    cea: positiveNumber(biomarkers?.cea),
    cea_positive: Boolean(biomarkers?.cea_positive),
    ca199: positiveNumber(biomarkers?.ca199),
    ca199_positive: Boolean(biomarkers?.ca199_positive),
    source: 'clinical_data_ultimate',
  };
}

function lookupUltimateByHospital(hospitalId: string): UsClinicalRow | null {
  const ultimate = loadUltimateClinical();
  for (const candidate of hospitalIdCandidates(hospitalId)) {
    const entry = ultimate[candidate];
    if (entry) return ultimateRowToUs(entry, candidate);
  }
  return null;
}

function mergeUsRows(primary: UsClinicalRow | null, fallback: UsClinicalRow | null): UsClinicalRow | null {
  if (!primary) return fallback;
  if (!fallback) return primary;
  return {
    ...fallback,
    ...primary,
    tumor_size_mm: primary.tumor_size_mm ?? fallback.tumor_size_mm,
    tumor_thickness_mm: primary.tumor_thickness_mm ?? fallback.tumor_thickness_mm,
    tumor_location: primary.tumor_location || fallback.tumor_location,
    cea: primary.cea ?? fallback.cea,
    cea_positive: primary.cea_positive ?? fallback.cea_positive,
    ca199: primary.ca199 ?? fallback.ca199,
    ca199_positive: primary.ca199_positive ?? fallback.ca199_positive,
  };
}

function lookupRowForCase(item: ReaderCase): UsClinicalRow | null {
  const pack = loadAssistUsClinicalPack();
  const caseKeys = [item.case_id, item.display_id, item.patient_id]
    .map((value) => String(value || '').trim())
    .filter(Boolean);

  let assistHit: UsClinicalRow | null = null;
  if (pack) {
    for (const key of caseKeys) {
      const byCase = pack.by_case?.[key];
      if (byCase) {
        assistHit = byCase;
        break;
      }
    }
  }

  const coverageHid = caseKeys.map((key) => loadCoverageHospitalMap().get(key)).find(Boolean);
  const tokenBlob = [
    ...caseKeys,
    coverageHid || '',
    ...(item.frames || []).map((frame) => String(frame.media_token || '')),
  ].join('|');
  const hospitalCandidates = hospitalIdCandidates(tokenBlob);

  if (!assistHit && pack) {
    for (const candidate of hospitalCandidates) {
      const byHospital = pack.by_hospital?.[candidate];
      if (byHospital) {
        assistHit = byHospital;
        break;
      }
    }
  }

  let ultimateHit: UsClinicalRow | null = null;
  for (const candidate of hospitalCandidates) {
    ultimateHit = lookupUltimateByHospital(candidate);
    if (ultimateHit) break;
  }

  return mergeUsRows(assistHit, ultimateHit);
}

function markerPositive(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value > 0;
  if (typeof value === 'string') return /阳|\+|positive|1/i.test(value);
  return false;
}

/** Map ultrasound table fields onto Patient.clinical (tumorSize stays in cm). */
export function clinicalFromReaderUsTable(item: ReaderCase): ClinicalData | undefined {
  const row = lookupRowForCase(item);
  if (!row) return undefined;

  const lengthMm = positiveNumber(row.tumor_size_mm);
  const thicknessMm = positiveNumber(row.tumor_thickness_mm);
  const location = String(row.tumor_location || '').trim();
  const cea = positiveNumber(row.cea);
  const ca199 = positiveNumber(row.ca199);

  if (lengthMm == null && thicknessMm == null && !location && cea == null && ca199 == null) {
    return undefined;
  }

  return {
    age: null,
    sex: '',
    tumorSize: {
      length: lengthMm == null ? null : Number((lengthMm / 10).toFixed(2)),
      thickness: thicknessMm == null ? null : Number((thicknessMm / 10).toFixed(2)),
    },
    location,
    biomarkers: {
      cea,
      ca199,
      cea_positive: markerPositive(row.cea_positive) || (cea != null && cea > 5),
      ca199_positive: markerPositive(row.ca199_positive) || (ca199 != null && ca199 > 37),
    },
  };
}
