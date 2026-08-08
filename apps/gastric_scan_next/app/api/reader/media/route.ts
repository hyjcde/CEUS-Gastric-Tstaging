import fs from 'node:fs';
import path from 'node:path';
import { Readable } from 'node:stream';
import { NextRequest, NextResponse } from 'next/server';
import { getReadingAgentBaseUrl } from '@/lib/reading-agent-url';
import { PROJECT_ROOT } from '@/lib/config';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function localMediaPath(rel: string): string | null {
  const root = path.resolve(
    process.env.READER_MEDIA_ROOT || path.join(PROJECT_ROOT, 'docs/clinical_validation/reader_study_v150'),
  );
  const candidate = path.resolve(root, rel);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) return null;
  try {
    return fs.statSync(candidate).isFile() ? candidate : null;
  } catch {
    return null;
  }
}

function localMediaResponse(request: NextRequest, filePath: string): NextResponse {
  const stat = fs.statSync(filePath);
  const range = request.headers.get('range');
  let start = 0;
  let end = stat.size - 1;
  let status = 200;
  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(range);
    if (match) {
      start = match[1] ? Number(match[1]) : Math.max(0, stat.size - Number(match[2] || 0));
      end = match[2] ? Number(match[2]) : end;
      if (start < 0 || end >= stat.size || start > end) {
        return new NextResponse(null, { status: 416, headers: { 'Content-Range': `bytes */${stat.size}` } });
      }
      status = 206;
    }
  }
  const length = end - start + 1;
  const stream = fs.createReadStream(filePath, { start, end });
  const headers = new Headers({
    'Content-Type': 'video/mp4',
    'Content-Length': String(length),
    'Accept-Ranges': 'bytes',
    'Cross-Origin-Resource-Policy': 'cross-origin',
    'Cache-Control': 'public, max-age=3600',
  });
  if (status === 206) headers.set('Content-Range', `bytes ${start}-${end}/${stat.size}`);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, { status, headers });
}

/** Serve copied reader media locally in production; fall back to the GPU workstation agent in LAN dev. */
export async function GET(request: NextRequest) {
  const rel = request.nextUrl.searchParams.get('rel')?.replace(/^\//, '');
  if (!rel || rel.includes('..')) {
    return NextResponse.json({ error: 'invalid rel' }, { status: 400 });
  }

  const localPath = localMediaPath(rel);
  if (localPath) return localMediaResponse(request, localPath);

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
