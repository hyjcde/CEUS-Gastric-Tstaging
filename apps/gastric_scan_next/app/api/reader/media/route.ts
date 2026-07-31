import { NextRequest, NextResponse } from 'next/server';
import { getReadingAgentBaseUrl } from '@/lib/reading-agent-url';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Proxy reader-study media from SAM static root (:8767) with range support for video seek. */
export async function GET(request: NextRequest) {
  const rel = request.nextUrl.searchParams.get('rel')?.replace(/^\//, '');
  if (!rel || rel.includes('..')) {
    return NextResponse.json({ error: 'invalid rel' }, { status: 400 });
  }

  const base = getReadingAgentBaseUrl();
  const segments = rel.split('/').map((s) => encodeURIComponent(s)).join('/');
  const v = request.nextUrl.searchParams.get('v');
  const upstreamUrl = `${base}/${segments}${v ? `?v=${encodeURIComponent(v)}` : ''}`;

  const range = request.headers.get('range') || undefined;
  const headers: Record<string, string> = {};
  if (range) headers.Range = range;

  try {
    const upstream = await fetch(upstreamUrl, {
      headers,
      cache: 'no-store',
      signal: AbortSignal.timeout(120000),
    });

    if (!upstream.ok && upstream.status !== 206) {
      return NextResponse.json(
        { error: `upstream HTTP ${upstream.status}`, url: upstreamUrl },
        { status: upstream.status === 404 ? 404 : 502 },
      );
    }

    const outHeaders = new Headers();
    const pass = ['content-type', 'content-length', 'content-range', 'accept-ranges', 'etag', 'last-modified'];
    for (const key of pass) {
      const val = upstream.headers.get(key);
      if (val) outHeaders.set(key, val);
    }
    outHeaders.set('Access-Control-Allow-Origin', '*');
    outHeaders.set('Cross-Origin-Resource-Policy', 'cross-origin');
    outHeaders.set('Cache-Control', 'public, max-age=3600');

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: outHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : 'media proxy failed',
        hint: 'Start SAM server: python3 scripts/serve_interactive_sam_agent.py --port 8767',
      },
      { status: 503 },
    );
  }
}
