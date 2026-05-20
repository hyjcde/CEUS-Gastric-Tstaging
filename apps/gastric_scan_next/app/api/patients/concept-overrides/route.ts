import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { ConceptState } from '@/types';

const OVERRIDES_FILE = path.join(process.cwd(), 'data', 'concept_overrides.json');

type OverrideStore = Record<string, ConceptState>;

function readStore(): OverrideStore {
  try {
    if (!fs.existsSync(OVERRIDES_FILE)) return {};
    const raw = fs.readFileSync(OVERRIDES_FILE, 'utf-8');
    const parsed = JSON.parse(raw) as OverrideStore;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(store: OverrideStore) {
  fs.mkdirSync(path.dirname(OVERRIDES_FILE), { recursive: true });
  fs.writeFileSync(OVERRIDES_FILE, JSON.stringify(store, null, 2), 'utf-8');
}

function isValidConceptState(value: unknown): value is ConceptState {
  if (!value || typeof value !== 'object') return false;
  const keys: (keyof ConceptState)[] = [
    'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7',
    'differentiation', 'lauren', 'vascularInvasion', 'neuralInvasion',
  ];
  return keys.every((key) => typeof (value as ConceptState)[key] === 'number');
}

export async function GET(request: NextRequest) {
  const patientId = request.nextUrl.searchParams.get('patientId');
  if (!patientId) {
    return NextResponse.json({ error: 'patientId is required' }, { status: 400 });
  }

  const store = readStore();
  const state = store[patientId] ?? null;
  return NextResponse.json({ patientId, state });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as { patientId?: string; state?: ConceptState };
    const { patientId, state } = body;

    if (!patientId || !state) {
      return NextResponse.json({ error: 'patientId and state are required' }, { status: 400 });
    }
    if (!isValidConceptState(state)) {
      return NextResponse.json({ error: 'Invalid concept state payload' }, { status: 400 });
    }

    const store = readStore();
    store[patientId] = state;
    writeStore(store);

    return NextResponse.json({ ok: true, patientId });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to save override';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const patientId = request.nextUrl.searchParams.get('patientId');
  if (!patientId) {
    return NextResponse.json({ error: 'patientId is required' }, { status: 400 });
  }

  const store = readStore();
  delete store[patientId];
  writeStore(store);
  return NextResponse.json({ ok: true, patientId });
}
