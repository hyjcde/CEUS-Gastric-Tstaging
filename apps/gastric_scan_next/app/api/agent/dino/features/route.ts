import { NextRequest, NextResponse } from 'next/server';
import { getReadingAgentBaseUrl } from '@/lib/reading-agent-url';
import { proxyAgentRequest } from '@/lib/agent-upstream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 180;

export async function GET(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = getReadingAgentBaseUrl();
  try {
    const load = request.nextUrl.searchParams.get('load');
    const qs = load ? `?load=${encodeURIComponent(load)}` : '';
    const response = await fetch(`${base}/api/sam/dino-status${qs}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(30_000),
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        available: false,
        error: error instanceof Error ? error.message : 'DINO feature service unavailable',
      },
      { status: 503 },
    );
  }
}

export async function POST(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = getReadingAgentBaseUrl();
  try {
    const body = await request.json();
    const response = await fetch(`${base}/api/sam/dino-features`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal: AbortSignal.timeout(180_000),
    });
    const text = await response.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { ok: false, error: text.slice(0, 500) };
    }
    if (!response.ok) {
      return NextResponse.json(
        { ok: false, available: true, error: `DINO feature HTTP ${response.status}`, result: payload },
        { status: response.status >= 500 ? 502 : response.status },
      );
    }
    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        available: false,
        error: error instanceof Error ? error.message : 'DINO feature proxy failed',
      },
      { status: 503 },
    );
  }
}
