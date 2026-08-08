import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import type { LumenOverride } from '@/types';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';

const OVERRIDES_FILE = runtimeDataFile('lumen_overrides.json');
const LEGACY_OVERRIDES_FILE = legacyAppDataFile('lumen_overrides.json');

type OverrideStore = Record<string, LumenOverride>;

function storeKey(patientId: string, frameId?: string | null): string {
  return frameId ? `${patientId}::${frameId}` : patientId;
}

function readStore(): OverrideStore {
  try {
    const file = fs.existsSync(OVERRIDES_FILE) ? OVERRIDES_FILE : LEGACY_OVERRIDES_FILE;
    if (!fs.existsSync(file)) return {};
    const raw = fs.readFileSync(file, 'utf-8');
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

function isValidLumenBBox(value: unknown): value is LumenOverride['lumen_bbox'] {
  if (!value || typeof value !== 'object') return false;
  const box = value as Record<string, unknown>;
  const x1 = Number(box.x1);
  const y1 = Number(box.y1);
  const x2 = Number(box.x2);
  const y2 = Number(box.y2);
  return Number.isFinite(x1) && Number.isFinite(y1) && Number.isFinite(x2) && Number.isFinite(y2) && x2 > x1 && y2 > y1;
}

function isValidLumenOverride(value: unknown): value is LumenOverride {
  if (!value || typeof value !== 'object') return false;
  const v = value as LumenOverride;
  if (typeof v.patientId !== 'string' || !v.patientId) return false;
  if (typeof v.imageWidth !== 'number' || typeof v.imageHeight !== 'number') return false;
  if (v.imageWidth <= 0 || v.imageHeight <= 0) return false;
  if (!isValidLumenBBox(v.lumen_bbox)) return false;
  if (v.lumen_polygon !== undefined) {
    if (!Array.isArray(v.lumen_polygon) || v.lumen_polygon.length < 3) return false;
    if (!v.lumen_polygon.every(
      (pt) => Array.isArray(pt) && pt.length >= 2
        && Number.isFinite(Number(pt[0])) && Number.isFinite(Number(pt[1])),
    )) return false;
  }
  return true;
}

function findOverride(store: OverrideStore, patientId: string, frameId?: string | null): LumenOverride | null {
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
    const body = await request.json() as { override?: LumenOverride };
    const override = body.override;
    if (!override || !isValidLumenOverride(override)) {
      return NextResponse.json({ error: 'Invalid lumen override payload' }, { status: 400 });
    }

    const next: LumenOverride = {
      ...override,
      lumen_bbox: {
        x1: Math.round(Number(override.lumen_bbox.x1)),
        y1: Math.round(Number(override.lumen_bbox.y1)),
        x2: Math.round(Number(override.lumen_bbox.x2)),
        y2: Math.round(Number(override.lumen_bbox.y2)),
      },
      updated_at: new Date().toISOString(),
      source: override.source || 'manual',
      lumen_mask_type: override.lumen_mask_type || (
        override.lumen_polygon && override.lumen_polygon.length >= 3
          ? 'sam31_polygon'
          : 'bbox_proxy'
      ),
    };

    const store = readStore();
    const key = storeKey(next.patientId, next.frameId);
    store[key] = next;
    store[next.patientId] = next;
    writeStore(store);

    return NextResponse.json({ ok: true, patientId: next.patientId, key, override: next });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to save lumen override';
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
