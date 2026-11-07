import fs from 'fs';
import path from 'path';
import { APP_ROOT, PROJECT_ROOT } from '@/lib/config';
import { findReaderCase, findReaderCaseByPatientId, loadReaderCasesBundle } from '@/lib/reader/cases-server';
import {
  goldFromClinicalRecord,
  goldFromReaderRefs,
  normalizeFiveClass,
  type FiveClassLabel,
} from '@/lib/reader/five-class';
import { PUBLIC_DEMO_STILL_CASES } from '@/lib/public-demo-stills';
import { lookupClinicalHistory } from '@/lib/clinical-history-server';

export type GoldLookup = {
  available: boolean;
  label: FiveClassLabel | null;
  source: 'reader_bundle' | 'clinical_pt' | 'benign_queue' | 'demo_still' | 'none';
};

let cachedClinicalMaps: Array<Record<string, Record<string, unknown>>> | undefined;
let cachedTableGold: { general: Map<string, FiveClassLabel>; year2026: Map<string, FiveClassLabel> } | undefined;

function readStageMap(filePath: string): Map<string, FiveClassLabel> {
  const map = new Map<string, FiveClassLabel>();
  const conflicts = new Set<string>();
  if (!fs.existsSync(filePath)) return map;
  const lines = fs.readFileSync(filePath, 'utf-8').split(/\r?\n/);
  const header = (lines[0] || '').replace(/^\uFEFF/, '').split(',');
  const idIndex = header.indexOf('patient_id');
  const stageIndex = header.indexOf('T_stage');
  if (idIndex < 0 || stageIndex < 0) return map;
  for (const line of lines.slice(1)) {
    if (!line.trim()) continue;
    const cells = line.split(',');
    const patientId = String(cells[idIndex] || '').trim();
    const label = normalizeFiveClass(cells[stageIndex]);
    if (!patientId || !label) continue;
    const previous = map.get(patientId);
    if (previous && previous !== label) {
      conflicts.add(patientId);
      continue;
    }
    map.set(patientId, label);
  }
  for (const patientId of conflicts) map.delete(patientId);
  return map;
}

function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          current += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        current += ch;
      }
      continue;
    }
    if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      cells.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells;
}

function fillMasterPt(map: Map<string, FiveClassLabel>) {
  const filePath = path.join(PROJECT_ROOT, 'dataset/patient_clinical_master.csv');
  if (!fs.existsSync(filePath)) return;
  const lines = fs.readFileSync(filePath, 'utf-8').split(/\r?\n/);
  const header = splitCsvLine((lines[0] || '').replace(/^\uFEFF/, ''));
  const idIndex = header.indexOf('patient_id_norm');
  const stageIndex = header.indexOf('pT');
  const okIndex = header.indexOf('pT_parse_ok');
  const conflictIndex = header.indexOf('pT_conflict');
  if (idIndex < 0 || stageIndex < 0) return;
  const incoming = new Map<string, FiveClassLabel>();
  const conflicts = new Set<string>();
  for (const line of lines.slice(1)) {
    if (!line.trim()) continue;
    const cells = splitCsvLine(line);
    if (okIndex >= 0 && cells[okIndex] !== '1') continue;
    if (conflictIndex >= 0 && cells[conflictIndex] === '1') continue;
    const patientId = String(cells[idIndex] || '').trim();
    const label = normalizeFiveClass(cells[stageIndex]);
    if (!patientId || !label || map.has(patientId)) continue;
    const previous = incoming.get(patientId);
    if (previous && previous !== label) {
      conflicts.add(patientId);
      continue;
    }
    incoming.set(patientId, label);
  }
  for (const [patientId, label] of incoming) {
    if (!conflicts.has(patientId)) map.set(patientId, label);
  }
}

function loadTableGold(): { general: Map<string, FiveClassLabel>; year2026: Map<string, FiveClassLabel> } {
  if (cachedTableGold) return cachedTableGold;
  const general = readStageMap(path.join(PROJECT_ROOT, 'tstaging_lab/data/clinical/patient_clinical_11.csv'));
  fillMasterPt(general);
  cachedTableGold = {
    general,
    year2026: readStageMap(path.join(PROJECT_ROOT, 'pipeline/data/_tmp_prospective_2026_accboost2_20261014/test_prospective_2026_stills_clinical.csv')),
  };
  return cachedTableGold;
}

function idCandidates(token: string): string[] {
  const raw = String(token || '').trim();
  if (!raw) return [];
  const digits = raw.replace(/^Z/i, '').replace(/^0+/, '') || '0';
  return Array.from(new Set([
    raw,
    raw.toUpperCase(),
    raw.replace(/_+$/g, ''),
    raw.replace(/[^0-9A-Za-z]/g, ''),
    raw.replace(/^0+/, ''),
    raw.padStart(7, '0'),
    digits,
    digits.padStart(7, '0'),
    `0${digits}`,
    `Z${digits}`,
    `Z${digits.padStart(7, '0')}`,
  ]));
}

function loadClinicalMaps(): Array<Record<string, Record<string, unknown>>> {
  if (cachedClinicalMaps) return cachedClinicalMaps;
  const dir = path.join(APP_ROOT, 'data');
  const maps: Array<Record<string, Record<string, unknown>>> = [];
  if (!fs.existsSync(dir)) {
    cachedClinicalMaps = maps;
    return maps;
  }
  const files = fs.readdirSync(dir).filter((name) => /^clinical_data_.*\.json$/i.test(name));
  for (const name of files) {
    try {
      const parsed = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf-8')) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        maps.push(parsed as Record<string, Record<string, unknown>>);
      }
    } catch {
      // Optional enrichment only.
    }
  }
  cachedClinicalMaps = maps;
  return maps;
}

function clinicalByPatientId(patientId: string): Record<string, unknown> | undefined {
  const maps = loadClinicalMaps();
  for (const key of idCandidates(patientId)) {
    for (const map of maps) {
      if (map[key]) return map[key];
    }
  }
  return undefined;
}

function isDemoStillId(token: string): boolean {
  return PUBLIC_DEMO_STILL_CASES.some((item) => (
    item.id === token
    || item.patient_id === token
    || item.frames.some((frame) => frame.id === token)
  ));
}

export function lookupGoldFiveClass(query: {
  id?: string | null;
  patient_id?: string | null;
  case_id?: string | null;
  phase?: string | null;
  group?: string | null;
  queue_id?: string | null;
}): GoldLookup {
  const ids = [query.case_id, query.id, query.patient_id]
    .map((item) => String(item || '').trim())
    .filter(Boolean);

  if (ids.some((id) => isDemoStillId(id))) {
    return { available: true, label: 'T1', source: 'demo_still' };
  }

  const bundle = loadReaderCasesBundle();
  for (const id of ids) {
    const found = findReaderCase(bundle.cases || [], id)
      || findReaderCaseByPatientId(bundle.cases || [], id);
    if (!found) continue;
    const label = goldFromReaderRefs(found.reference_pt, found.reference_lesion_nature);
    if (label) return { available: true, label, source: 'reader_bundle' };
  }

  if (
    query.phase === 'benign'
    || query.group === 'Benign'
    || ids.some((id) => id.startsWith('benign:'))
  ) {
    return { available: true, label: 'benign', source: 'benign_queue' };
  }

  for (const id of ids) {
    const label = goldFromClinicalRecord(clinicalByPatientId(id));
    if (label) return { available: true, label, source: 'clinical_pt' };
  }

  const queueId = String(query.queue_id || '').trim()
    || (query.phase && query.phase !== 'external' && query.phase !== 'benign' && query.phase !== 'reader_v150'
      ? `internal:${query.phase}`
      : '');
  if (queueId) {
    for (const id of ids) {
      const hit = lookupClinicalHistory(id, { queueId });
      const label = goldFromClinicalRecord({ pT: hit?.pT, T_stage: hit?.pT });
      if (label) return { available: true, label, source: 'clinical_pt' };
    }
  }

  const tables = loadTableGold();
  const tableGold = queueId === 'internal:2026' ? tables.year2026 : tables.general;
  for (const id of ids) {
    for (const key of idCandidates(id)) {
      const label = tableGold.get(key);
      if (label) return { available: true, label, source: 'clinical_pt' };
    }
  }

  return { available: false, label: null, source: 'none' };
}
