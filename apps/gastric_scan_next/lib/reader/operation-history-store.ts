import fs from 'fs';
import path from 'path';
import { runtimeDataFile } from '@/lib/runtime-data';

const HISTORY_FILE = runtimeDataFile('doctor_operation_history.json');

export type DoctorHistoryEntry = {
  history_id: string;
  owner_account_id: string;
  session_id: string;
  case_id: string;
  patient_id?: string;
  title: string;
  summary: string;
  event_count: number;
  last_event_type: string;
  last_action?: string;
  environment?: string;
  study_mode?: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

type HistoryStore = {
  entries: DoctorHistoryEntry[];
};

function readStore(): HistoryStore {
  try {
    if (!fs.existsSync(HISTORY_FILE)) return { entries: [] };
    const parsed = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf8')) as HistoryStore;
    return {
      entries: Array.isArray(parsed.entries) ? parsed.entries : [],
    };
  } catch {
    return { entries: [] };
  }
}

function writeStore(store: HistoryStore) {
  fs.mkdirSync(path.dirname(HISTORY_FILE), { recursive: true });
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(store, null, 2), 'utf8');
}

function text(value: unknown, fallback = ''): string {
  return String(value ?? fallback).trim();
}

function buildTitle(caseId: string, patientId?: string): string {
  if (patientId && patientId !== caseId) return `${patientId} / ${caseId}`;
  return caseId || '未命名病例';
}

function buildSummary(eventType: string, payload: Record<string, unknown>): string {
  const action = text(payload.action || payload.operation || eventType);
  const outcome = text(payload.outcome || payload.status);
  if (action && outcome) return `${action} (${outcome})`;
  return action || eventType;
}

export function upsertHistoryFromAudit(input: {
  owner_account_id: string;
  session_id: string;
  case_id: string;
  patient_id?: string;
  event_type: string;
  environment?: string;
  study_mode?: string;
  payload?: Record<string, unknown>;
  recorded_at?: string;
}): DoctorHistoryEntry | null {
  const owner = text(input.owner_account_id);
  const sessionId = text(input.session_id);
  const caseId = text(input.case_id);
  if (!owner || !sessionId || !caseId) return null;

  const store = readStore();
  const now = text(input.recorded_at) || new Date().toISOString();
  const payload = input.payload && typeof input.payload === 'object' ? input.payload : {};
  const existing = store.entries.find(
    (entry) => entry.owner_account_id === owner
      && entry.session_id === sessionId
      && !entry.deleted_at,
  );

  if (existing) {
    existing.case_id = caseId;
    existing.patient_id = text(input.patient_id) || existing.patient_id;
    existing.title = buildTitle(existing.case_id, existing.patient_id);
    existing.summary = buildSummary(input.event_type, payload);
    existing.event_count += 1;
    existing.last_event_type = input.event_type;
    existing.last_action = text(payload.action || payload.operation) || existing.last_action;
    existing.environment = text(input.environment) || existing.environment;
    existing.study_mode = text(input.study_mode) || existing.study_mode;
    existing.updated_at = now;
    writeStore(store);
    return existing;
  }

  const entry: DoctorHistoryEntry = {
    history_id: `hist_${owner}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    owner_account_id: owner,
    session_id: sessionId,
    case_id: caseId,
    patient_id: text(input.patient_id) || undefined,
    title: buildTitle(caseId, text(input.patient_id) || undefined),
    summary: buildSummary(input.event_type, payload),
    event_count: 1,
    last_event_type: input.event_type,
    last_action: text(payload.action || payload.operation) || undefined,
    environment: text(input.environment) || undefined,
    study_mode: text(input.study_mode) || undefined,
    created_at: now,
    updated_at: now,
    deleted_at: null,
  };
  store.entries = [entry, ...store.entries].slice(0, 5000);
  writeStore(store);
  return entry;
}

export function listHistoryForAccount(
  accountId: string,
  options: { includeDeleted?: boolean; limit?: number } = {},
): DoctorHistoryEntry[] {
  const owner = text(accountId);
  const limit = Math.min(Math.max(options.limit || 200, 1), 1000);
  return readStore().entries
    .filter((entry) => entry.owner_account_id === owner)
    .filter((entry) => options.includeDeleted || !entry.deleted_at)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, limit);
}

export function getHistoryEntry(
  historyId: string,
  accountId: string,
): DoctorHistoryEntry | null {
  const id = text(historyId);
  const owner = text(accountId);
  if (!id || !owner) return null;
  return readStore().entries.find(
    (entry) => entry.history_id === id && entry.owner_account_id === owner,
  ) || null;
}

export function softDeleteHistoryEntry(
  historyId: string,
  accountId: string,
): DoctorHistoryEntry | null {
  const store = readStore();
  const entry = store.entries.find(
    (item) => item.history_id === text(historyId) && item.owner_account_id === text(accountId),
  );
  if (!entry || entry.deleted_at) return null;
  entry.deleted_at = new Date().toISOString();
  entry.updated_at = entry.deleted_at;
  writeStore(store);
  return entry;
}

export function softDeleteAllHistoryForAccount(accountId: string): number {
  const store = readStore();
  const owner = text(accountId);
  const now = new Date().toISOString();
  let count = 0;
  for (const entry of store.entries) {
    if (entry.owner_account_id !== owner || entry.deleted_at) continue;
    entry.deleted_at = now;
    entry.updated_at = now;
    count += 1;
  }
  if (count) writeStore(store);
  return count;
}
