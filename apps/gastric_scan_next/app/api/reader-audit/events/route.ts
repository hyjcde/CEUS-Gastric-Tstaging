import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DATA_FILE = runtimeDataFile('reader_audit_events.jsonl');
const LEGACY_DATA_FILE = legacyAppDataFile('reader_audit_events.jsonl');
const EVENT_TYPES = new Set([
  'session_start',
  'session_end',
  'ai_suggestion',
  'report_generated',
  'doctor_action',
  'frame_viewed',
  'error',
  'boundary_saved',
  'mask_saved',
  'abstain',
]);

type AuditEvent = {
  event_id?: string;
  event_type: string;
  session_id: string;
  case_id: string;
  reader_id?: string;
  round?: string;
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

  const event = {
    event_id: text(body.event_id) || `${sessionId}:${Date.now()}:${eventType}`,
    event_type: eventType,
    session_id: sessionId,
    case_id: caseId,
    reader_id: text(body.reader_id) || undefined,
    round: text(body.round) || undefined,
    patient_id: text(body.patient_id) || undefined,
    payload: body.payload || {},
    client_recorded_at: text(body.client_recorded_at) || undefined,
    recorded_at: new Date().toISOString(),
  };

  await fs.mkdir(path.dirname(DATA_FILE), { recursive: true });
  await fs.appendFile(DATA_FILE, `${JSON.stringify(event)}\n`, 'utf8');
  return NextResponse.json({ ok: true, event_id: event.event_id });
}

export async function GET(request: NextRequest) {
  const sessionId = text(request.nextUrl.searchParams.get('session_id'));
  const caseId = text(request.nextUrl.searchParams.get('case_id'));
  const limit = Math.min(
    Math.max(Number(request.nextUrl.searchParams.get('limit') || 200), 1),
    1000,
  );
  try {
    const rawFiles = await Promise.all(
      [LEGACY_DATA_FILE, DATA_FILE]
        .filter((file, index, files) => files.indexOf(file) === index)
        .map(async (file) => {
          try {
            return await fs.readFile(file, 'utf8');
          } catch {
            return '';
          }
        }),
    );
    const events = rawFiles
      .join('\n')
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>)
      .filter((event) => {
        if (sessionId && event.session_id !== sessionId) return false;
        if (caseId && event.case_id !== caseId) return false;
        return true;
      })
      .slice(-limit);
    return NextResponse.json({ ok: true, count: events.length, events });
  } catch {
    return NextResponse.json({ ok: true, count: 0, events: [] });
  }
}
