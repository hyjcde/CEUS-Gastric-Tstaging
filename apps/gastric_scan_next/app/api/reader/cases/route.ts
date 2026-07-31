import { NextRequest, NextResponse } from 'next/server';
import { filterReaderCases, findReaderCase, loadReaderCasesBundle } from '@/lib/reader/cases-server';
import type { ReaderCohort } from '@/lib/reader/types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const cohort = (request.nextUrl.searchParams.get('cohort') || 'all') as ReaderCohort;
  const caseId = request.nextUrl.searchParams.get('case_id') || '';
  const bundle = loadReaderCasesBundle();
  const cases = filterReaderCases(bundle.cases || [], cohort);

  if (caseId) {
    const found = findReaderCase(bundle.cases || [], caseId);
    if (!found) {
      return NextResponse.json({ ok: false, error: 'case not found' }, { status: 404 });
    }
    return NextResponse.json({
      ok: true,
      created_at: bundle.created_at,
      case: found,
    });
  }

  return NextResponse.json({
    ok: true,
    created_at: bundle.created_at,
    schema_version: bundle.schema_version,
    count: cases.length,
    cases: cases.map((c) => ({
      case_id: c.case_id,
      display_id: c.display_id,
      study_mode: c.study_mode,
      reference_pt: c.reference_pt,
      reference_lesion_nature: c.reference_lesion_nature,
      frame_count: c.frames?.length || 0,
      axis_labels: (c.frames || []).map((f) => f.axis_label).filter(Boolean),
    })),
  });
}
