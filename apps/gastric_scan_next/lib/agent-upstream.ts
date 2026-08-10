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
  if (!base || shouldHandleLocally(upstreamPath)) return null;

  const target = `${base}${upstreamPath}${request.nextUrl.search}`;
  const headers = new Headers();
  const contentType = request.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  const accept = request.headers.get('accept');
  if (accept) headers.set('accept', accept);
  // The public SSH reverse tunnel can surface a locked response body when
  // keep-alive is reused for large JSON segmentation requests.
  headers.set('connection', 'close');

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
    const expectedJson = expectsJsonAgentResponse(upstreamPath);
    const contentType = response.headers.get('content-type') || '';
    const structuredResponse = expectedJson || /application\/json/i.test(contentType);
    let responseBody: BodyInit | null = response.body;
    let responseStatus = response.status;
    let responseContentType = contentType;
    let preserveLength = true;

    // Reading JSON responses before constructing NextResponse avoids passing a
    // disturbed or locked fetch stream through the public edge. It also turns
    // an HTML proxy error page into a JSON error that the client can display.
    if (structuredResponse) {
      const text = await response.text();
      if (expectedJson && !/json/i.test(contentType)) {
        responseStatus = response.ok ? 502 : response.status;
        responseContentType = 'application/json; charset=utf-8';
        responseBody = JSON.stringify({
          ok: false,
          available: false,
          error: 'Agent upstream returned a non-JSON response',
          upstream_status: response.status,
          upstream_content_type: contentType || null,
          upstream_body_prefix: text.slice(0, 500),
        });
        preserveLength = false;
      } else {
        responseBody = text;
      }
    }

    const outputHeaders = new Headers();
    if (responseContentType) outputHeaders.set('content-type', responseContentType);
    if (preserveLength) {
      for (const name of ['content-length', 'content-range', 'accept-ranges']) {
        const value = response.headers.get(name);
        if (value) outputHeaders.set(name, value);
      }
    }
    outputHeaders.set('Cache-Control', 'no-store');
    return new NextResponse(responseBody, {
      status: responseStatus,
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

function expectsJsonAgentResponse(pathname: string): boolean {
  // Artifact bytes are binary images/files — never force JSON parsing.
  if (/^\/api\/agent\/artifacts(?:\/|$)/i.test(pathname)) return false;
  return /^\/api\/(?:agent\/(?:sam-interactive|lesion-segmentation|video\/propagate|video\/keyframes|lumen-detection|nninteractive|dino\/features)|explainable\/analyze)(?:\/|$)/i.test(
    pathname,
  );
}

function shouldHandleLocally(pathname: string): boolean {
  const configured = String(process.env.NEXT_AGENT_LOCAL_PATHS || '');
  if (!configured) return false;
  return configured
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
    .some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function tenMinutes(): number {
  return 10 * 60 * 1000;
}
