import { getDicomDir, parseCohortYear } from '@/lib/config';
import fs from 'fs';
import { NextRequest, NextResponse } from 'next/server';

/**
 * GET /api/dicom?patient_id=1048931&cohort=2024&treatment=surgery
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const patientId = searchParams.get('patient_id');
  const cohortYear = parseCohortYear(searchParams.get('cohort'));
  if (!patientId) {
    return NextResponse.json({ error: 'patient_id is required' }, { status: 400 });
  }

  const dicomDir = getDicomDir(cohortYear);
  if (!dicomDir || !fs.existsSync(dicomDir)) {
    return NextResponse.json({ frames: [], total: 0, dicomDir: dicomDir ?? null });
  }

  const allFiles = fs.readdirSync(dicomDir);
  const prefix = `${patientId}-`;
  const dcmFiles = allFiles
    .filter((f) => f.startsWith(prefix) && (f.endsWith('.dcm') || f.endsWith('.jpg') || f.endsWith('.jpeg')))
    .sort((a, b) => {
      const numA = parseInt(a.replace(prefix, '').split('.')[0] ?? '0', 10);
      const numB = parseInt(b.replace(prefix, '').split('.')[0] ?? '0', 10);
      return numA - numB;
    });

  const cohortParam = searchParams.get('cohort') || cohortYear;
  const frames = dcmFiles.map((filename, idx) => ({
    filename,
    index: idx,
    isDicom: filename.endsWith('.dcm'),
    url: `/api/dicom/serve?filename=${encodeURIComponent(filename)}&cohort=${cohortParam}`,
  }));

  return NextResponse.json({ frames, total: frames.length, dicomDir });
}
