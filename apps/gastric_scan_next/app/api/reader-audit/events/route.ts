import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';
import {
  READER_ROUND2_AGENT_VERSION,
  READER_ROUND2_FREEZE_ID,
  READER_ROUND2_MANIFEST_VERSION,
  READER_ROUND2_MODEL_VERSION,
  READER_ROUND2_PROMPT_VERSION,
  READER_ROUND2_RULE_VERSION,
  READER_ROUND2_SOFTWARE_VERSION,
} from '@/lib/reader/study-contract';
import { assertResearchCaseAccess } from '@/lib/reader/research-gate';
import { resolveDoctorSession } from '@/lib/reader/doctor-account-store';
import { upsertHistoryFromAudit } from '@/lib/reader/operation-history-store';
import { resolveAuthenticatedReader } from '@/lib/reader/study-auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DATA_FILE = runtimeDataFile('reader_audit_events.jsonl');
const LEGACY_DATA_FILE = legacyAppDataFile('reader_audit_events.jsonl');
const EVENT_TYPES = new Set([
  'session_start',
  'session_end',
  'case_started',
  'case_completed',
  'initial_judgment',
  'ai_suggestion',
  'report_generated',
  'doctor_action',
  'frame_viewed',
  'error',
  'boundary_saved',
  'mask_saved',
  'mask_event',
  'model_trace',
  'abstain',
]);

type AuditEvent = {
  event_id?: string;
  event_type: string;
  session_id: string;
  case_id: string;
  reader_id?: string;
  authenticated_reader_id?: string;
  round?: string;
  condition?: string;
  study_mode?: string;
  freeze_id?: string;
  software_version?: string;
  agent_version?: string;
  model_version?: string;
  rule_version?: string;
  prompt_version?: string;
  manifest_version?: string;
  environment?: string;
  patient_id?: string;
  payload?: Record<string, unknown>;
  client_recorded_at?: string;
};

function text(value: unknown, fallback = '') {
  return String(value ?? fallback).trim();
}

function bad(message: string, status = 400) {
  return NextResponse.json({ ok: false, error: message }, { status });
}

async function readEventLines(files: string[]): Promise<string[]> {
  const chunks = await Promise.all(
    files.map(async (file) => {
      try {
        return await fs.readFile(file, 'utf8');
      } catch {
        return '';
      }
    }),
  );
  return chunks.join('\n').split('\n').filter(Boolean);
}

export async function POST(request: NextRequest) {
  let body: AuditEvent;
  try {
    body = (await request.json()) as AuditEvent;
  } catch {
    return bad('Invalid JSON');
  }

  const eventType = text(body.event_type);
  const sessionId = text(body.session_id);
  const caseId = text(body.case_id);
  if (!EVENT_TYPES.has(eventType)) return bad('Unsupported event_type');
  if (!sessionId || !caseId) return bad('session_id and case_id are required');
  if (body.payload && typeof body.payload !== 'object') return bad('payload must be an object');

  const payload = body.payload || {};
  const environment = text(body.environment || payload.environment);
  const round = text(body.round || payload.round);
  const requestedReaderId = text(body.reader_id || payload.reader_id);
  let authenticatedReaderId = '';
  let versions = {
    freeze_id: text(body.freeze_id || payload.freeze_id || READER_ROUND2_FREEZE_ID),
    software_version: text(body.software_version || payload.software_version || READER_ROUND2_SOFTWARE_VERSION),
    agent_version: text(body.agent_version || payload.agent_version || READER_ROUND2_AGENT_VERSION),
    model_version: text(body.model_version || payload.model_version || READER_ROUND2_MODEL_VERSION),
    rule_version: text(body.rule_version || payload.rule_version || READER_ROUND2_RULE_VERSION),
    prompt_version: text(body.prompt_version || payload.prompt_version || READER_ROUND2_PROMPT_VERSION),
    manifest_version: text(body.manifest_version || payload.manifest_version || READER_ROUND2_MANIFEST_VERSION),
  };

  if (environment === 'research') {
    const access = await assertResearchCaseAccess({
      headers: request.headers,
      requestedReaderId,
      caseId,
      round,
      versions: {
        freeze_id: body.freeze_id || payload.freeze_id,
        software_version: body.software_version || payload.software_version,
        agent_version: body.agent_version || payload.agent_version,
        model_version: body.model_version || payload.model_version,
        rule_version: body.rule_version || payload.rule_version,
        prompt_version: body.prompt_version || payload.prompt_version,
        manifest_version: body.manifest_version || payload.manifest_version,
      },
      requireInitialJudgment: eventType === 'doctor_action' || eventType === 'case_completed',
      sessionId,
    });
    if (!access.ok) {
      return NextResponse.json(
        { ok: false, error: access.message, code: access.code },
        { status: access.status },
      );
    }
    if (body.authenticated_reader_id && body.authenticated_reader_id !== access.readerId) {
      return bad('authenticated_reader_id does not match the trusted proxy identity', 403);
    }
    authenticatedReaderId = access.readerId;
    versions = access.versions;
  } else {
    const doctor = resolveDoctorSession(request.headers);
    if (doctor.ok) {
      authenticatedReaderId = doctor.account.account_id;
      if (requestedReaderId && requestedReaderId !== authenticatedReaderId) {
        return bad('reader_id does not match the logged-in doctor account', 403);
      }
    }
  }

  const condition = text(body.condition || payload.condition || (round === 'round1' ? 'no_ai' : 'ai_assisted'));
  const studyMode = text(body.study_mode || payload.study_mode);
  const ownerReaderId = authenticatedReaderId || requestedReaderId || undefined;
  const normalizedPayload = {
    ...payload,
    ...(environment ? { environment } : {}),
    ...(round ? { round } : {}),
    ...(condition ? { condition } : {}),
    ...(studyMode ? { study_mode: studyMode } : {}),
    ...versions,
    ...(authenticatedReaderId ? { authenticated_reader_id: authenticatedReaderId } : {}),
  };
  const event = {
    event_id: text(body.event_id) || `${sessionId}:${Date.now()}:${eventType}`,
    event_type: eventType,
    session_id: sessionId,
    case_id: caseId,
    reader_id: ownerReaderId,
    authenticated_reader_id: authenticatedReaderId || undefined,
    round: round || undefined,
    condition: condition || undefined,
    study_mode: studyMode || undefined,
    ...versions,
    environment: environment || undefined,
    patient_id: text(body.patient_id) || undefined,
    payload: normalizedPayload,
    client_recorded_at: text(body.client_recorded_at) || undefined,
    recorded_at: new Date().toISOString(),
  };

  await fs.mkdir(path.dirname(DATA_FILE), { recursive: true });
  await fs.appendFile(DATA_FILE, `${JSON.stringify(event)}\n`, 'utf8');

  if (ownerReaderId) {
    upsertHistoryFromAudit({
      owner_account_id: ownerReaderId,
      session_id: sessionId,
      case_id: caseId,
      patient_id: text(body.patient_id) || undefined,
      event_type: eventType,
      environment: environment || undefined,
      study_mode: studyMode || undefined,
      payload: normalizedPayload,
      recorded_at: event.recorded_at,
    });
  }

  return NextResponse.json({ ok: true, event_id: event.event_id });
}

export async function GET(request: NextRequest) {
  const doctor = resolveDoctorSession(request.headers);
  const research = resolveAuthenticatedReader(request.headers);
  const ownerReaderId = doctor.ok
    ? doctor.account.account_id
    : research.ok
      ? research.readerId
      : '';
  if (!ownerReaderId) {
    return NextResponse.json(
      { ok: false, error: 'Login with a doctor account is required to read audit events' },
      { status: 401 },
    );
  }

  const sessionId = text(request.nextUrl.searchParams.get('session_id'));
  const caseId = text(request.nextUrl.searchParams.get('case_id'));
  const limit = Math.min(
    Math.max(Number(request.nextUrl.searchParams.get('limit') || 200), 1),
    1000,
  );
  try {
    const lines = await readEventLines(
      [LEGACY_DATA_FILE, DATA_FILE].filter((file, index, files) => files.indexOf(file) === index),
    );
    const events = lines
      .map((line) => JSON.parse(line) as Record<string, unknown>)
      .filter((event) => {
        const eventOwner = text(event.authenticated_reader_id || event.reader_id);
        if (eventOwner !== ownerReaderId) return false;
        if (sessionId && event.session_id !== sessionId) return false;
        if (caseId && event.case_id !== caseId) return false;
        return true;
      })
      .slice(-limit);
    return NextResponse.json({
      ok: true,
      owner_account_id: ownerReaderId,
      count: events.length,
      events,
    });
  } catch {
    return NextResponse.json({
      ok: true,
      owner_account_id: ownerReaderId,
      count: 0,
      events: [],
    });
  }
}
