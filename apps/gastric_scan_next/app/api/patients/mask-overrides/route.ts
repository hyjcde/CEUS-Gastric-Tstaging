import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import type { MaskBoundaryOverride } from '@/types';
import { bboxFromPolygon, isValidMaskOverride } from '@/lib/mask-override';

const OVERRIDES_FILE = path.join(process.cwd(), 'data', 'mask_overrides.json');

type OverrideStore = Record<string, MaskBoundaryOverride>;

function storeKey(patientId: string, frameId?: string | null): string {
  return frameId ? `${patientId}::${frameId}` : patientId;
}

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

function findOverride(store: OverrideStore, patientId: string, frameId?: string | null): MaskBoundaryOverride | null {
  if (frameId) {
    const keyed = store[storeKey(patientId, frameId)];
    if (keyed) return keyed;
  }
  return store[patientId] ?? store[storeKey(patientId)] ?? null;
}

export async function GET(request: NextRequest) {
  const patientId = request.nextUrl.searchParams.get('patientId');
  const frameId = request.nextUrl.searchParams.get('frameId');
  if (!patientId) {
    return NextResponse.json({ error: 'patientId is required' }, { status: 400 });
  }
  const store = readStore();
  const override = findOverride(store, patientId, frameId);
  return NextResponse.json({ patientId, frameId, override });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as { override?: MaskBoundaryOverride };
    const override = body.override;
    if (!override || !isValidMaskOverride(override)) {
      return NextResponse.json({ error: 'Invalid mask override payload' }, { status: 400 });
    }

    const next: MaskBoundaryOverride = {
      ...override,
      roi_bbox: override.roi_bbox || bboxFromPolygon(override.mask_polygon),
      updated_at: new Date().toISOString(),
      source: override.source || 'manual',
      roi_mode: override.roi_mode || 'predicted',
    };

    const store = readStore();
    const key = storeKey(next.patientId, next.frameId);
    store[key] = next;
    // Also index by patientId for analyze when frame id is omitted.
    store[next.patientId] = next;
    writeStore(store);

    return NextResponse.json({ ok: true, patientId: next.patientId, key, override: next });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to save mask override';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const patientId = request.nextUrl.searchParams.get('patientId');
  const frameId = request.nextUrl.searchParams.get('frameId');
  if (!patientId) {
    return NextResponse.json({ error: 'patientId is required' }, { status: 400 });
  }

  const store = readStore();
  if (frameId) {
    delete store[storeKey(patientId, frameId)];
  }
  delete store[patientId];
  writeStore(store);
  return NextResponse.json({ ok: true, patientId, frameId });
}
