import { NextRequest, NextResponse } from 'next/server';
import { proxyAgentRequest } from '@/lib/agent-upstream';
import { formatFiveClass } from '@/lib/reader/five-class';
import { lookupGoldFiveClass } from '@/lib/reader/five-class-server';
import { canRevealCaseGold } from '@/lib/reader/gold-reveal-access';
import { isTrustedPublicUpstream } from '@/lib/reader/local-access';
import { requireAppAuth } from '@/lib/reader/require-app-auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const access = requireAppAuth(request);
  const admittedReader = isTrustedPublicUpstream(request.headers)
    ? (request.headers.get('x-authenticated-reader-id') || '')
    : '';
  const accountId = access.ok ? access.accountId : admittedReader;
  if (!access.ok && !admittedReader) return access.response;
  if (access.ok && process.env.NEXT_AGENT_UPSTREAM) {
    const forwarded = await proxyAgentRequest(
      request,
      request.nextUrl.pathname,
      canRevealCaseGold(access.accountId)
        ? { 'x-authenticated-reader-id': access.accountId }
        : undefined,
    );
    if (forwarded) return forwarded;
  }
  if (!canRevealCaseGold(accountId)) {
    return NextResponse.json(
      { ok: false, error: 'gold hidden', code: 'gold_forbidden' },
      { status: 403 },
    );
  }
  const patientId = request.nextUrl.searchParams.get('patient_id') || '';
  const caseId = request.nextUrl.searchParams.get('case_id') || '';
  const id = request.nextUrl.searchParams.get('id') || '';
  const phase = request.nextUrl.searchParams.get('phase') || '';
  const group = request.nextUrl.searchParams.get('group') || '';
  const queueId = request.nextUrl.searchParams.get('queue_id') || '';
  if (!patientId && !caseId && !id) {
    return NextResponse.json({ ok: false, error: 'missing id' }, { status: 400 });
  }
  const gold = lookupGoldFiveClass({
    id,
    patient_id: patientId,
    case_id: caseId,
    phase,
    group,
    queue_id: queueId,
  });
  return NextResponse.json({
    ok: true,
    available: gold.available,
    gold_five_class: gold.label,
    gold_label_zh: formatFiveClass(gold.label, true),
    gold_label_en: formatFiveClass(gold.label, false),
    source: gold.source,
  });
}
