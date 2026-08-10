import { NextRequest, NextResponse } from 'next/server';
import {
  createDoctorAccount,
  listDoctorAccounts,
  loginDoctorAccount,
  logoutDoctorSession,
  resolveDoctorSession,
} from '@/lib/reader/doctor-account-store';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const session = resolveDoctorSession(request.headers);
  return NextResponse.json({
    ok: true,
    authenticated: session.ok,
    account: session.ok ? session.account : null,
    accounts: listDoctorAccounts().map((account) => ({
      account_id: account.account_id,
      display_name: account.display_name,
      last_seen_at: account.last_seen_at,
    })),
  });
}

export async function POST(request: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON' }, { status: 400 });
  }

  const action = String(body.action || '').trim().toLowerCase();
  if (action === 'logout') {
    const current = resolveDoctorSession(request.headers);
    const token = current.ok ? current.token : String(body.token || '').trim();
    logoutDoctorSession(token);
    return NextResponse.json({ ok: true });
  }

  if (action === 'create') {
    const result = createDoctorAccount({
      account_id: body.account_id,
      display_name: body.display_name,
      pin: body.pin,
    });
    if (!result.ok) {
      return NextResponse.json({ ok: false, error: result.error }, { status: result.status });
    }
    return NextResponse.json({ ok: true, account: result.account, token: result.token });
  }

  if (action === 'login') {
    const result = loginDoctorAccount({
      account_id: body.account_id,
      pin: body.pin,
    });
    if (!result.ok) {
      return NextResponse.json({ ok: false, error: result.error }, { status: result.status });
    }
    return NextResponse.json({ ok: true, account: result.account, token: result.token });
  }

  return NextResponse.json({ ok: false, error: 'Unsupported action' }, { status: 400 });
}
