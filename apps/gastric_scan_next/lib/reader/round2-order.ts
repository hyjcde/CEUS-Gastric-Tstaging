import fs from 'node:fs';
import path from 'node:path';
import { PROJECT_ROOT } from '@/lib/config';
import { READER_ROUND2_FREEZE_ID } from '@/lib/reader/study-contract';

const ORDER_FILE = path.join(PROJECT_ROOT, 'data/registry/reader_round2_case_order_20260810.csv');

type ReaderOrder = {
  freezeId: string;
  readerId: string;
  orderByCaseId: Map<string, number>;
};

const cache = new Map<string, ReaderOrder | null>();

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === ',' && !quoted) {
      values.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  values.push(current);
  return values;
}

function loadOrder(readerId: string): ReaderOrder | null {
  if (cache.has(readerId)) return cache.get(readerId) || null;
  if (!fs.existsSync(ORDER_FILE)) {
    cache.set(readerId, null);
    return null;
  }
  const lines = fs.readFileSync(ORDER_FILE, 'utf8').split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) {
    cache.set(readerId, null);
    return null;
  }
  const header = parseCsvLine(lines[0]);
  const readerIndex = header.indexOf('reader_id');
  const caseIndex = header.indexOf('case_id');
  const orderIndex = header.indexOf('round2_order') >= 0
    ? header.indexOf('round2_order')
    : header.indexOf('presentation_index');
  const freezeIndex = header.indexOf('freeze_id');
  if (readerIndex < 0 || caseIndex < 0 || orderIndex < 0) {
    cache.set(readerId, null);
    return null;
  }
  const orderByCaseId = new Map<string, number>();
  let freezeId = READER_ROUND2_FREEZE_ID;
  for (const line of lines.slice(1)) {
    const values = parseCsvLine(line);
    if (values[readerIndex] !== readerId) continue;
    const caseId = values[caseIndex]?.trim();
    const order = Number(values[orderIndex]);
    if (!caseId || !Number.isFinite(order)) continue;
    orderByCaseId.set(caseId, order);
    if (freezeIndex >= 0 && values[freezeIndex]) freezeId = values[freezeIndex];
  }
  const result = orderByCaseId.size
    ? { freezeId, readerId, orderByCaseId }
    : null;
  cache.set(readerId, result);
  return result;
}

export function sortReaderRound2Patients<T extends { id: string }>(
  patients: T[],
  readerId?: string,
): { patients: T[]; orderApplied: boolean; freezeId: string } {
  if (!readerId) {
    return { patients, orderApplied: false, freezeId: READER_ROUND2_FREEZE_ID };
  }
  const order = loadOrder(readerId);
  if (!order) {
    return { patients, orderApplied: false, freezeId: READER_ROUND2_FREEZE_ID };
  }
  const sorted = [...patients].sort((left, right) => (
    (order.orderByCaseId.get(left.id) ?? Number.MAX_SAFE_INTEGER)
    - (order.orderByCaseId.get(right.id) ?? Number.MAX_SAFE_INTEGER)
  ));
  return { patients: sorted, orderApplied: true, freezeId: order.freezeId };
}

export function readerRound2CaseMembership(
  readerId: string,
  caseId: string,
): { ok: true; presentationIndex: number; freezeId: string } | { ok: false; reason: string } {
  const normalizedReader = String(readerId || '').trim();
  const normalizedCase = String(caseId || '').trim();
  if (!normalizedReader || !normalizedCase) {
    return { ok: false, reason: 'reader_id and case_id are required for freeze membership' };
  }
  const order = loadOrder(normalizedReader);
  if (!order) {
    return { ok: false, reason: `No frozen Round2 case order for reader ${normalizedReader}` };
  }
  const presentationIndex = order.orderByCaseId.get(normalizedCase);
  if (presentationIndex == null) {
    return {
      ok: false,
      reason: `case_id ${normalizedCase} is not in the frozen Round2 order for ${normalizedReader}`,
    };
  }
  return { ok: true, presentationIndex, freezeId: order.freezeId };
}
