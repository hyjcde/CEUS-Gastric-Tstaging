import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

export const runtime = 'nodejs';

const DATA_FILE = path.join(process.cwd(), 'data', 'reader_agent_results.json');

type Store = Record<string, unknown>;

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

async function readStore(): Promise<Store> {
  try {
    const raw = await fs.readFile(DATA_FILE, 'utf8');
    return JSON.parse(raw) as Store;
  } catch {
    return {};
  }
}

async function writeStore(store: Store) {
  await fs.mkdir(path.dirname(DATA_FILE), { recursive: true });
  await fs.writeFile(DATA_FILE, JSON.stringify(store, null, 2), 'utf8');
}

function resultKey(body: Record<string, unknown>): string {
  const frameId = String(body.frame_id || body.frameId || '').trim();
  const patientId = String(body.patient_id || body.patientId || '').trim();
  const caseId = String(body.case_id || body.caseId || '').trim();
  return frameId || patientId || caseId || `anon-${Date.now()}`;
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: corsHeaders() });
}

/** GET ?frame_id= | ?patient_id= | ?case_id= | ?all=1 */
export async function GET(req: NextRequest) {
  const store = await readStore();
  const sp = req.nextUrl.searchParams;
  if (sp.get('all') === '1') {
    return NextResponse.json({ ok: true, results: store }, { headers: corsHeaders() });
  }
  const key =
    sp.get('frame_id') ||
    sp.get('patient_id') ||
    sp.get('case_id') ||
    '';
  if (!key) {
    return NextResponse.json(
      { ok: false, message: 'Provide frame_id, patient_id, case_id, or all=1' },
      { status: 400, headers: corsHeaders() },
    );
  }
  const hit = store[key] || null;
  return NextResponse.json({ ok: true, key, result: hit }, { headers: corsHeaders() });
}

/** POST body: { frame_id?, patient_id?, case_id?, layer?, mask_polygon?, ... } */
export async function POST(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, message: 'Invalid JSON' }, { status: 400, headers: corsHeaders() });
  }
  const key = resultKey(body);
  const store = await readStore();
  const prev = (store[key] as Record<string, unknown>) || {};
  const next = {
    ...prev,
    ...body,
    key,
    updated_at: new Date().toISOString(),
  };
  store[key] = next;
  // also index by alternate ids
  for (const alt of [body.frame_id, body.patient_id, body.case_id]) {
    const k = String(alt || '').trim();
    if (k && k !== key) store[k] = next;
  }
  await writeStore(store);
  return NextResponse.json({ ok: true, key, result: next }, { headers: corsHeaders() });
}
