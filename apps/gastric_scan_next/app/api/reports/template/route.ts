import fs from 'fs/promises';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';
import {
  createGcUsReportState,
  validateGcUsReportForFinalize,
  GC_US_TEMPLATE_FIELD_DEFINITIONS,
  type GcUsReportState,
  type GcUsReportStatus,
} from '@/lib/gc-us-report-template';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DATA_FILE = runtimeDataFile('template_reports.json');
const LEGACY_DATA_FILE = legacyAppDataFile('template_reports.json');
const INDEX_FILE = runtimeDataFile('template_reports_index.json');

type StoredReport = {
  report_id: string;
  case_id: string;
  patient_id: string;
  patient_label: string;
  status: GcUsReportStatus;
  revision: number;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
  report: GcUsReportState;
};

type ReportStore = Record<string, { current: StoredReport; revisions: StoredReport[] }>;

type ReportMetadata = {
  report_id: string;
  case_id: string;
  patient_id: string;
  patient_label: string;
  status: GcUsReportStatus;
  revision: number;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
  signed_by: string | null;
  template_stage: string;
  changed_fields: string[];
};

function text(value: unknown): string {
  return String(value ?? '').trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isStoredReport(value: unknown): value is StoredReport {
  if (!isRecord(value)) return false;
  return typeof value.report_id === 'string'
    && typeof value.case_id === 'string'
    && typeof value.patient_id === 'string'
    && typeof value.patient_label === 'string'
    && typeof value.status === 'string'
    && typeof value.revision === 'number'
    && typeof value.created_at === 'string'
    && typeof value.updated_at === 'string'
    && (value.finalized_at == null || typeof value.finalized_at === 'string')
    && isRecord(value.report);
}

function isReportStore(value: unknown): value is ReportStore {
  if (!isRecord(value)) return false;
  return Object.values(value).every((entry) => (
    isRecord(entry)
    && isStoredReport(entry.current)
    && Array.isArray(entry.revisions)
    && entry.revisions.every(isStoredReport)
  ));
}

async function backupCorruptFile(file: string): Promise<void> {
  if (file !== DATA_FILE) return;
  try {
    await fs.copyFile(file, `${file}.corrupt-${Date.now()}.json`);
  } catch {
    // A backup is best effort. The read path still recovers with an empty store.
  }
}

async function readStore(): Promise<ReportStore> {
  for (const file of [DATA_FILE, LEGACY_DATA_FILE]) {
    try {
      const raw = await fs.readFile(file, 'utf8');
      const parsed: unknown = JSON.parse(raw);
      if (isReportStore(parsed)) return parsed;
      await backupCorruptFile(file);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        await backupCorruptFile(file);
      }
      // Try the next compatibility location.
    }
  }
  return {};
}

async function writeJsonAtomically(file: string, value: unknown): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
  try {
    await fs.writeFile(temporary, JSON.stringify(value, null, 2), 'utf8');
    const handle = await fs.open(temporary, 'r');
    try {
      await handle.sync();
    } finally {
      await handle.close();
    }
    await fs.rename(temporary, file);
  } finally {
    await fs.unlink(temporary).catch(() => undefined);
  }
}

async function writeStore(store: ReportStore): Promise<void> {
  await writeJsonAtomically(DATA_FILE, store);
  try {
    const index = Object.values(store)
      .map((entry) => entry.revisions.length ? entry.revisions[entry.revisions.length - 1] : entry.current)
      .map((item) => metadata(item))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    await writeJsonAtomically(INDEX_FILE, index);
  } catch {
    // The full store remains authoritative if the optional summary index fails.
  }
}

function reportIdFor(caseId: string): string {
  const safeCaseId = caseId.replace(/[^a-zA-Z0-9_-]/g, '').slice(-18) || 'case';
  return `GUS-${safeCaseId}-${Date.now().toString(36).toUpperCase()}`;
}

function changedFields(previous: StoredReport | null | undefined, current: StoredReport): string[] {
  if (!previous) return ['initial_report'];
  const changed = new Set<string>();
  for (const definition of GC_US_TEMPLATE_FIELD_DEFINITIONS) {
    const before = previous.report.template_fields[definition.id];
    const after = current.report.template_fields[definition.id];
    if (JSON.stringify({
      value: before?.value,
      status: before?.status,
      source: before?.source,
      doctor_override: before?.doctor_override,
    }) !== JSON.stringify({
      value: after?.value,
      status: after?.status,
      source: after?.source,
      doctor_override: after?.doctor_override,
    })) {
      changed.add(definition.id);
    }
  }
  if (previous.report.report.status !== current.report.report.status) changed.add('report.status');
  if (previous.report.report.signed_by !== current.report.report.signed_by) changed.add('report.signed_by');
  if (previous.report.report.export_method !== current.report.report.export_method) changed.add('report.export_method');
  if (previous.report.report_images.length !== current.report.report_images.length) changed.add('report_images');
  return Array.from(changed);
}

function metadata(item: StoredReport, previous?: StoredReport | null): ReportMetadata {
  return {
    report_id: item.report_id,
    case_id: item.case_id,
    patient_id: item.patient_id,
    patient_label: item.patient_label,
    status: item.status,
    revision: item.revision,
    created_at: item.created_at,
    updated_at: item.updated_at,
    finalized_at: item.finalized_at,
    signed_by: item.report.report.signed_by,
    template_stage: text(item.report.template_fields.ct_stage.value) || 'uTx',
    changed_fields: changedFields(previous, item),
  };
}

function revisionMetadata(revisions: StoredReport[]): ReportMetadata[] {
  return revisions.map((item, index) => metadata(item, revisions[index - 1] || null));
}

async function readIndex(): Promise<ReportMetadata[] | null> {
  try {
    const parsed: unknown = JSON.parse(await fs.readFile(INDEX_FILE, 'utf8'));
    if (!Array.isArray(parsed)) return null;
    return parsed.filter((item): item is ReportMetadata => (
      isRecord(item)
      && typeof item.report_id === 'string'
      && typeof item.updated_at === 'string'
      && Array.isArray(item.changed_fields)
    ));
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest) {
  const caseId = text(request.nextUrl.searchParams.get('case_id'));
  const reportId = text(request.nextUrl.searchParams.get('report_id'));
  const revisionParam = text(request.nextUrl.searchParams.get('revision'));
  const requestedRevision = revisionParam && Number.isFinite(Number(revisionParam))
    ? Number(revisionParam)
    : null;

  if (!caseId && !reportId) {
    const indexed = await readIndex();
    if (indexed) return NextResponse.json({ ok: true, reports: indexed });
  }

  const store = await readStore();
  if (caseId) {
    const item = store[caseId]?.current;
    const revisions = store[caseId]?.revisions || [];
    return NextResponse.json({
      ok: true,
      report: item?.report || null,
      metadata: item ? metadata(item, revisions[revisions.length - 2] || null) : null,
      revisions: revisionMetadata(revisions),
    });
  }

  if (reportId) {
    const entry = Object.values(store).find((candidate) => (
      candidate.current.report_id === reportId
      || candidate.revisions.some((item) => item.report_id === reportId)
    ));
    const revisions = entry?.revisions || [];
    const current = entry?.current;
    const item = requestedRevision != null
      ? revisions.find((candidate) => candidate.revision === requestedRevision) || current
      : current;
    const itemIndex = item ? revisions.findIndex((candidate) => candidate.revision === item.revision) : -1;
    return NextResponse.json({
      ok: true,
      report: item?.report || null,
      metadata: item
        ? metadata(item, itemIndex > 0 ? revisions[itemIndex - 1] : null)
        : null,
      revisions: revisionMetadata(revisions),
    });
  }

  const reports = Object.values(store)
    .map((entry) => {
      const revisions = entry.revisions || [];
      return metadata(entry.current, revisions[revisions.length - 2] || null);
    })
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return NextResponse.json({ ok: true, reports });
}

export async function POST(request: NextRequest) {
  let body: {
    action?: 'save_draft' | 'review' | 'finalize';
    case_id?: string;
    patient_id?: string;
    patient_label?: string;
    revision_of?: number | null;
    report?: Partial<GcUsReportState>;
  };
  try {
    body = await request.json() as typeof body;
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON' }, { status: 400 });
  }

  const reportInput = body.report;
  const caseId = text(body.case_id) || text(reportInput?.case_id);
  const patientId = text(body.patient_id);
  const patientLabel = text(body.patient_label) || patientId || caseId;
  const action = body.action || 'save_draft';
  if (!caseId || !reportInput) {
    return NextResponse.json({ ok: false, error: 'case_id and report are required' }, { status: 400 });
  }
  if (action !== 'save_draft' && action !== 'review' && action !== 'finalize') {
    return NextResponse.json({ ok: false, error: 'Unsupported report action' }, { status: 400 });
  }

  const store = await readStore();
  const previous = store[caseId]?.current;
  const revisionOf = body.revision_of == null
    ? null
    : Number.isFinite(Number(body.revision_of))
      ? Number(body.revision_of)
      : null;
  if (previous?.status === 'finalized' && revisionOf !== previous.revision) {
    return NextResponse.json({
      ok: false,
      error: '已签发版本不可直接覆盖，请先开始修订。',
      code: 'FINALIZED_VERSION_LOCKED',
    }, { status: 409 });
  }
  if (revisionOf != null && (!previous || previous.status !== 'finalized' || previous.revision !== revisionOf)) {
    return NextResponse.json({
      ok: false,
      error: '修订基线已变化，请刷新病例后重新开始修订。',
      code: 'REVISION_BASE_MISMATCH',
    }, { status: 409 });
  }
  if (action === 'finalize' && previous?.status !== 'reviewed') {
    return NextResponse.json({
      ok: false,
      error: '请先完成医生复核，再签发报告。',
      code: 'REVIEW_REQUIRED_BEFORE_FINALIZE',
    }, { status: 409 });
  }
  const now = new Date().toISOString();
  const revision = (previous?.revision || 0) + 1;
  const status: GcUsReportStatus = action === 'finalize'
    ? 'finalized'
    : action === 'review'
      ? 'reviewed'
      : 'draft';
  const reportId = previous?.report_id || text(reportInput.report?.report_id) || reportIdFor(caseId);
  const reportForState: GcUsReportState['report'] = {
    prose: reportInput.report?.prose || '',
    source: reportInput.report?.source || 'template',
    doctor_edited: Boolean(reportInput.report?.doctor_edited),
    status,
    report_id: reportId,
    revision,
    signed_by: reportInput.report?.signed_by || null,
    signed_at: action === 'finalize'
      ? (reportInput.report?.signed_at || now)
      : null,
    export_method: reportInput.report?.export_method || null,
  };
  const normalized = createGcUsReportState({
    ...reportInput,
    case_id: caseId,
    report: reportForState,
  });
  if (action === 'review' || action === 'finalize') {
    const validation = validateGcUsReportForFinalize(normalized);
    if (validation.issues.some((issue) => issue.severity === 'error')) {
      return NextResponse.json({
        ok: false,
        error: action === 'finalize'
          ? '报告尚未满足签发条件。'
          : '报告尚未满足复核条件。',
        code: 'REPORT_VALIDATION_FAILED',
        validation,
      }, { status: 422 });
    }
  }
  const item: StoredReport = {
    report_id: reportId,
    case_id: caseId,
    patient_id: patientId || previous?.patient_id || caseId,
    patient_label: patientLabel || previous?.patient_label || caseId,
    status,
    revision,
    created_at: previous?.created_at || now,
    updated_at: now,
    finalized_at: action === 'finalize' ? normalized.report.signed_at : null,
    report: normalized,
  };
  const revisions = [...(store[caseId]?.revisions || []), item].slice(-30);
  store[caseId] = { current: item, revisions };
  await writeStore(store);

  return NextResponse.json({
    ok: true,
    ...metadata(item, revisions[revisions.length - 2] || null),
    report: normalized,
  });
}
