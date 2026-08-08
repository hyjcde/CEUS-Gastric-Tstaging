import { NextRequest, NextResponse } from 'next/server';
import { getReadingAgentBaseUrl } from '@/lib/reading-agent-url';
import { proxyAgentRequest } from '@/lib/agent-upstream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

export async function GET(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = getReadingAgentBaseUrl();
  try {
    const res = await fetch(`${base}/api/sam/video-status`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(10_000),
    });
    const payload = await res.json();
    return NextResponse.json(payload, { status: res.status });
  } catch (error) {
    return NextResponse.json(
      { ok: false, available: false, error: error instanceof Error ? error.message : 'SAM2 video tracker unavailable' },
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
    const model = typeof body?.model === 'string' ? body.model : '';
    const sam31Base = String(process.env.SAM31_UPSTREAM || 'http://127.0.0.1:8768').replace(/\/+$/, '');
    const target = model === 'sam31'
      ? `${sam31Base}/api/sam31/video-propagate`
      : `${base}/api/sam/video-propagate`;
    const res = await fetch(target, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal: AbortSignal.timeout(600_000),
    });
    const text = await res.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { ok: false, error: text.slice(0, 500) };
    }
    if (!res.ok) {
      return NextResponse.json(
        {
          ok: false,
          available: true,
          error: `${model === 'sam31' ? 'SAM3.1' : 'SAM2'} video HTTP ${res.status}`,
          result: payload,
        },
        { status: res.status >= 500 ? 502 : res.status },
      );
    }
    return NextResponse.json({ ok: true, available: true, result: (payload as { result?: unknown })?.result ?? payload });
  } catch (error) {
    return NextResponse.json(
      { ok: false, available: false, error: error instanceof Error ? error.message : 'SAM2 video proxy failed' },
      { status: 503 },
    );
  }
}
