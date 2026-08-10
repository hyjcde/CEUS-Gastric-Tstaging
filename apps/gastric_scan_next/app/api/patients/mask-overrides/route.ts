import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import type { LumenOverride, MaskBoundaryOverride, MaskHistoryEntry } from '@/types';
import { bboxFromPolygon, isValidMaskOverride } from '@/lib/mask-override';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';
import { resolveDoctorSession } from '@/lib/reader/doctor-account-store';
import { normalizeReaderId, resolveAuthenticatedReader } from '@/lib/reader/study-auth';

const OVERRIDES_FILE = runtimeDataFile('mask_overrides.json');
const LEGACY_OVERRIDES_FILE = legacyAppDataFile('mask_overrides.json');
const HISTORY_FILE = runtimeDataFile('mask_overrides_history.json');
const HISTORY_LIMIT = 40;

type OverrideStore = Record<string, MaskBoundaryOverride>;
type HistoryStore = Record<string, MaskHistoryEntry[]>;

function storeKey(patientId: string, frameId?: string | null, readerId?: string | null): string {
  const base = frameId ? `${patientId}::${frameId}` : patientId;
  const reader = normalizeReaderId(readerId);
  return reader ? `${reader}::${base}` : base;
}

function resolveReaderId(request: NextRequest, explicit?: string | null): string {
  const doctor = resolveDoctorSession(request.headers);
  if (doctor.ok) return doctor.account.account_id;
  const research = resolveAuthenticatedReader(request.headers);
  if (research.ok) return research.readerId;
  return normalizeReaderId(explicit || request.nextUrl.searchParams.get('readerId'));
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

function comparableLumenOverride(override: LumenOverride | undefined): string {
  if (!override) return '';
  const rest = { ...override };
  delete rest.updated_at;
  return JSON.stringify(rest);
}

function normalizeVideoFrames(frames: MaskBoundaryOverride['video_frames']) {
  if (!frames) return undefined;
  return frames.map((frame) => ({
    ...frame,
    roi_bbox: frame.roi_bbox || bboxFromPolygon(frame.mask_polygon),
    lumen_bbox: frame.lumen_bbox
      || (frame.lumen_polygon ? bboxFromPolygon(frame.lumen_polygon) : undefined),
  }));
}

function normalizeOverride(override: MaskBoundaryOverride): MaskBoundaryOverride {
  return {
    ...override,
    video_frames: normalizeVideoFrames(override.video_frames),
  };
}

function findOverride(
  store: OverrideStore,
  patientId: string,
  frameId?: string | null,
  readerId?: string | null,
): MaskBoundaryOverride | null {
  if (readerId) {
    if (frameId) {
      const keyed = store[storeKey(patientId, frameId, readerId)];
      if (keyed) return keyed;
    }
    const patientKeyed = store[storeKey(patientId, null, readerId)];
    if (patientKeyed) return patientKeyed;
  }
  // Legacy shared fallback only when the caller has no account yet.
  if (!readerId) {
    if (frameId) {
      const keyed = store[storeKey(patientId, frameId)];
      if (keyed) return keyed;
    }
    return store[patientId] ?? store[storeKey(patientId)] ?? null;
  }
  return null;
}

export async function GET(request: NextRequest) {
  const patientId = request.nextUrl.searchParams.get('patientId');
  const frameId = request.nextUrl.searchParams.get('frameId');
  const readerId = resolveReaderId(request);
  if (!patientId) {
    return NextResponse.json({ error: 'patientId is required' }, { status: 400 });
  }
  if (request.nextUrl.searchParams.get('history') === '1') {
    const key = storeKey(patientId, frameId, readerId || undefined);
    const history = (readHistory()[key] || [])
      .filter((entry) => entry && isValidMaskOverride(entry.override) && !entry.deleted_at)
      .map((entry) => ({ ...entry, override: normalizeOverride(entry.override) }));
    return NextResponse.json({ patientId, frameId, readerId: readerId || null, history });
  }
  const store = readStore();
  const override = findOverride(store, patientId, frameId, readerId || undefined);
  return NextResponse.json({
    patientId,
    frameId,
    readerId: readerId || null,
    override: override ? normalizeOverride(override) : null,
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as {
      override?: MaskBoundaryOverride;
      lumen_override?: LumenOverride;
      action?: string;
      reader_id?: string;
    };
    const override = body.override ? normalizeOverride(body.override) : undefined;
    if (!override || !isValidMaskOverride(override)) {
      return NextResponse.json({ error: 'Invalid mask override payload' }, { status: 400 });
    }
    const readerId = resolveReaderId(request, body.reader_id);

    const savedAt = new Date().toISOString();
    const next: MaskBoundaryOverride = {
      ...override,
      roi_bbox: override.roi_bbox || bboxFromPolygon(override.mask_polygon),
      updated_at: savedAt,
      source: override.source || 'manual',
      roi_mode: override.roi_mode || 'predicted',
      reviewer_id: readerId || override.reviewer_id,
    };

    const store = readStore();
    const key = storeKey(next.patientId, next.frameId, readerId || undefined);
    store[key] = next;
    // Also index by account+patient for analyze when frame id is omitted.
    store[storeKey(next.patientId, null, readerId || undefined)] = next;
    if (!readerId) {
      store[next.patientId] = next;
    }
    writeStore(store);

    const historyStore = readHistory();
    const history = (historyStore[key] || []).filter((entry) => !entry.deleted_at);
    const action = String(body.action || 'manual_save').slice(0, 80);
    const lumenOverride = body.lumen_override
      && typeof body.lumen_override === 'object'
      && body.lumen_override.patientId === next.patientId
      ? body.lumen_override
      : undefined;
    const previous = history[0];
    let historyEntry = previous;
    if (
      !previous
      || comparableOverride(previous.override) !== comparableOverride(next)
      || comparableLumenOverride(previous.lumen_override) !== comparableLumenOverride(lumenOverride)
    ) {
      historyEntry = {
        id: `mask_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        saved_at: savedAt,
        action,
        override: next,
        lumen_override: lumenOverride,
        owner_account_id: readerId || undefined,
      };
      historyStore[key] = [historyEntry, ...history].slice(0, HISTORY_LIMIT);
      writeHistory(historyStore);
    }

    return NextResponse.json({
      ok: true,
      patientId: next.patientId,
      readerId: readerId || null,
      key,
      override: next,
      lumen_override: lumenOverride,
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
  const historyId = request.nextUrl.searchParams.get('historyId');
  const readerId = resolveReaderId(request);
  if (!patientId) {
    return NextResponse.json({ error: 'patientId is required' }, { status: 400 });
  }

  if (historyId) {
    if (!readerId) {
      return NextResponse.json({ error: 'Login required to delete personal history' }, { status: 401 });
    }
    const key = storeKey(patientId, frameId, readerId);
    const historyStore = readHistory();
    const history = historyStore[key] || [];
    const idx = history.findIndex((entry) => entry.id === historyId);
    if (idx < 0) {
      return NextResponse.json({ error: 'History entry not found' }, { status: 404 });
    }
    history[idx] = {
      ...history[idx],
      deleted_at: new Date().toISOString(),
    };
    historyStore[key] = history;
    writeHistory(historyStore);
    return NextResponse.json({
      ok: true,
      patientId,
      frameId,
      readerId,
      historyId,
      deleted: true,
    });
  }

  const store = readStore();
  if (readerId) {
    if (frameId) delete store[storeKey(patientId, frameId, readerId)];
    delete store[storeKey(patientId, null, readerId)];
  } else {
    if (frameId) delete store[storeKey(patientId, frameId)];
    delete store[patientId];
  }
  writeStore(store);
  return NextResponse.json({ ok: true, patientId, frameId, readerId: readerId || null });
}
