import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Serve generated keyframe thumbs from the runtime directory, with legacy read compatibility. */
export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get('path') || '';
  if (!raw) return NextResponse.json({ error: 'path required' }, { status: 400 });
  const resolved = path.resolve(raw);
  const allowedRoots = [
    path.resolve(runtimeDataFile('keyframe_tmp')),
    path.resolve(legacyAppDataFile('keyframe_tmp')),
  ];
  const isAllowed = allowedRoots.some((root) => {
    const relative = path.relative(root, resolved);
    return relative && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
  });
  if (!isAllowed) {
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
