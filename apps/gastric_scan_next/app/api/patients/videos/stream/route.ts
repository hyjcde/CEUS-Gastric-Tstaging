import { Readable } from 'stream';
import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import { isUnderAllowedRoot } from '@/lib/video-stream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MIME: Record<string, string> = {
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.mov': 'video/quicktime',
  '.mkv': 'video/x-matroska',
  '.avi': 'video/x-msvideo',
};

function asWebStream(nodeStream: fs.ReadStream): ReadableStream {
  return Readable.toWeb(nodeStream) as ReadableStream;
}

/**
 * Stream patient video from allowlisted dataset/raw paths (no upload).
 * GET /api/patients/videos/stream?rel=dataset/internal/.../676059_(1).mp4
 * Supports HTTP Range for scrubbing in <video>.
 */
export async function GET(request: NextRequest) {
  const rel = (request.nextUrl.searchParams.get('rel') || '').trim();
  if (!rel || rel.includes('..')) {
    return NextResponse.json({ error: 'rel required' }, { status: 400 });
  }

  const abs = path.resolve(PROJECT_ROOT, rel);
  if (!isUnderAllowedRoot(abs) || !fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
    return NextResponse.json({ error: 'video not found or not allowed' }, { status: 404 });
  }

  const size = fs.statSync(abs).size;
  const ext = path.extname(abs).toLowerCase();
  const contentType = MIME[ext] || 'application/octet-stream';
  const range = request.headers.get('range');

  if (range) {
    const m = /bytes=(\d*)-(\d*)/.exec(range);
    if (!m) {
      return new NextResponse(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
    }
    const start = m[1] ? Number(m[1]) : 0;
    let end = m[2] ? Number(m[2]) : size - 1;
    if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= size) {
      return new NextResponse(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
    }
    end = Math.min(end, size - 1);
    const chunkSize = end - start + 1;
    const stream = fs.createReadStream(abs, { start, end });
    return new NextResponse(asWebStream(stream), {
      status: 206,
      headers: {
        'Content-Range': `bytes ${start}-${end}/${size}`,
        'Accept-Ranges': 'bytes',
        'Content-Length': String(chunkSize),
        'Content-Type': contentType,
        'Cache-Control': 'private, max-age=60',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Content-Range, Accept-Ranges, Content-Length',
        'Cross-Origin-Resource-Policy': 'cross-origin',
      },
    });
  }

  const stream = fs.createReadStream(abs);
  return new NextResponse(asWebStream(stream), {
    status: 200,
    headers: {
      'Content-Length': String(size),
      'Accept-Ranges': 'bytes',
      'Content-Type': contentType,
      'Cache-Control': 'private, max-age=60',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Expose-Headers': 'Content-Range, Accept-Ranges, Content-Length',
      'Cross-Origin-Resource-Policy': 'cross-origin',
    },
  });
}
