import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import { resolveDoctorSession } from '@/lib/reader/doctor-account-store';
import { getHistoryEntry, softDeleteHistoryEntry } from '@/lib/reader/operation-history-store';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';
import { resolveAuthenticatedReader } from '@/lib/reader/study-auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DATA_FILE = runtimeDataFile('reader_audit_events.jsonl');
const LEGACY_DATA_FILE = legacyAppDataFile('reader_audit_events.jsonl');

function resolveOwner(request: NextRequest): { ok: true; accountId: string } | { ok: false; status: number; error: string } {
  const doctor = resolveDoctorSession(request.headers);
  if (doctor.ok) return { ok: true, accountId: doctor.account.account_id };
  const research = resolveAuthenticatedReader(request.headers);
  if (research.ok) return { ok: true, accountId: research.readerId };
  return { ok: false, status: 401, error: 'Login with a doctor account is required' };
}

async function readEventsForSession(sessionId: string, accountId: string, limit: number) {
  const chunks = await Promise.all(
    [LEGACY_DATA_FILE, DATA_FILE].map(async (file) => {
      try {
        return await fs.readFile(file, 'utf8');
      } catch {
        return '';
      }
    }),
  );
  const events = chunks
    .join('\n')
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as Record<string, unknown>;
      } catch {
        return null;
      }
    })
    .filter((event): event is Record<string, unknown> => Boolean(event))
    .filter((event) => {
      if (event.session_id !== sessionId) return false;
      const owner = String(event.authenticated_reader_id || event.reader_id || '');
      return owner === accountId;
    })
    .slice(-limit);
  return events;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ historyId: string }> },
) {
  const owner = resolveOwner(request);
  if (!owner.ok) {
    return NextResponse.json({ ok: false, error: owner.error }, { status: owner.status });
  }
  const { historyId } = await context.params;
  const entry = getHistoryEntry(historyId, owner.accountId);
  if (!entry || entry.deleted_at) {
    return NextResponse.json({ ok: false, error: 'History entry not found' }, { status: 404 });
  }
  const limit = Math.min(Math.max(Number(request.nextUrl.searchParams.get('limit') || 300), 1), 1000);
  const events = await readEventsForSession(entry.session_id, owner.accountId, limit);
  const traces = events
    .filter((event) => event.event_type === 'model_trace' || event.event_type === 'mask_event' || event.event_type === 'doctor_action')
    .map((event) => {
      const payload = (event.payload && typeof event.payload === 'object')
        ? event.payload as Record<string, unknown>
        : {};
      return {
        event_id: event.event_id,
        event_type: event.event_type,
        recorded_at: event.recorded_at || event.client_recorded_at,
        action: payload.action || payload.operation || event.event_type,
        status: payload.outcome || payload.status || null,
        frame_time_sec: payload.frame_time_sec ?? null,
        input: payload.input || null,
        output: payload.output || null,
        error: payload.error || null,
        payload,
      };
    });
  return NextResponse.json({
    ok: true,
    entry,
    count: events.length,
    events,
    traces,
  });
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ historyId: string }> },
) {
  const owner = resolveOwner(request);
  if (!owner.ok) {
    return NextResponse.json({ ok: false, error: owner.error }, { status: owner.status });
  }
  const { historyId } = await context.params;
  const entry = softDeleteHistoryEntry(historyId, owner.accountId);
  if (!entry) {
    return NextResponse.json({ ok: false, error: 'History entry not found' }, { status: 404 });
  }
  return NextResponse.json({ ok: true, entry });
}
