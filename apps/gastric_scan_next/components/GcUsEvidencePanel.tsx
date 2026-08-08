'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, FileText, Pencil, RotateCcw } from 'lucide-react';
import {
  GC_US_REPORT_SCHEMA_VERSION,
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
import { computeLesionLumenGeometry } from '@/lib/lesion-lumen-geometry';
import type { AgentToolResult } from '@/types';
import { GcUsSignModelMap } from '@/components/GcUsSignModelMap';

const SIGN_OPTIONS: Record<string, Array<{ zh: string; en: string }>> = {
  layer_structure: [
    { zh: '层次结构清晰', en: 'Layer structure clear' },
    { zh: '黏膜/黏膜下层（T1）', en: 'Mucosa / submucosa (T1)' },
    { zh: '固有肌层（T2）', en: 'Muscularis propria (T2)' },
    { zh: '浆膜下层（T3）', en: 'Subserosa (T3)' },
    { zh: '浆膜连续性中断（T4a）', en: 'Serosal discontinuity (T4a)' },
    { zh: '邻近器官侵犯（T4b）', en: 'Adjacent organ invasion (T4b)' },
    { zh: '局部受累，结构尚可辨', en: 'Focal involvement, layers still readable' },
    { zh: '结构紊乱', en: 'Disorganized wall structure' },
    { zh: '连续性可疑破坏', en: 'Suspected continuity break' },
    { zh: '不可辨', en: 'Not assessable' },
  ],
  morphology: [
    { zh: '浅表隆起型', en: 'Superficial elevated' },
    { zh: '局限隆起型', en: 'Localized elevated' },
    { zh: '局部浸润型', en: 'Locally infiltrative' },
    { zh: '溃疡浸润型', en: 'Ulcerative infiltrative' },
    { zh: '巨大浸润型', en: 'Bulky infiltrative' },
    { zh: '未评估', en: 'Not assessed' },
  ],
  boundary: [
    { zh: '边界清晰、规则', en: 'Clear, regular margin' },
    { zh: '边界部分欠清', en: 'Partially ill-defined margin' },
    { zh: '边界不规则', en: 'Irregular margin' },
    { zh: '外侵样改变，边界消失倾向', en: 'Invasive appearance, margin fading' },
    { zh: '未评估', en: 'Not assessed' },
  ],
  growth_pattern: [
    { zh: '膨胀型', en: 'Expansile' },
    { zh: '局部浸润性', en: 'Locally infiltrative' },
    { zh: '明显浸润性', en: 'Frankly infiltrative' },
    { zh: '跨壁向外侵犯倾向', en: 'Transmural outward invasion tendency' },
    { zh: '未评估', en: 'Not assessed' },
  ],
  serosa_change: [
    { zh: '浆膜连续光滑', en: 'Serosa continuous and smooth' },
    { zh: '浆膜面欠光整', en: 'Serosal surface irregular' },
    { zh: '浆膜连续性可疑破坏', en: 'Suspected serosal discontinuity' },
    { zh: '浆膜连续性中断', en: 'Serosal discontinuity' },
    { zh: '未评估', en: 'Not assessed' },
  ],
  perigastric_tissue: [
    { zh: '胃周组织未见明显异常改变', en: 'No clear perigastric abnormality' },
    { zh: '胃周脂肪间隙清晰', en: 'Perigastric fat plane clear' },
    { zh: '胃周脂肪间隙欠清', en: 'Perigastric fat plane ill-defined' },
    { zh: '胃周脂肪间隙异常改变', en: 'Abnormal perigastric fat change' },
    { zh: '未评估', en: 'Not assessed' },
  ],
};

const LABELS: Record<string, { zh: string; en: string }> = {
  length: { zh: '肿瘤长径', en: 'Tumor length' },
  thickness: { zh: '肿瘤厚度', en: 'Tumor thickness' },
  layer_structure: { zh: '胃壁层次结构', en: 'Wall layer structure' },
  morphology: { zh: '肿瘤形态', en: 'Tumor morphology' },
  boundary: { zh: '肿瘤边界', en: 'Tumor margin' },
  growth_pattern: { zh: '生长方式', en: 'Growth pattern' },
  serosa_change: { zh: '浆膜改变', en: 'Serosal change' },
  perigastric_tissue: { zh: '胃周组织', en: 'Perigastric tissue' },
};

const SOURCE_LABELS: Record<string, { zh: string; en: string }> = {
  clinical: { zh: '病例表格', en: 'Case table' },
  live_contour: { zh: '本帧轮廓', en: 'Current-frame contour' },
  pixel: { zh: '像素辅助', en: 'Pixel assist' },
  model: { zh: '系统建议', en: 'System suggestion' },
  doctor: { zh: '医生', en: 'Physician' },
  product_score: { zh: '产品评分', en: 'Product score' },
  track_window: { zh: '短窗跟踪', en: 'Short-window track' },
  template_reference: { zh: '模板参考', en: 'Template reference' },
  not_available: { zh: '暂无来源', en: 'No source yet' },
};

function asClinicalRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null;
}

function clinicalPositiveNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function clinicalFlag(value: unknown): boolean {
  return value === true || value === 1 || value === '1' || value === 'true';
}

function clinicalLabDisplay(value: unknown, positive: unknown): string {
  const number = clinicalPositiveNumber(value);
  if (number != null) return String(number);
  if (clinicalFlag(positive)) return 'Positive';
  return 'Not provided';
}

const STATUS_LABELS: Record<string, { zh: string; en: string }> = {
  suggested: { zh: '系统建议', en: 'System suggestion' },
  confirmed: { zh: '已确认', en: 'Confirmed' },
  doctor_edited: { zh: '已人工修正', en: 'Physician edited' },
  unevaluated: { zh: '未评估', en: 'Not assessed' },
  conflict: { zh: '证据冲突', en: 'Evidence conflict' },
  pending: { zh: '待补充', en: 'Pending' },
  reference_only: { zh: '仅供参考', en: 'Reference only' },
};

function pickLabel(entry: { zh: string; en: string } | undefined, zh: boolean, fallback = ''): string {
  if (!entry) return fallback;
  return zh ? entry.zh : entry.en;
}

type Props = {
  caseId?: string | null;
  frameId?: string | null;
  frameTime?: number | null;
  clinical?: Record<string, unknown>;
  lesionPolygon?: number[][];
  wallPolygon?: number[][];
  lumenPolygon?: number[][];
  lumenBBox?: { x1: number; y1: number; x2: number; y2: number } | null;
  frameSize?: { width: number; height: number } | null;
  layerResult?: LayerAnalyzeResult | null;
  productStage?: string | null;
  assistantStage?: string | null;
  assistantConfidence?: number | null;
  signAnalysis?: AgentToolResult | null;
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

function latestDoctorFieldAction(
  state: GcUsReportState,
  fieldId: string,
): GcUsDoctorAction | null {
  return (state.doctor_actions || [])
    .filter((action) => action.field_id === fieldId)
    .reduce<GcUsDoctorAction | null>((latest, action) => {
      if (!latest || action.created_at >= latest.created_at) return action;
      return latest;
    }, null);
}

export function mergeFreshEvidence(previous: GcUsReportState | null, fresh: GcUsReportState): GcUsReportState {
  if (!previous || previous.case_id !== fresh.case_id) return fresh;
  let signs = fresh.signs;
  const template_fields = { ...fresh.template_fields };
  let changed = false;
  for (const id of ['length', 'thickness', 'layer_structure', 'morphology', 'boundary', 'growth_pattern', 'serosa_change', 'perigastric_tissue']) {
    const old = fieldFor(previous.signs, id);
    if (old.status !== 'doctor_edited' && old.doctor_override == null) continue;
    changed = true;
    if (id === 'length') signs = { ...signs, size: { ...signs.size, length: old as GcUsField<number> } };
    else if (id === 'thickness') signs = { ...signs, size: { ...signs.size, thickness: old as GcUsField<number> } };
    else signs = { ...signs, [id]: old } as GcUsSigns;
  }
  for (const id of Object.keys(fresh.template_fields) as Array<keyof GcUsReportState['template_fields']>) {
    const old = previous.template_fields[id];
    const next = fresh.template_fields[id];
    if (!old) continue;
    if (next.status === 'doctor_edited' || next.doctor_override != null) {
      (template_fields as unknown as Record<string, GcUsField<unknown>>)[id] = next;
    } else if (old.status === 'doctor_edited' || old.doctor_override != null || next.value == null) {
      (template_fields as unknown as Record<string, GcUsField<unknown>>)[id] = old;
      changed = true;
    }
  }
  if (!changed
    && previous.reference_stage.source !== 'doctor'
    && previous.report.status !== 'finalized'
    && !(previous.report.doctor_edited || previous.report.source === 'doctor')
    && !(previous.doctor_actions || []).length) {
    return fresh;
  }
  const freshOwnsReport = fresh.report.status !== 'draft'
    || fresh.report.doctor_edited
    || fresh.report.source === 'doctor';
  const previousOwnsReport = previous.report.status === 'finalized'
    || previous.report.doctor_edited
    || previous.report.source === 'doctor';
  const previousSignedByAction = latestDoctorFieldAction(previous, 'signed_by');
  const freshSignedByAction = latestDoctorFieldAction(fresh, 'signed_by');
  const isSameSignedByAction = Boolean(
    previousSignedByAction
      && freshSignedByAction
      && previousSignedByAction.action_id === freshSignedByAction.action_id,
  );
  const freshSignedByIsNewer = Boolean(
    freshSignedByAction
      && !isSameSignedByAction
      && (!previousSignedByAction || freshSignedByAction.created_at >= previousSignedByAction.created_at),
  );
  const mergedReport = freshOwnsReport || !previousOwnsReport
    ? fresh.report
    : previous.report;
  const report = {
    ...mergedReport,
    // Evidence panels can echo an older report while a doctor is typing. Do not
    // let that echo erase a newer signing physician unless it explicitly
    // records a signed_by edit.
    signed_by: freshSignedByIsNewer || (
      fresh.report.signed_by != null
      && !previousSignedByAction
      && !freshSignedByAction
    )
      ? fresh.report.signed_by
      : previous.report.signed_by,
    signed_at: freshSignedByIsNewer || (
      fresh.report.signed_at != null
      && !previousSignedByAction
      && !freshSignedByAction
    )
      ? fresh.report.signed_at
      : previous.report.signed_at,
  };
  return {
    ...fresh,
    signs,
    template_fields,
    report_images: previous.report_images.length ? previous.report_images : fresh.report_images,
    report,
    reference_stage: previous.reference_stage.source === 'doctor'
      ? previous.reference_stage
      : fresh.reference_stage,
    doctor_actions: Array.from(
      new Map(
        [...(previous.doctor_actions || []), ...(fresh.doctor_actions || [])]
          .map((action) => [action.action_id, action] as const),
      ).values(),
    ),
  };
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

function displayStageLabel(value: unknown): string | null {
  const raw = String(value || '').trim();
  const match = raw.toUpperCase().match(/\bT([1-4])(\+)?\b/);
  if (match) return `T${match[1]}${match[2] || ''}`;
  if (/^(benign|良性)$/i.test(raw)) return 'benign';
  if (/^(malignant|恶性)$/i.test(raw)) return 'malignant';
  return null;
}

function displayStageText(value: string | null, zh: boolean): string {
  if (value === 'benign') return zh ? '良性' : 'Benign';
  if (value === 'malignant') return zh ? '恶性' : 'Malignant';
  return value || (zh ? '待生成' : 'Pending');
}

export function GcUsEvidencePanel({
  caseId,
  frameId,
  frameTime,
  clinical = {},
  lesionPolygon = [],
  wallPolygon = [],
  lumenPolygon = [],
  lumenBBox = null,
  frameSize,
  layerResult,
  productStage,
  assistantStage = null,
  assistantConfidence = null,
  signAnalysis = null,
  initialState = null,
  zh = true,
  compact = false,
  actorId = null,
  modelVersion = null,
  ruleVersion = GC_US_REPORT_SCHEMA_VERSION,
  onStateChange,
}: Props) {
  const contourGeometry = useMemo(
    () => computeLesionLumenGeometry(lesionPolygon, lumenPolygon, lumenBBox),
    [lesionPolygon, lumenBBox, lumenPolygon],
  );
  const derivedBase = useMemo(() => {
    const layer = layerResult?.layer;
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
          // Length / thickness come from the case clinical table only (fixed mm).
          // Do not seed from live contour pixels — those are not calibrated.
          lengthMm: clinical.tumor_size_mm as number | undefined,
          thicknessMm: clinical.tumor_thickness_mm as number | undefined,
          lengthPx: undefined,
          thicknessPx: undefined,
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
        // A ContactGeom tHint is proxy geometry, not an independent stage.
        // Only an explicitly supplied product/doctor stage may populate this
        // reference slot.
        ...normalizeGcUsStage(productStage),
        source: productStage ? 'product_score' : 'not_available',
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
    return derivedState;
    // Do NOT depend on initialState/gcUsReport here — parent echoes onStateChange and
    // would create a Maximum update depth loop.
  }, [caseId, clinical, frameId, frameSize, frameTime, layerResult, lesionPolygon, productStage, wallPolygon]);

  const [state, setState] = useState<GcUsReportState>(derivedBase);
  const storageKey = caseId ? `next-gc-us-report:${caseId}` : null;
  const lastEmittedRef = useRef<string>('');
  const seededCaseRef = useRef<string | null>(null);

  const initialStateRef = useRef(initialState);
  useEffect(() => {
    initialStateRef.current = initialState;
  }, [initialState]);

  useEffect(() => {
    const handleExternalReportUpdate = (event: Event) => {
      const detail = (event as CustomEvent<GcUsReportState>).detail;
      if (!detail || detail.case_id !== caseId) return;
      const incoming = createGcUsReportState(detail);
      setState((previous) => mergeFreshEvidence(previous, incoming));
    };
    window.addEventListener('gastric:template-report-updated', handleExternalReportUpdate);
    return () => window.removeEventListener('gastric:template-report-updated', handleExternalReportUpdate);
  }, [caseId]);

  useEffect(() => {
    let next = derivedBase;
    const caseChanged = caseId !== seededCaseRef.current;
    if (caseChanged) {
      seededCaseRef.current = caseId || null;
      lastEmittedRef.current = '';
      const seed = initialStateRef.current;
      if (seed && seed.case_id === caseId) {
        const seeded = createGcUsReportState(seed);
        const chooseField = <T,>(fresh: GcUsField<T>, seedField: GcUsField<T>) => (
          seedField.value != null || seedField.status === 'doctor_edited' ? seedField : fresh
        );
        const chooseSizeField = <T,>(fresh: GcUsField<T>, seedField: GcUsField<T>) => (
          seedField.status === 'doctor_edited' || seedField.doctor_override != null
            ? seedField
            : (fresh.value != null ? fresh : seedField)
        );
        next = {
          ...derivedBase,
          ...seeded,
          clinical: { ...derivedBase.clinical, ...seeded.clinical },
          signs: {
            ...derivedBase.signs,
            ...seeded.signs,
            size: {
              ...derivedBase.signs.size,
              ...seeded.signs.size,
              length: chooseSizeField(derivedBase.signs.size.length, seeded.signs.size.length),
              thickness: chooseSizeField(derivedBase.signs.size.thickness, seeded.signs.size.thickness),
            },
            layer_structure: chooseField(derivedBase.signs.layer_structure, seeded.signs.layer_structure),
            morphology: chooseField(derivedBase.signs.morphology, seeded.signs.morphology),
            boundary: chooseField(derivedBase.signs.boundary, seeded.signs.boundary),
            growth_pattern: chooseField(derivedBase.signs.growth_pattern, seeded.signs.growth_pattern),
            serosa_change: chooseField(derivedBase.signs.serosa_change, seeded.signs.serosa_change),
            perigastric_tissue: chooseField(derivedBase.signs.perigastric_tissue, seeded.signs.perigastric_tissue),
            lesion_echo: chooseField(derivedBase.signs.lesion_echo, seeded.signs.lesion_echo),
          },
          reference_stage: seeded.reference_stage.source === 'doctor'
            ? seeded.reference_stage
            : derivedBase.reference_stage,
          report: seeded.report.status === 'finalized'
            || seeded.report.doctor_edited
            || seeded.report.source === 'doctor'
            ? seeded.report
            : derivedBase.report,
          conflicts: seeded.reference_stage.source === 'doctor'
            ? seeded.conflicts
            : derivedBase.conflicts,
          doctor_actions: seeded.doctor_actions || [],
        };
      }
      if (storageKey && typeof window !== 'undefined') {
        try {
          const saved = window.localStorage.getItem(storageKey);
          if (saved) next = mergeFreshEvidence(createGcUsReportState(JSON.parse(saved)), next);
        } catch {
          // Ignore stale browser state.
        }
      }
      const timer = window.setTimeout(() => setState(next), 0);
      return () => window.clearTimeout(timer);
    }
    // Same case: merge live contour/clinical suggestions but keep doctor edits.
    const timer = window.setTimeout(() => {
      setState((previous) => {
        const merged = mergeFreshEvidence(previous, derivedBase);
        return merged === previous ? previous : merged;
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [caseId, derivedBase, storageKey]);

  const report = useMemo(
    () => buildGcUsReport(state, state.reference_stage.requested_band || state.reference_stage.band),
    [state],
  );
  const doctorStage = state.reference_stage.source === 'doctor'
    ? displayStageLabel(state.reference_stage.requested_band || state.reference_stage.band)
    : null;
  const referenceStageLabel = doctorStage
    || displayStageLabel(assistantStage)
    || displayStageLabel(report.stage)
    || displayStageLabel(state.reference_stage.requested_band);
  const confidenceScore = typeof assistantConfidence === 'number' && Number.isFinite(assistantConfidence)
    ? Math.max(0, Math.min(1, assistantConfidence))
    : null;
  const stageProse = referenceStageLabel && report.stage === 'uncertain'
    ? referenceStageLabel === 'benign' || referenceStageLabel === 'malignant'
      ? (zh
        ? `当前二分类辅助判断倾向${displayStageText(referenceStageLabel, true)}，置信度${confidenceScore != null ? `${Math.round(confidenceScore * 100)}%` : '待生成'}；T分期不适用，仍需医生复核。`
        : `The malignancy gate favors ${displayStageText(referenceStageLabel, false).toLowerCase()}, with ${confidenceScore != null ? `${Math.round(confidenceScore * 100)}%` : 'pending'} confidence; T staging is not applicable and physician review remains required.`)
      : report.prose.replace(
        '胃癌可能，超声评估cTx期，浸润深度倾向尚不确定。',
        `胃癌可能，超声评估c${referenceStageLabel}期，当前置信度${
          confidenceScore != null ? `${Math.round(confidenceScore * 100)}%` : '待生成'
        }，存在征象冲突，需医生复核。`,
      )
    : report.prose;
  const geometryProse = contourGeometry.available
    ? (zh
      ? `当前帧胃腔关系代理：两者${contourGeometry.relation === 'overlap' ? '存在重叠' : contourGeometry.relation === 'near_lumen' ? '邻近' : '分离'}，间隙${contourGeometry.distancePx != null ? `${Math.round(contourGeometry.distancePx)}像素` : '待测'}。该信息仅用于定位与复核，不能独立决定 cT。`
      : `Current-frame lumen relation proxy: the lesion is ${contourGeometry.relation === 'overlap' ? 'overlapping' : contourGeometry.relation === 'near_lumen' ? 'near the lumen' : 'separate from the lumen'}, with a ${contourGeometry.distancePx != null ? `${Math.round(contourGeometry.distancePx)} px` : 'pending'} gap. Use only for localization/review; it cannot decide cT alone.`)
    : '';
  const visibleProse = [stageProse, geometryProse].filter(Boolean).join('\n');

  useEffect(() => {
    let next = report.structured;
    if (storageKey && typeof window !== 'undefined') {
      try {
        const saved = window.localStorage.getItem(storageKey);
        if (saved) {
          next = mergeFreshEvidence(createGcUsReportState(JSON.parse(saved)), next);
        }
      } catch {
        // Ignore malformed browser state and keep the live evidence state.
      }
    }
    if (initialStateRef.current?.case_id === caseId) {
      next = mergeFreshEvidence(initialStateRef.current, next);
    }
    let serialized = '';
    try {
      serialized = JSON.stringify(next);
    } catch {
      serialized = '';
    }
    if (serialized && serialized === lastEmittedRef.current) return;
    lastEmittedRef.current = serialized;
    if (storageKey && typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(next));
        window.localStorage.setItem(`${storageKey}:updated_at`, String(Date.now()));
      } catch {
        // Browser storage is optional.
      }
    }
    onStateChange?.(next);
  }, [caseId, onStateChange, report.structured, storageKey]);

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
    lastEmittedRef.current = '';
    setState(derivedBase);
  };

  const fields = ['length', 'thickness', 'layer_structure', 'morphology', 'boundary', 'growth_pattern', 'serosa_change', 'perigastric_tissue'];
  const tumorSize = asClinicalRecord(clinical.tumorSize);
  const biomarkers = asClinicalRecord(clinical.biomarkers);
  const tumorLengthMm = clinicalPositiveNumber(clinical.tumor_size_mm)
    ?? ((clinicalPositiveNumber(tumorSize?.length) ?? 0) * 10 || null);
  const tumorThicknessMm = clinicalPositiveNumber(clinical.tumor_thickness_mm)
    ?? ((clinicalPositiveNumber(tumorSize?.thickness) ?? 0) * 10 || null);
  const clinicalLocation = typeof clinical.location === 'string' && clinical.location.trim()
    ? clinical.location.trim()
    : 'No source yet';

  return (
    <section className={`rounded-xl border border-white/10 bg-black/30 text-[11px] text-gray-200 ${compact ? 'p-2.5' : 'p-3.5'}`}>
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-gray-100">
          <FileText size={14} />
          {zh ? '核心影像征象（可快速编辑）' : 'Core imaging signs (quick edit)'}
        </div>
      </div>
      <div className="mb-2.5 rounded border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-gray-400">
        <div className="flex items-center justify-between gap-2">
          <span>{zh ? '当前参考分期' : 'Current reference stage'}</span>
          <strong className={report.conflicts.length ? 'text-amber-300' : 'text-emerald-300'}>
            {displayStageText(referenceStageLabel, zh)}
          </strong>
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[10px] text-gray-500">
          <span>
            {confidenceScore != null
              ? `${zh ? '置信度' : 'Confidence'} ${Math.round(confidenceScore * 100)}%`
              : (zh ? '置信度待生成' : 'Confidence pending')}
          </span>
          {report.conflicts.length ? (
            <span className="text-amber-300">{zh ? '存在冲突，需复核' : 'Conflicts require review'}</span>
          ) : null}
        </div>
      </div>
      <section className="mb-2.5 rounded border border-cyan-400/20 bg-cyan-400/[0.04] px-2.5 py-2 text-[10px]">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-cyan-100">{zh ? '临床辅助资料' : 'Clinical auxiliary data'}</span>
          <span className="text-[9px] text-cyan-200/70">
            {zh ? '仅供医生参考，不参与自动分期' : 'Reference only; not used for automatic staging'}
          </span>
        </div>
        <div className="mt-1.5 grid grid-cols-2 gap-1.5">
          <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
            <div className="text-[8px] text-slate-500">{zh ? '病灶部位' : 'Location'}</div>
            <div className="mt-0.5 truncate text-gray-200">{clinicalLocation}</div>
          </div>
          <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
            <div className="text-[8px] text-slate-500">{zh ? '肿瘤长径' : 'Tumor length'}</div>
            <div className="mt-0.5 font-mono text-gray-200">
              {tumorLengthMm != null ? `${tumorLengthMm} mm` : (zh ? '未评估' : 'Not assessed')}
            </div>
          </div>
          <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
            <div className="text-[8px] text-slate-500">{zh ? '肿瘤厚度' : 'Tumor thickness'}</div>
            <div className="mt-0.5 font-mono text-gray-200">
              {tumorThicknessMm != null ? `${tumorThicknessMm} mm` : (zh ? '未评估' : 'Not assessed')}
            </div>
          </div>
          <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
            <div className="text-[8px] text-slate-500">CEA</div>
            <div className="mt-0.5 font-mono text-gray-200">
              {clinicalLabDisplay(clinical.cea, biomarkers?.cea_positive)}
            </div>
          </div>
          <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
            <div className="text-[8px] text-slate-500">CA19-9</div>
            <div className="mt-0.5 font-mono text-gray-200">
              {clinicalLabDisplay(clinical.ca199, biomarkers?.ca199_positive)}
            </div>
          </div>
        </div>
      </section>
      {contourGeometry.available ? (
        <div className="mb-2.5 rounded border border-fuchsia-300/20 bg-fuchsia-400/[0.04] px-2.5 py-2 text-[10px]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-fuchsia-100">
              {zh ? '胃腔关系（定位/复核代理）' : 'Lumen relation (localization/review proxy)'}
            </span>
            <span className="text-[9px] uppercase text-slate-500">{contourGeometry.quality}</span>
          </div>
          <div className="mt-1 grid grid-cols-3 gap-1.5">
            <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
              <div className="text-[8px] text-slate-500">{zh ? '间距' : 'Gap'}</div>
              <div className="font-mono text-fuchsia-100">
                {contourGeometry.distancePx != null ? `${Math.round(contourGeometry.distancePx)} px` : '—'}
              </div>
            </div>
            <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
              <div className="text-[8px] text-slate-500">{zh ? '状态' : 'Status'}</div>
              <div className="font-mono text-lime-100">
                {contourGeometry.relation === 'overlap'
                  ? (zh ? '重叠' : 'overlap')
                  : contourGeometry.relation === 'near_lumen'
                    ? (zh ? '邻近' : 'near')
                    : contourGeometry.relation === 'separated'
                      ? (zh ? '分离' : 'separated')
                      : (zh ? '未评估' : 'unknown')}
              </div>
            </div>
            <div className="rounded border border-white/10 bg-black/20 px-1.5 py-1">
              <div className="text-[8px] text-slate-500">{zh ? '向外扩张' : 'Outward'}</div>
              <div className="font-mono text-lime-100">
                {contourGeometry.outwardExpansionRatio != null
                  ? `${contourGeometry.outwardExpansionRatio >= 0 ? '+' : ''}${Math.round(contourGeometry.outwardExpansionRatio * 100)}%`
                  : '—'}
              </div>
            </div>
          </div>
          <div className="mt-1 text-[9px] leading-relaxed text-amber-100/80">
            {zh
              ? '当前帧定位与复核代理，不能独立决定 cT；矩形胃腔框更只是框代理，不等于真实胃壁或胃腔边界。'
              : 'Current-frame localization/review proxy only; it cannot decide cT alone. A rectangular lumen box is a box proxy, not true wall or lumen boundary.'}
          </div>
        </div>
      ) : null}
      <GcUsSignModelMap
        signs={state.signs}
        signAnalysis={signAnalysis}
        zh={zh}
        compact={compact}
      />
      <div className="mb-1.5 rounded border border-cyan-300/15 bg-cyan-400/[0.04] px-2 py-1.5 text-[9px] leading-relaxed text-slate-300">
        {zh
          ? 'cT 阶梯：T1 黏膜/黏膜下层；T2 固有肌层；T3 浆膜下组织；T4a 浆膜；T4b 邻近器官。本工作台评估 cT，不等于完整 TNM（N=淋巴结，M=远处转移）。无经确认壁层/浆膜/邻近器官证据时保持 cTx。T4+ 仅为模型聚合标签，亚型未定时勿当作确定分期。'
          : 'cT ladder: T1 mucosa/submucosa; T2 muscularis propria; T3 subserosa; T4a serosa; T4b adjacent organs. This workbench estimates cT, not full TNM (N=nodes, M=metastasis). Keep cTx without confirmed wall/serosa/adjacent-organ evidence. T4+ is only a model aggregate label when subtype is unresolved.'}
      </div>
      <div className="mb-2.5 grid grid-cols-5 gap-1.5">
        {(['T1', 'T2', 'T3', 'T4', 'uncertain'] as const).map((stage) => (
          <button
            key={stage}
            type="button"
            onClick={() => chooseStage(stage)}
            className={`rounded border px-2 py-1.5 font-mono text-[11px] ${
              state.reference_stage.requested_band === stage
                ? 'border-orange-400/60 bg-orange-500/15 text-orange-100'
                : 'border-white/10 text-gray-400 hover:bg-white/5'
            }`}
          >
            {stage === 'uncertain' ? 'cTx' : stage === 'T4' ? 'T4+' : stage}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {fields.map((id) => {
          const field = fieldFor(state.signs, id);
          const options = SIGN_OPTIONS[id] || [];
          const isMeasurement = id === 'length' || id === 'thickness';
          const display = field.value == null ? '' : String(field.value);
          return (
            <div key={id} className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-2 rounded border border-white/10 bg-black/20 p-2">
              <div className="text-[11px] text-gray-300">
                {pickLabel(LABELS[id], Boolean(zh), id)}
                <span className="mt-0.5 block text-[10px] text-gray-500">
                  {pickLabel(STATUS_LABELS[field.status], Boolean(zh), field.status)}
                </span>
              </div>
              <div className="min-w-0">
                {isMeasurement ? (
                  <div className="flex gap-1">
                    <input
                      value={display}
                      type="number"
                      step="any"
                      onChange={(event) => doctorEdit(id, event.target.value)}
                      className="min-w-0 flex-1 rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[11px] text-gray-100 outline-none focus:border-orange-400/60"
                      placeholder={zh ? '未评估' : 'Not assessed'}
                    />
                    <span className="rounded border border-white/10 px-2 py-1.5 font-mono text-[11px] text-gray-500">{field.unit || 'mm'}</span>
                  </div>
                ) : (
                  <select
                    value={display}
                    onChange={(event) => doctorEdit(id, event.target.value)}
                    className="w-full rounded border border-white/10 bg-black/40 px-2 py-1.5 text-[11px] text-gray-100 outline-none focus:border-orange-400/60"
                  >
                    <option value="">{zh ? '未评估' : 'Not assessed'}</option>
                    {(
                      options.some((item) => item.zh === display)
                        ? options
                        : display
                          ? [{ zh: display, en: display }, ...options]
                          : options
                    ).map((option) => (
                      <option key={option.zh} value={option.zh}>
                        {zh ? option.zh : option.en}
                      </option>
                    ))}
                  </select>
                )}
                <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-gray-500">
                  <span>{pickLabel(SOURCE_LABELS[field.source], Boolean(zh), field.source)}</span>
                  {field.doctor_override != null ? (
                    <span className="text-orange-300">{zh ? '原始建议已修正' : 'Suggestion overridden'}</span>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {report.conflicts.length ? (
        <div className="mt-2.5 rounded border border-rose-400/30 bg-rose-950/20 px-2.5 py-2 text-[11px] leading-relaxed text-rose-100">
          <div className="mb-1 flex items-center gap-1 font-semibold"><AlertTriangle size={12} />{zh ? '需要医生复核' : 'Physician review needed'}</div>
          {report.conflicts.map((item) => <div key={item.code}>- {item.message}</div>)}
        </div>
      ) : (
        <div className="mt-2.5 flex items-center gap-1 text-[11px] text-emerald-300/80"><Check size={12} />{zh ? '当前无结构化征象冲突' : 'No structured sign conflicts'}</div>
      )}
      <div className="mt-2.5 whitespace-pre-wrap rounded border border-white/10 bg-black/30 p-2.5 text-[11px] leading-relaxed text-gray-300">{visibleProse}</div>
      <button
        type="button"
        onClick={resetDoctorEdits}
        className="mt-2.5 inline-flex items-center gap-1 rounded border border-white/10 px-2.5 py-1.5 text-[11px] text-gray-400 hover:bg-white/5"
      >
        <RotateCcw size={11} />{zh ? '恢复系统建议' : 'Restore system suggestions'}
      </button>
      <div className="mt-1.5 flex items-center gap-1 text-[10px] text-gray-500">
        <Pencil size={10} />
        {zh
          ? '医生可直接修改征象；修改会按病例保存，并进入辅助诊断意见。'
          : 'Edit signs directly; changes are saved per case and feed assisted diagnosis.'}
      </div>
    </section>
  );
}
