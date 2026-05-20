import { getDicomDir, parseCohortYear } from '@/lib/config';
import fs from 'fs';
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';

/**
 * GET /api/dicom/serve?filename=1048931-1.dcm&cohort=2024
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filename = searchParams.get('filename');
  const cohortYear = parseCohortYear(searchParams.get('cohort'));
  if (!filename) {
    return NextResponse.json({ error: 'filename is required' }, { status: 400 });
  }

  const dicomDir = getDicomDir(cohortYear);
  if (!dicomDir) {
    return NextResponse.json({ error: 'DICOM directory not configured for this cohort' }, { status: 404 });
  }

  const safeFilename = path.basename(decodeURIComponent(filename));
  const filePath = path.join(dicomDir, safeFilename);
  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: `File not found: ${safeFilename}` }, { status: 404 });
  }

  const fileBuffer = fs.readFileSync(filePath);
  let contentType = 'application/dicom';
  if (safeFilename.endsWith('.jpg') || safeFilename.endsWith('.jpeg')) {
    contentType = 'image/jpeg';
  }

  return new NextResponse(fileBuffer, {
    headers: {
      'Content-Type': contentType,
      'Cache-Control': 'public, max-age=3600',
      'Content-Length': fileBuffer.length.toString(),
    },
  });
}
