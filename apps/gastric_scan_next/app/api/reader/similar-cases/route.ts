import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DATA_PATH = path.join(
  PROJECT_ROOT,
  'apps/gastric_scan_next/data/reader_similar_cases.json',
);

type SimilarCaseEntry = {
  available: boolean;
  reason?: string;
  basis?: string[];
  clinical_summary?: Record<string, unknown>;
  similar_cases?: Array<Record<string, unknown>>;
  stage_distribution?: Record<string, number>;
};

type SimilarCasePack = {
  memory_version?: string;
  query_mode?: string;
  cases?: Record<string, SimilarCaseEntry>;
};

let cachedPack: SimilarCasePack | null | undefined;

function loadPack(): SimilarCasePack | null {
  if (cachedPack !== undefined) return cachedPack;
  if (!fs.existsSync(DATA_PATH)) {
    cachedPack = null;
    return cachedPack;
  }
  try {
    cachedPack = JSON.parse(fs.readFileSync(DATA_PATH, 'utf-8')) as SimilarCasePack;
  } catch {
    cachedPack = null;
  }
  return cachedPack;
}

export async function GET(request: NextRequest) {
  const caseId = (request.nextUrl.searchParams.get('case_id') || '').trim();
  if (!caseId) {
    return NextResponse.json({ ok: false, error: 'case_id required' }, { status: 400 });
  }
  const pack = loadPack();
  const entry = pack?.cases?.[caseId];
  if (!entry) {
    return NextResponse.json({
      ok: true,
      available: false,
      reason: 'case_not_precomputed',
      case_id: caseId,
    });
  }
  return NextResponse.json({
    ok: true,
    case_id: caseId,
    memory_version: pack?.memory_version,
    query_mode: pack?.query_mode,
    ...entry,
  });
}
