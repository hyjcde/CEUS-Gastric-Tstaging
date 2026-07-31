import { NextRequest, NextResponse } from 'next/server';
import { getVideoMap, getVideosForPatient } from '@/lib/video-index';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** List videos for a patient (fuzzy) or sample catalog for boundary-edit video mode. */
export async function GET(request: NextRequest) {
  const patientId = (request.nextUrl.searchParams.get('patientId') || '').trim();
  const listAll = request.nextUrl.searchParams.get('list') === '1';
  const limit = Math.min(Number(request.nextUrl.searchParams.get('limit') || 40), 200);

  if (patientId) {
    const exact = getVideosForPatient(patientId);
    if (exact.length) {
      return NextResponse.json({
        ok: true,
        patientId,
        videos: exact.slice(0, limit),
        match: 'exact',
        source: 'crop_ui_or_public',
      });
    }
    // Fuzzy: any catalog entry whose filename / key contains patientId digits
    const digits = patientId.replace(/\D/g, '');
    const map = getVideoMap();
    const fuzzy: typeof exact = [];
    for (const [key, videos] of map.entries()) {
      if (
        key === patientId
        || (digits && (key.includes(digits) || videos.some((v) => v.filename.includes(digits))))
      ) {
        fuzzy.push(...videos);
      }
    }
    return NextResponse.json({
      ok: true,
      patientId,
      videos: fuzzy.slice(0, limit),
      match: fuzzy.length ? 'fuzzy' : 'none',
      source: 'crop_ui_or_public',
    });
  }

  if (listAll) {
    const map = getVideoMap();
    const videos = [];
    for (const [key, list] of map.entries()) {
      for (const v of list) {
        videos.push({ patient_key: key, ...v });
        if (videos.length >= limit) break;
      }
      if (videos.length >= limit) break;
    }
    return NextResponse.json({ ok: true, count: videos.length, videos });
  }

  return NextResponse.json({ ok: false, error: 'patientId or list=1 required' }, { status: 400 });
}
