import { NextRequest, NextResponse } from 'next/server';
import { proxyAgentRequest } from '@/lib/agent-upstream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DEFAULT_UPSTREAM = 'http://127.0.0.1:8770';

function upstreamBase(): string {
  return String(process.env.NNINTERACTIVE_UPSTREAM || DEFAULT_UPSTREAM).replace(/\/+$/, '');
}

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

export async function GET(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = upstreamBase();
  try {
    const response = await fetch(`${base}/api/nninteractive/status`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(4000),
    });
    const payload = await parseJsonResponse(response);
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        available: false,
        error: error instanceof Error ? error.message : 'nnInteractive bridge unreachable',
        upstream: base,
        hint: 'Start scripts/serve_nninteractive_agent.py after configuring the remote GPU server',
      },
      { status: 503 },
    );
  }
}

export async function POST(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const base = upstreamBase();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);
  const onAbort = () => controller.abort();
  request.signal.addEventListener('abort', onAbort);
  try {
    const body = await request.arrayBuffer();
    const response = await fetch(`${base}/api/nninteractive/refine`, {
      method: 'POST',
      headers: { 'Content-Type': request.headers.get('content-type') || 'application/json' },
      body,
      signal: controller.signal,
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      return NextResponse.json(
        {
          ok: false,
          available: response.status !== 503,
          error: `nnInteractive bridge HTTP ${response.status}`,
          result: payload,
        },
        { status: response.status },
      );
    }
    if (!isRecord(payload) || payload.ok === false) {
      return NextResponse.json(payload, { status: 502 });
    }
    return NextResponse.json({
      ok: true,
      available: true,
      result: payload,
    });
  } catch (error) {
    const aborted = request.signal.aborted
      || (error instanceof Error && error.name === 'AbortError');
    return NextResponse.json(
      {
        ok: false,
        available: false,
        error: aborted
          ? 'nnInteractive request aborted'
          : (error instanceof Error ? error.message : 'nnInteractive proxy failed'),
        hint: 'Start scripts/serve_nninteractive_agent.py and the official nninteractive-server',
      },
      { status: aborted ? 499 : 503 },
    );
  } finally {
    clearTimeout(timeout);
    request.signal.removeEventListener('abort', onAbort);
  }
}
