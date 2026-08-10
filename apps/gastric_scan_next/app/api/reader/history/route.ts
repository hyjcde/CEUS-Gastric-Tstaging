import { NextRequest, NextResponse } from 'next/server';
import { resolveDoctorSession } from '@/lib/reader/doctor-account-store';
import {
  listHistoryForAccount,
  softDeleteAllHistoryForAccount,
  softDeleteHistoryEntry,
} from '@/lib/reader/operation-history-store';
import { resolveAuthenticatedReader } from '@/lib/reader/study-auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function resolveOwner(request: NextRequest): { ok: true; accountId: string } | { ok: false; status: number; error: string } {
  const doctor = resolveDoctorSession(request.headers);
  if (doctor.ok) return { ok: true, accountId: doctor.account.account_id };

  const research = resolveAuthenticatedReader(request.headers);
  if (research.ok) return { ok: true, accountId: research.readerId };

  return {
    ok: false,
    status: 401,
    error: 'Login with a doctor account is required to view history',
  };
}

export async function GET(request: NextRequest) {
  const owner = resolveOwner(request);
  if (!owner.ok) {
    return NextResponse.json({ ok: false, error: owner.error }, { status: owner.status });
  }
  const limit = Number(request.nextUrl.searchParams.get('limit') || 200);
  const entries = listHistoryForAccount(owner.accountId, { limit });
  return NextResponse.json({
    ok: true,
    owner_account_id: owner.accountId,
    count: entries.length,
    entries,
  });
}

export async function DELETE(request: NextRequest) {
  const owner = resolveOwner(request);
  if (!owner.ok) {
    return NextResponse.json({ ok: false, error: owner.error }, { status: owner.status });
  }

  const historyId = String(request.nextUrl.searchParams.get('history_id') || '').trim();
  const deleteAll = request.nextUrl.searchParams.get('all') === '1';

  if (deleteAll) {
    const deleted = softDeleteAllHistoryForAccount(owner.accountId);
    return NextResponse.json({ ok: true, deleted });
  }

  if (!historyId) {
    return NextResponse.json({ ok: false, error: 'history_id is required' }, { status: 400 });
  }
  const entry = softDeleteHistoryEntry(historyId, owner.accountId);
  if (!entry) {
    return NextResponse.json({ ok: false, error: 'History entry not found' }, { status: 404 });
  }
  return NextResponse.json({ ok: true, entry });
}
