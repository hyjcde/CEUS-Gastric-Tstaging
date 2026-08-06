'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, FileText, Pencil, RotateCcw } from 'lucide-react';
import {
  GC_US_REPORT_SCHEMA_VERSION,
  GC_US_REPORT_TEMPLATE_ID,
  applyGcUsDoctorOverride,
  buildGcUsReport,
  createGcUsReportState,
  deriveGcUsSigns,
  normalizeGcUsStage,
  type GcUsField,
  type GcUsDoctorAction,
  type GcUsEvidenceProvenance,
  type GcUsReportState,
  type GcUsSigns,
  type GcUsStageBand,
} from '@/lib/gc-us-report-template';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';

const SIGN_OPTIONS: Record<string, string[]> = {
  layer_structure: [
    '层次结构清晰',
    '黏膜/黏膜下层（T1）',
    '固有肌层（T2）',
    '浆膜下层（T3）',
    '浆膜连续性中断（T4a）',
    '邻近器官侵犯（T4b）',
    '局部受累，结构尚可辨',
    '结构紊乱',
    '连续性可疑破坏',
    '不可辨',
  ],
  morphology: ['浅表隆起型', '局限隆起型', '局部浸润型', '溃疡浸润型', '巨大浸润型', '未评估'],
  boundary: ['边界清晰、规则', '边界部分欠清', '边界不规则', '外侵样改变，边界消失倾向', '未评估'],
  growth_pattern: ['膨胀型', '局部浸润性', '明显浸润性', '跨壁向外侵犯倾向', '未评估'],
  serosa_change: ['浆膜连续光滑', '浆膜面欠光整', '浆膜连续性可疑破坏', '浆膜连续性中断', '未评估'],
  perigastric_tissue: ['胃周组织未见明显异常改变', '胃周脂肪间隙清晰', '胃周脂肪间隙欠清', '胃周脂肪间隙异常改变', '未评估'],
};

const LABELS: Record<string, string> = {
  length: '肿瘤长径',
  thickness: '肿瘤厚度',
  layer_structure: '胃壁层次结构',
  morphology: '肿瘤形态',
  boundary: '肿瘤边界',
  growth_pattern: '生长方式',
  serosa_change: '浆膜改变',
  perigastric_tissue: '胃周组织',
};

const SOURCE_LABELS: Record<string, string> = {
  clinical: '临床字段',
  live_contour: '本帧轮廓',
  pixel: '像素辅助',
  model: '模型/几何',
  doctor: '医生',
  product_score: '产品评分',
  track_window: '短窗跟踪',
  template_reference: '模板参考',
  not_available: '暂无来源',
};

const STATUS_LABELS: Record<string, string> = {
  suggested: 'AI/规则建议',
  confirmed: '已确认',
  doctor_edited: '已人工修正',
  unevaluated: '未评估',
  conflict: '证据冲突',
  pending: '待补充',
  reference_only: '仅供参考',
};

type Props = {
  caseId?: string | null;
  frameId?: string | null;
  frameTime?: number | null;
  clinical?: Record<string, unknown>;
  lesionPolygon?: number[][];
  wallPolygon?: number[][];
  frameSize?: { width: number; height: number } | null;
  layerResult?: LayerAnalyzeResult | null;
  productStage?: string | null;
  initialState?: GcUsReportState | null;
  zh?: boolean;
  compact?: boolean;
  actorId?: string | null;
  modelVersion?: string | null;
  ruleVersion?: string;
  onStateChange?: (state: GcUsReportState) => void;
};

const EVIDENCE_SOFTWARE_VERSION = 'next-gc-us-evidence-panel-v1';

function makeAuditId(prefix: string, caseId?: string | null, fieldId?: string | null): string {
  const nonce = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${caseId || 'unknown'}:${fieldId || 'stage'}:${nonce}`;
}

function buildSourceRefs(
  caseId: string | null | undefined,
  frameId: string | null | undefined,
  frameTime: number | null | undefined,
  fieldId?: string | null,
): string[] {
  return [
    caseId ? `case:${caseId}` : 'case:unknown',
    fieldId ? `field:${fieldId}` : 'field:stage',
    frameId ? `frame:${frameId}` : 'frame:unknown',
    frameTime != null ? `time:${frameTime}` : 'time:unknown',
  ];
}

function fieldFor(signs: GcUsSigns, id: string): GcUsField<unknown> {
  if (id === 'length') return signs.size.length as GcUsField<unknown>;
  if (id === 'thickness') return signs.size.thickness as GcUsField<unknown>;
  return (signs as unknown as Record<string, GcUsField<unknown>>)[id] || {
    value: null,
    status: 'unevaluated',
    source: 'not_available',
    confidence: null,
    raw_value: null,
    doctor_override: null,
    evidence_ref: [],
  };
}

function setField(state: GcUsReportState, id: string, field: GcUsField<unknown>): GcUsReportState {
  if (id === 'length') {
    return { ...state, signs: { ...state.signs, size: { ...state.signs.size, length: field as GcUsField<number> } } };
  }
  if (id === 'thickness') {
    return { ...state, signs: { ...state.signs, size: { ...state.signs.size, thickness: field as GcUsField<number> } } };
  }
  return { ...state, signs: { ...state.signs, [id]: field } };
}

function mergeFreshEvidence(previous: GcUsReportState | null, fresh: GcUsReportState): GcUsReportState {
  if (!previous || previous.case_id !== fresh.case_id) return fresh;
  let signs = fresh.signs;
  for (const id of ['length', 'thickness', 'layer_structure', 'morphology', 'boundary', 'growth_pattern', 'serosa_change', 'perigastric_tissue']) {
    const old = fieldFor(previous.signs, id);
    if (old.status !== 'doctor_edited' && old.doctor_override == null) continue;
    if (id === 'length') signs = { ...signs, size: { ...signs.size, length: old as GcUsField<number> } };
    else if (id === 'thickness') signs = { ...signs, size: { ...signs.size, thickness: old as GcUsField<number> } };
    else signs = { ...signs, [id]: old } as GcUsSigns;
  }
  return {
    ...fresh,
    signs,
    report: previous.report,
    reference_stage: previous.reference_stage,
    doctor_actions: Array.from(
      new Map(
        [...(previous.doctor_actions || []), ...(fresh.doctor_actions || [])]
          .map((action) => [action.action_id, action] as const),
      ).values(),
    ),
  };
}

function polygonExtent(points: number[][]): { lengthPx: number | null; thicknessPx: number | null } {
  if (points.length < 3) return { lengthPx: null, thicknessPx: null };
  const xs = points.map((point) => Number(point[0])).filter(Number.isFinite);
  const ys = points.map((point) => Number(point[1])).filter(Number.isFinite);
  if (!xs.length || !ys.length) return { lengthPx: null, thicknessPx: null };
  const width = Math.max(...xs) - Math.min(...xs);
  const height = Math.max(...ys) - Math.min(...ys);
  if (width <= 1 || height <= 1) return { lengthPx: null, thicknessPx: null };
  return { lengthPx: Math.max(width, height), thicknessPx: Math.min(width, height) };
}

function polygonIrregularity(points: number[][]): number | null {
  if (points.length < 3) return null;
  let area = 0;
  let perimeter = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current[0] * next[1] - next[0] * current[1];
    perimeter += Math.hypot(next[0] - current[0], next[1] - current[1]);
  }
  const absoluteArea = Math.abs(area) / 2;
  return absoluteArea > 1e-3 && perimeter > 1e-3
    ? (perimeter * perimeter) / (4 * Math.PI * absoluteArea)
    : null;
}

export function GcUsEvidencePanel({
  caseId,
  frameId,
  frameTime,
  clinical = {},
  lesionPolygon = [],
  wallPolygon = [],
  frameSize,
  layerResult,
  productStage,
  initialState = null,
  zh = true,
  compact = false,
  actorId = null,
  modelVersion = null,
  ruleVersion = GC_US_REPORT_SCHEMA_VERSION,
  onStateChange,
}: Props) {
  const derived = useMemo(() => {
    const layer = layerResult?.layer;
    const penetration = layerResult?.pen;
    const extent = polygonExtent(lesionPolygon);
    const irregularity = polygonIrregularity(lesionPolygon);
    const label = layer?.label || null;
    const tHint = layer?.tHint || null;
    const clinicalSerosa = (clinical.serosa_status || clinical.serosa_change) as string | null | undefined;
    const serosaHint = clinicalSerosa || (/L5|浆膜|T4|T3[-–]T4/i.test(`${label || ''} ${tHint || ''}`) ? '浆膜面欠光整' : null);
    const sourceEcho = layerResult?.source?.badge || null;

    const derivedState = createGcUsReportState({
      case_id: caseId || null,
      frame_id: frameId || null,
      frame_time: frameTime ?? null,
      clinical,
      signs: deriveGcUsSigns({
        caseId,
        frameId,
        frameTime,
        clinical,
        lesion: {
          lengthMm: clinical.tumor_size_mm as number | undefined,
          thicknessMm: clinical.tumor_thickness_mm as number | undefined,
          lengthPx: extent.lengthPx,
          thicknessPx: penetration?.thick ?? extent.thicknessPx,
          echo: sourceEcho,
          morphology: clinical.morphology as string | undefined,
          boundary: clinical.boundary as string | undefined,
          growthPattern: (clinical.us_growth_pattern || clinical.growth_pattern_us) as string | undefined,
          serosaChange: serosaHint,
          perigastricTissue: (clinical.perigastric_tissue || clinical.fat_status) as string | undefined,
        },
        layer: {
          label: layerResult?.inContact === false ? null : label,
          tHint: layerResult?.inContact === false ? null : tHint,
          inContact: layerResult?.inContact,
          confidence: typeof layer?.confidence === 'number' ? layer.confidence : null,
        },
        pixel: {
          irregularity,
          echo: sourceEcho,
        },
        evidenceRef: [
          frameId || `frame:${frameTime ?? 'current'}`,
          frameSize ? `frame_size:${frameSize.width}x${frameSize.height}` : 'frame_size:unknown',
          wallPolygon.length >= 3 ? 'wall_polygon' : 'wall_unavailable',
        ],
      }),
      reference_stage: {
        ...normalizeGcUsStage(layerResult?.inContact === false ? null : (productStage || tHint)),
        source: productStage ? 'product_score' : 'model',
        conflicts: [],
      },
    });
    if (lesionPolygon.length >= 3) {
      const proxyField = (value: string, evidenceRef: string): GcUsField<string> => ({
        value,
        status: 'pending',
        source: 'live_contour',
        confidence: 0.25,
        raw_value: value,
        doctor_override: null,
        evidence_ref: [evidenceRef],
        note: '当前帧几何/界面代理，需医生结合多切面核对',
      });
      if (derivedState.signs.layer_structure.value == null) {
        derivedState.signs.layer_structure = proxyField('当前帧层次显示有限，需多切面复核', 'layer.multiplanar_review');
      }
      if (derivedState.signs.serosa_change.value == null) {
        derivedState.signs.serosa_change = proxyField('当前帧浆膜连续性需多切面核对', 'serosa.multiplanar_review');
      }
      if (derivedState.signs.perigastric_tissue.value == null) {
        derivedState.signs.perigastric_tissue = proxyField('当前帧胃周组织需多切面核对', 'perigastric.multiplanar_review');
      }
    }
    if (!initialState) return derivedState;
    const seeded = createGcUsReportState(initialState);
    const chooseField = <T,>(fresh: GcUsField<T>, seed: GcUsField<T>) => (
      seed.value != null || seed.status === 'doctor_edited' ? seed : fresh
    );
    return {
      ...derivedState,
      ...seeded,
      clinical: { ...derivedState.clinical, ...seeded.clinical },
      signs: {
        ...derivedState.signs,
        ...seeded.signs,
        size: {
          ...derivedState.signs.size,
          ...seeded.signs.size,
          length: chooseField(derivedState.signs.size.length, seeded.signs.size.length),
          thickness: chooseField(derivedState.signs.size.thickness, seeded.signs.size.thickness),
        },
      },
    };
  }, [caseId, clinical, frameId, frameSize, frameTime, initialState, layerResult, lesionPolygon, productStage, wallPolygon]);

  const [state, setState] = useState<GcUsReportState>(derived);
  const storageKey = caseId ? `next-gc-us-report:${caseId}` : null;

  useEffect(() => {
    let next = derived;
    if (storageKey && typeof window !== 'undefined') {
      try {
        const saved = window.localStorage.getItem(storageKey);
        if (saved) next = mergeFreshEvidence(next, createGcUsReportState(JSON.parse(saved)));
      } catch {
        // Ignore stale browser state.
      }
    }
    const timer = window.setTimeout(() => setState((previous) => mergeFreshEvidence(previous, next)), 0);
    return () => window.clearTimeout(timer);
  }, [derived, storageKey]);

  const report = useMemo(
    () => buildGcUsReport(state, state.reference_stage.requested_band || state.reference_stage.band),
    [state],
  );

  useEffect(() => {
    const next = report.structured;
    if (storageKey && typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // Browser storage is optional.
      }
    }
    onStateChange?.(next);
  }, [onStateChange, report.structured, storageKey]);

  const doctorEdit = (id: string, rawValue: string) => {
    const old = fieldFor(state.signs, id);
    const isMeasurement = id === 'length' || id === 'thickness';
    const value = isMeasurement
      ? (rawValue.trim() === '' ? null : Number(rawValue))
      : (rawValue || null);
    if (isMeasurement && value !== null && !Number.isFinite(value)) return;
    let nextField = applyGcUsDoctorOverride(old, value) as GcUsField<unknown>;
    if (isMeasurement && value !== null) nextField = { ...nextField, unit: 'mm' };
    const evidenceId = makeAuditId('evidence', caseId, id);
    const sourceRefs = buildSourceRefs(caseId, frameId, frameTime, id);
    const provenance: GcUsEvidenceProvenance = {
      evidence_id: evidenceId,
      source_type: 'doctor_input',
      source_refs: sourceRefs,
      frame_id_or_time: frameId || frameTime || null,
      model_version: modelVersion,
      rule_version: ruleVersion,
      actor_id: actorId,
      created_at: new Date().toISOString(),
    };
    nextField = {
      ...nextField,
      evidence_ref: Array.from(new Set([...(nextField.evidence_ref || []), evidenceId])),
      provenance: [...(old.provenance || []), provenance],
    };
    const action: GcUsDoctorAction = {
      action_id: makeAuditId('action', caseId, id),
      action_type: 'field_edit',
      field_id: id,
      suggestion_id: old.evidence_ref?.[0] || null,
      before_value: old.value,
      after_value: value,
      reason: 'Doctor override from the structured evidence panel.',
      evidence_ids: [evidenceId],
      source_refs: sourceRefs,
      frame_id_or_time: frameId || frameTime || null,
      actor_id: actorId,
      software_version: EVIDENCE_SOFTWARE_VERSION,
      model_version: modelVersion,
      rule_version: ruleVersion,
      created_at: new Date().toISOString(),
    };
    setState((previous) => ({
      ...setField(previous, id, nextField),
      doctor_actions: [...previous.doctor_actions, action],
      report: { ...previous.report, doctor_edited: true, source: 'doctor' },
    }));
  };

  const chooseStage = (stage: GcUsStageBand) => {
    const sourceRefs = buildSourceRefs(caseId, frameId, frameTime);
    const evidenceIds = Object.values(state.signs)
      .flatMap((field) => (
        field && typeof field === 'object' && 'provenance' in field
          ? ((field as GcUsField<unknown>).provenance || []).map((item) => item.evidence_id)
          : []
      ));
    const action: GcUsDoctorAction = {
      action_id: makeAuditId('action', caseId, 'stage'),
      action_type: 'stage_override',
      field_id: null,
      suggestion_id: state.reference_stage.raw,
      before_value: state.reference_stage.band,
      after_value: stage,
      reason: 'Doctor selected the provisional stage band.',
      evidence_ids: evidenceIds,
      source_refs: sourceRefs,
      frame_id_or_time: frameId || frameTime || null,
      actor_id: actorId,
      software_version: EVIDENCE_SOFTWARE_VERSION,
      model_version: modelVersion,
      rule_version: ruleVersion,
      created_at: new Date().toISOString(),
    };
    setState((previous) => ({
      ...previous,
      reference_stage: {
        ...previous.reference_stage,
        band: stage,
        requested_band: stage,
        raw: stage,
        source: 'doctor',
      },
      doctor_actions: [...previous.doctor_actions, action],
      report: { ...previous.report, doctor_edited: true, source: 'doctor' },
    }));
  };

  const resetDoctorEdits = () => {
    if (storageKey && typeof window !== 'undefined') window.localStorage.removeItem(storageKey);
    setState(derived);
  };

  const fields = ['length', 'thickness', 'layer_structure', 'morphology', 'boundary', 'growth_pattern', 'serosa_change', 'perigastric_tissue'];

  return (
    <section className={`rounded-xl border border-white/10 bg-black/30 text-[10px] text-gray-200 ${compact ? 'p-2' : 'p-3'}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold text-gray-100">
          <FileText size={13} />
          {zh ? '七项核心征象 / 胃周组织' : 'Seven core signs / perigastric tissue'}
        </div>
        <span className="font-mono text-[9px] text-gray-500">{GC_US_REPORT_SCHEMA_VERSION}</span>
      </div>
      <div className="mb-2 rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[9px] text-gray-400">
        模板：{GC_US_REPORT_TEMPLATE_ID}；来源：{state.source_doc}；当前阶段：
        <strong className={report.stage === 'uncertain' ? 'text-amber-300' : 'text-emerald-300'}>{report.stage}</strong>
      </div>
      <div className="mb-2 grid grid-cols-4 gap-1">
        {(['T1', 'T2', 'T3', 'T4'] as const).map((stage) => (
          <button
            key={stage}
            type="button"
            onClick={() => chooseStage(stage)}
            className={`rounded border px-2 py-1 font-mono text-[10px] ${
              state.reference_stage.requested_band === stage
                ? 'border-orange-400/60 bg-orange-500/15 text-orange-100'
                : 'border-white/10 text-gray-400 hover:bg-white/5'
            }`}
          >
            {stage}
          </button>
        ))}
      </div>
      <div className="space-y-1.5">
        {fields.map((id) => {
          const field = fieldFor(state.signs, id);
          const options = SIGN_OPTIONS[id] || [];
          const isMeasurement = id === 'length' || id === 'thickness';
          const display = field.value == null ? '' : String(field.value);
          return (
            <div key={id} className="grid grid-cols-[86px_minmax(0,1fr)] gap-2 rounded border border-white/10 bg-black/20 p-1.5">
              <div className="text-gray-400">
                {LABELS[id]}
                <span className="mt-0.5 block font-mono text-[8px] text-gray-600">{STATUS_LABELS[field.status] || field.status}</span>
              </div>
              <div className="min-w-0">
                {isMeasurement ? (
                  <div className="flex gap-1">
                    <input
                      value={display}
                      type="number"
                      step="any"
                      onChange={(event) => doctorEdit(id, event.target.value)}
                      className="min-w-0 flex-1 rounded border border-white/10 bg-black/40 px-1.5 py-1 text-gray-100 outline-none focus:border-orange-400/60"
                      placeholder="未评估"
                    />
                    <span className="rounded border border-white/10 px-1.5 py-1 font-mono text-gray-500">{field.unit || 'mm'}</span>
                  </div>
                ) : (
                  <select
                    value={display}
                    onChange={(event) => doctorEdit(id, event.target.value)}
                    className="w-full rounded border border-white/10 bg-black/40 px-1.5 py-1 text-gray-100 outline-none focus:border-orange-400/60"
                  >
                    <option value="">未评估</option>
                    {(options.includes(display) ? options : display ? [display, ...options] : options).map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                )}
                <div className="mt-0.5 flex flex-wrap gap-2 font-mono text-[8px] text-gray-600">
                  <span>{SOURCE_LABELS[field.source] || field.source}</span>
                  {field.doctor_override != null ? <span className="text-orange-300">原始建议；医生修正</span> : null}
                  {field.provenance?.length ? <span className="text-emerald-300/80">evidence:{field.provenance.length}</span> : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {report.conflicts.length ? (
        <div className="mt-2 rounded border border-rose-400/30 bg-rose-950/20 px-2 py-1.5 text-[9px] leading-relaxed text-rose-100">
          <div className="mb-0.5 flex items-center gap-1 font-semibold"><AlertTriangle size={11} />需要医生复核</div>
          {report.conflicts.map((item) => <div key={item.code}>- {item.message}</div>)}
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-1 text-[9px] text-emerald-300/80"><Check size={11} />当前无结构化征象冲突</div>
      )}
      <div className="mt-2 whitespace-pre-wrap rounded border border-white/10 bg-black/30 p-2 text-[9px] leading-relaxed text-gray-300">{report.prose}</div>
      <button
        type="button"
        onClick={resetDoctorEdits}
        className="mt-2 inline-flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[9px] text-gray-400 hover:bg-white/5"
      >
        <RotateCcw size={10} />恢复 AI/规则建议
      </button>
      <div className="mt-1 flex items-center gap-1 text-[8px] text-gray-600">
        <Pencil size={9} />医生修正后会按病例保存字段变更、证据来源和版本信息，并进入 Agent 报告请求。
      </div>
    </section>
  );
}
