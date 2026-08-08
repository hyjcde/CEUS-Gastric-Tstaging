import { NextRequest, NextResponse } from 'next/server';
import { getReadingAgentBaseUrl } from '@/lib/reading-agent-url';
import { proxyAgentRequest } from '@/lib/agent-upstream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { ok: false, message: text.slice(0, 500) };
  }
}

async function trySam2Fallback(
  base: string,
  body: Record<string, unknown>,
): Promise<NextResponse | null> {
  try {
    const fallbackRes = await fetch(`${base}/api/sam/interactive-analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120000),
    });
    const fallbackPayload = await parseJsonResponse(fallbackRes);
    if (!fallbackRes.ok || !isRecord(fallbackPayload) || fallbackPayload.ok === false) return null;
    return NextResponse.json({
      ok: true,
      available: true,
      fallback: true,
      result: {
        ...fallbackPayload,
        backend_id: fallbackPayload.backend_id || 'sam2_interactive_fallback',
        fallback_backend: 'sam2_interactive',
      },
    });
  } catch {
    return null;
  }
}

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
    const model = typeof body?.model === 'string' ? body.model : '';
    const sam31Base = String(process.env.SAM31_UPSTREAM || 'http://127.0.0.1:8768').replace(/\/+$/, '');
    const target = model === 'sam31'
      ? `${sam31Base}/api/sam31/static-segment`
      : `${base}/api/sam/interactive-analyze`;
    let res: Response;
    try {
      res = await fetch(target, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(model === 'sam31' ? 180000 : 120000),
      });
    } catch (error) {
      if (model === 'sam31') {
        const fallback = await trySam2Fallback(base, body);
        if (fallback) return fallback;
      }
      throw error;
    }
    const payload = await parseJsonResponse(res);
    if (!res.ok) {
      if (model === 'sam31' && res.status >= 500) {
        const fallback = await trySam2Fallback(base, body);
        if (fallback) return fallback;
      }
      return NextResponse.json(
        {
          ok: false,
          available: true,
          error: `${model === 'sam31' ? 'SAM3.1' : 'SAM'} HTTP ${res.status}`,
          result: payload,
        },
        { status: res.status >= 500 ? 502 : res.status },
      );
    }
    return NextResponse.json({ ok: true, available: true, result: payload });
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'SAM proxy failed';
    return NextResponse.json({
      ok: false,
      available: false,
      error: detail === 'fetch failed' ? 'SAM3.1 and SAM2 upstreams are unavailable' : detail,
      hint: 'Start the local SAM backend with scripts/dev_all.sh',
    }, { status: 503 });
  }
}
