import { NextRequest, NextResponse } from 'next/server';

/**
 * Public edge → workstation compute bridge.
 *
 * Local/LAN keeps the existing in-process routes. The public service sets
 * NEXT_AGENT_UPSTREAM to the loopback end of an SSH reverse tunnel so Python,
 * DINO and SAM workloads stay on the workstation.
 */
export async function proxyAgentRequest(
  request: NextRequest,
  upstreamPath = request.nextUrl.pathname,
): Promise<NextResponse | null> {
  const base = String(process.env.NEXT_AGENT_UPSTREAM || '').replace(/\/+$/, '');
  if (!base) return null;

  const target = `${base}${upstreamPath}${request.nextUrl.search}`;
  const headers = new Headers();
  const contentType = request.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  const accept = request.headers.get('accept');
  if (accept) headers.set('accept', accept);

  const body = request.method === 'GET' || request.method === 'HEAD'
    ? undefined
    : Buffer.from(await request.arrayBuffer());
  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout( tenMinutes()),
    });
    const outputHeaders = new Headers();
    for (const name of ['content-type', 'content-length', 'content-range', 'accept-ranges']) {
      const value = response.headers.get(name);
      if (value) outputHeaders.set(name, value);
    }
    outputHeaders.set('Cache-Control', 'no-store');
    return new NextResponse(response.body, {
      status: response.status,
      headers: outputHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        available: false,
        error: error instanceof Error ? error.message : 'workstation Agent upstream unavailable',
        upstream: base,
      },
      { status: 503 },
    );
  }
}

function tenMinutes(): number {
  return 10 * 60 * 1000;
}
