import crypto from 'node:crypto';
import fs from 'fs';
import path from 'path';
import { normalizeReaderId } from '@/lib/reader/study-auth';
import { runtimeDataFile } from '@/lib/runtime-data';

const ACCOUNTS_FILE = runtimeDataFile('doctor_accounts.json');
const SESSIONS_FILE = runtimeDataFile('doctor_sessions.json');
const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 30; // 30 days
const SESSION_HEADER = 'x-doctor-session-token';

export type DoctorAccountPublic = {
  account_id: string;
  display_name: string;
  created_at: string;
  last_seen_at: string;
};

type DoctorAccountRecord = DoctorAccountPublic & {
  pin_salt: string;
  pin_hash: string;
};

type DoctorSessionRecord = {
  token: string;
  account_id: string;
  created_at: string;
  expires_at: string;
};

type AccountStore = {
  accounts: DoctorAccountRecord[];
};

type SessionStore = {
  sessions: DoctorSessionRecord[];
};

function readJsonFile<T>(file: string, fallback: T): T {
  try {
    if (!fs.existsSync(file)) return fallback;
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8')) as T;
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJsonFile(file: string, value: unknown) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2), 'utf8');
}

function readAccounts(): AccountStore {
  const store = readJsonFile<AccountStore>(ACCOUNTS_FILE, { accounts: [] });
  return {
    accounts: Array.isArray(store.accounts) ? store.accounts : [],
  };
}

function writeAccounts(store: AccountStore) {
  writeJsonFile(ACCOUNTS_FILE, store);
}

function readSessions(): SessionStore {
  const store = readJsonFile<SessionStore>(SESSIONS_FILE, { sessions: [] });
  const now = Date.now();
  const sessions = (Array.isArray(store.sessions) ? store.sessions : []).filter(
    (session) => Date.parse(session.expires_at) > now,
  );
  if (sessions.length !== (store.sessions || []).length) {
    writeJsonFile(SESSIONS_FILE, { sessions });
  }
  return { sessions };
}

function writeSessions(store: SessionStore) {
  writeJsonFile(SESSIONS_FILE, store);
}

function hashPin(pin: string, salt: string): string {
  return crypto.createHash('sha256').update(`${salt}:${pin}`, 'utf8').digest('hex');
}

function normalizePin(pin: unknown): string {
  const value = String(pin ?? '').trim();
  return /^\d{4,8}$/.test(value) ? value : '';
}

function normalizeDisplayName(value: unknown, accountId: string): string {
  const name = String(value ?? '').trim().slice(0, 48);
  return name || accountId;
}

function toPublic(account: DoctorAccountRecord): DoctorAccountPublic {
  return {
    account_id: account.account_id,
    display_name: account.display_name,
    created_at: account.created_at,
    last_seen_at: account.last_seen_at,
  };
}

function issueSession(accountId: string): DoctorSessionRecord {
  const now = new Date();
  const session: DoctorSessionRecord = {
    token: crypto.randomBytes(24).toString('hex'),
    account_id: accountId,
    created_at: now.toISOString(),
    expires_at: new Date(now.getTime() + SESSION_TTL_MS).toISOString(),
  };
  const store = readSessions();
  store.sessions = [session, ...store.sessions.filter((item) => item.account_id !== accountId)].slice(0, 500);
  writeSessions(store);
  return session;
}

export function listDoctorAccounts(): DoctorAccountPublic[] {
  return readAccounts().accounts
    .map(toPublic)
    .sort((a, b) => b.last_seen_at.localeCompare(a.last_seen_at));
}

export function createDoctorAccount(input: {
  account_id: unknown;
  display_name?: unknown;
  pin: unknown;
}): { ok: true; account: DoctorAccountPublic; token: string } | { ok: false; error: string; status: number } {
  const accountId = normalizeReaderId(input.account_id);
  const pin = normalizePin(input.pin);
  if (!accountId) {
    return { ok: false, error: 'account_id must be 1-64 letters, numbers, _ or -', status: 400 };
  }
  if (!pin) {
    return { ok: false, error: 'pin must be 4-8 digits', status: 400 };
  }
  const store = readAccounts();
  if (store.accounts.some((account) => account.account_id === accountId)) {
    return { ok: false, error: 'account_id already exists', status: 409 };
  }
  const now = new Date().toISOString();
  const salt = crypto.randomBytes(12).toString('hex');
  const account: DoctorAccountRecord = {
    account_id: accountId,
    display_name: normalizeDisplayName(input.display_name, accountId),
    pin_salt: salt,
    pin_hash: hashPin(pin, salt),
    created_at: now,
    last_seen_at: now,
  };
  store.accounts.push(account);
  writeAccounts(store);
  const session = issueSession(accountId);
  return { ok: true, account: toPublic(account), token: session.token };
}

export function loginDoctorAccount(input: {
  account_id: unknown;
  pin: unknown;
}): { ok: true; account: DoctorAccountPublic; token: string } | { ok: false; error: string; status: number } {
  const accountId = normalizeReaderId(input.account_id);
  const pin = normalizePin(input.pin);
  if (!accountId || !pin) {
    return { ok: false, error: 'account_id and 4-8 digit pin are required', status: 400 };
  }
  const store = readAccounts();
  const account = store.accounts.find((item) => item.account_id === accountId);
  if (!account || account.pin_hash !== hashPin(pin, account.pin_salt)) {
    return { ok: false, error: 'invalid account_id or pin', status: 401 };
  }
  account.last_seen_at = new Date().toISOString();
  writeAccounts(store);
  const session = issueSession(accountId);
  return { ok: true, account: toPublic(account), token: session.token };
}

export function logoutDoctorSession(token: unknown): boolean {
  const value = String(token ?? '').trim();
  if (!value) return false;
  const store = readSessions();
  const next = store.sessions.filter((session) => session.token !== value);
  if (next.length === store.sessions.length) return false;
  writeSessions({ sessions: next });
  return true;
}

export function resolveDoctorSession(headers: Headers): {
  ok: true;
  account: DoctorAccountPublic;
  token: string;
} | {
  ok: false;
  code: 'missing_session' | 'invalid_session';
  message: string;
} {
  const auth = String(headers.get('authorization') || '').trim();
  const bearer = auth.toLowerCase().startsWith('bearer ')
    ? auth.slice(7).trim()
    : '';
  const token = String(headers.get(SESSION_HEADER) || bearer || '').trim();
  if (!token) {
    return { ok: false, code: 'missing_session', message: 'Missing doctor session token' };
  }
  const session = readSessions().sessions.find((item) => item.token === token);
  if (!session || Date.parse(session.expires_at) <= Date.now()) {
    return { ok: false, code: 'invalid_session', message: 'Doctor session is invalid or expired' };
  }
  const store = readAccounts();
  const idx = store.accounts.findIndex((item) => item.account_id === session.account_id);
  if (idx < 0) {
    return { ok: false, code: 'invalid_session', message: 'Doctor account no longer exists' };
  }
  store.accounts[idx] = {
    ...store.accounts[idx],
    last_seen_at: new Date().toISOString(),
  };
  writeAccounts(store);
  return { ok: true, account: toPublic(store.accounts[idx]), token };
}

export const DOCTOR_SESSION_HEADER = SESSION_HEADER;
