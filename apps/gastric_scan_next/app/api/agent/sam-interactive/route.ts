import { NextRequest, NextResponse } from 'next/server';
import { getReadingAgentBaseUrl } from '@/lib/reading-agent-url';
import { proxyAgentRequest } from '@/lib/agent-upstream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/**
 * Proxy click/box prompts to the local SAM agent (:8767).
 * Returns { ok:false, available:false } when the SAM server is down — UI can fall back to manual edit.
 */
export async function GET(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = getReadingAgentBaseUrl();
  try {
    const res = await fetch(`${base}/api/sam/status`, { cache: 'no-store', signal: AbortSignal.timeout(4000) });
    if (!res.ok) {
      return NextResponse.json({ available: false, error: `SAM status HTTP ${res.status}` });
    }
    const status = await res.json();
    return NextResponse.json({ available: true, status, base });
  } catch (error) {
    return NextResponse.json({
      available: false,
      base,
      error: error instanceof Error ? error.message : 'SAM server unreachable',
      hint: 'Start with: python3 scripts/serve_interactive_sam_agent.py --port 8767',
    });
  }
}

export async function POST(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = getReadingAgentBaseUrl();
  try {
    const body = await request.json();
    const res = await fetch(`${base}/api/sam/interactive-analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120000),
    });
    const text = await res.text();
    let payload: unknown = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { ok: false, message: text.slice(0, 500) };
    }
    if (!res.ok) {
      return NextResponse.json(
        { ok: false, available: true, error: `SAM HTTP ${res.status}`, result: payload },
        { status: res.status >= 500 ? 502 : res.status },
      );
    }
    return NextResponse.json({ ok: true, available: true, result: payload });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      available: false,
      error: error instanceof Error ? error.message : 'SAM proxy failed',
      hint: 'Start with: python3 scripts/serve_interactive_sam_agent.py --port 8767',
    }, { status: 503 });
  }
}
