import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Serve generated keyframe thumbs under apps/gastric_scan_next/data/keyframe_tmp only. */
export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get('path') || '';
  if (!raw) return NextResponse.json({ error: 'path required' }, { status: 400 });
  const resolved = path.resolve(raw);
  const allowedRoot = path.resolve(path.join(process.cwd(), 'data', 'keyframe_tmp'));
  if (!resolved.startsWith(allowedRoot + path.sep) && resolved !== allowedRoot) {
    return NextResponse.json({ error: 'path not allowed' }, { status: 403 });
  }
  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ error: 'not found' }, { status: 404 });
  }
  const buf = fs.readFileSync(resolved);
  return new NextResponse(buf, {
    headers: {
      'Content-Type': 'image/jpeg',
      'Cache-Control': 'private, max-age=60',
    },
  });
}
