import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import type { MaskBoundaryOverride, MaskHistoryEntry } from '@/types';
import { bboxFromPolygon, isValidMaskOverride } from '@/lib/mask-override';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';

const OVERRIDES_FILE = runtimeDataFile('mask_overrides.json');
const LEGACY_OVERRIDES_FILE = legacyAppDataFile('mask_overrides.json');
const HISTORY_FILE = runtimeDataFile('mask_overrides_history.json');
const HISTORY_LIMIT = 40;

type OverrideStore = Record<string, MaskBoundaryOverride>;
type HistoryStore = Record<string, MaskHistoryEntry[]>;

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

function readHistory(): HistoryStore {
  try {
    if (!fs.existsSync(HISTORY_FILE)) return {};
    const raw = fs.readFileSync(HISTORY_FILE, 'utf-8');
    const parsed = JSON.parse(raw) as HistoryStore;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeHistory(store: HistoryStore) {
  fs.mkdirSync(path.dirname(HISTORY_FILE), { recursive: true });
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(store, null, 2), 'utf-8');
}

function comparableOverride(override: MaskBoundaryOverride): string {
  const rest = { ...override };
  delete rest.updated_at;
  return JSON.stringify(rest);
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
  if (request.nextUrl.searchParams.get('history') === '1') {
    const key = storeKey(patientId, frameId);
    const history = (readHistory()[key] || [])
      .filter((entry) => entry && isValidMaskOverride(entry.override));
    return NextResponse.json({ patientId, frameId, history });
  }
  const store = readStore();
  const override = findOverride(store, patientId, frameId);
  return NextResponse.json({ patientId, frameId, override });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as { override?: MaskBoundaryOverride; action?: string };
    const override = body.override;
    if (!override || !isValidMaskOverride(override)) {
      return NextResponse.json({ error: 'Invalid mask override payload' }, { status: 400 });
    }

    const savedAt = new Date().toISOString();
    const next: MaskBoundaryOverride = {
      ...override,
      roi_bbox: override.roi_bbox || bboxFromPolygon(override.mask_polygon),
      updated_at: savedAt,
      source: override.source || 'manual',
      roi_mode: override.roi_mode || 'predicted',
    };

    const store = readStore();
    const key = storeKey(next.patientId, next.frameId);
    store[key] = next;
    // Also index by patientId for analyze when frame id is omitted.
    store[next.patientId] = next;
    writeStore(store);

    const historyStore = readHistory();
    const history = historyStore[key] || [];
    const action = String(body.action || 'manual_save').slice(0, 80);
    const previous = history[0];
    let historyEntry = previous;
    if (!previous || comparableOverride(previous.override) !== comparableOverride(next)) {
      historyEntry = {
        id: `mask_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        saved_at: savedAt,
        action,
        override: next,
      };
      historyStore[key] = [historyEntry, ...history].slice(0, HISTORY_LIMIT);
      writeHistory(historyStore);
    }

    return NextResponse.json({
      ok: true,
      patientId: next.patientId,
      key,
      override: next,
      history_entry: historyEntry,
    });
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
