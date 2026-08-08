import { NextRequest, NextResponse } from 'next/server';
import {
  filterReaderCases,
  findReaderCase,
  findReaderCaseByPatientId,
  loadReaderCasesBundle,
} from '@/lib/reader/cases-server';
import { clinicalFromReaderUsTable } from '@/lib/reader/us-clinical-server';
import type { ReaderCohort } from '@/lib/reader/types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function publicCase(input: ReturnType<typeof findReaderCase>) {
  if (!input) return null;
  const clinical = clinicalFromReaderUsTable(input);
  const lengthCm = clinical?.tumorSize?.length;
  const thicknessCm = clinical?.tumorSize?.thickness;
  const safeCase = {
    ...input,
    clinical: clinical
      ? {
          ...clinical,
          tumor_size_mm: lengthCm != null && Number(lengthCm) > 0 ? Number(lengthCm) * 10 : undefined,
          tumor_thickness_mm: thicknessCm != null && Number(thicknessCm) > 0 ? Number(thicknessCm) * 10 : undefined,
          length_cm: lengthCm ?? undefined,
          thickness_cm: thicknessCm ?? undefined,
          cea: clinical.biomarkers?.cea ?? undefined,
          ca199: clinical.biomarkers?.ca199 ?? undefined,
        }
      : undefined,
  };
  delete safeCase.reference_pt;
  delete safeCase.reference_lesion_nature;
  return safeCase;
}

export async function GET(request: NextRequest) {
  const cohort = (request.nextUrl.searchParams.get('cohort') || 'all') as ReaderCohort;
  const caseId = request.nextUrl.searchParams.get('case_id') || '';
  const patientId = request.nextUrl.searchParams.get('patient_id') || '';
  const bundle = loadReaderCasesBundle();
  const cases = filterReaderCases(bundle.cases || [], cohort);

  if (caseId || patientId) {
    const found = caseId
      ? findReaderCase(bundle.cases || [], caseId)
      : findReaderCaseByPatientId(bundle.cases || [], patientId);
    if (!found) {
      return NextResponse.json({ ok: false, error: 'case not found' }, { status: 404 });
    }
    return NextResponse.json({
      ok: true,
      created_at: bundle.created_at,
      case: publicCase(found),
    });
  }

  return NextResponse.json({
    ok: true,
    created_at: bundle.created_at,
    schema_version: bundle.schema_version,
    count: cases.length,
    cases: cases.map((c) => ({
      case_id: c.case_id,
      patient_id: c.patient_id,
      display_id: c.display_id,
      study_mode: c.study_mode,
      frame_count: c.frames?.length || 0,
      axis_labels: (c.frames || []).map((f) => f.axis_label).filter(Boolean),
    })),
  });
}
