'use client';

import React, { useMemo } from 'react';
import type { AgentToolResult } from '@/types';
import type { GcUsField, GcUsSigns } from '@/lib/gc-us-report-template';
import { GC_US_SIGN_MODEL_SPECS, type GcUsSignModelSpec } from '@/lib/gc-us-sign-models';

type UnknownRecord = Record<string, unknown>;

type Props = {
  signs?: GcUsSigns | null;
  signAnalysis?: AgentToolResult | null;
  zh?: boolean;
  compact?: boolean;
  showGeometry?: boolean;
};

type FieldSnapshot = {
  status?: string;
  source?: string;
  confidence?: number | null;
  value?: unknown;
  grade?: unknown;
  detail?: string;
};

function asRecord(value: unknown): UnknownRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as UnknownRecord
    : null;
}

function asFiniteNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getLocalField(signs: GcUsSigns | null | undefined, id: GcUsSignModelSpec['id']): GcUsField<unknown> | null {
  if (!signs) return null;
  if (id === 'length') return signs.size.length as GcUsField<unknown>;
  if (id === 'thickness') return signs.size.thickness as GcUsField<unknown>;
  return (signs as unknown as Record<string, GcUsField<unknown>>)[id] || null;
}

function getAgentField(signAnalysis: AgentToolResult | null | undefined, id: GcUsSignModelSpec['id']): FieldSnapshot | null {
  const explanation = asRecord(signAnalysis?.explanation);
  const explanationFields = asRecord(explanation?.fields);
  const featurePack = asRecord(signAnalysis?.feature_pack);
  const featurePackFields = asRecord(featurePack?.fields);
  const agentId = id === 'length' ? 'size_length' : id === 'thickness' ? 'size_thickness' : id;
  const raw = asRecord(explanationFields?.[agentId] ?? featurePackFields?.[agentId]);
  if (!raw) return null;
  return {
    status: typeof raw.status === 'string' ? raw.status : undefined,
    source: typeof raw.source === 'string' ? raw.source : undefined,
    confidence: asFiniteNumber(raw.confidence),
    value: raw.value,
    grade: raw.grade,
    detail: typeof raw.detail === 'string' ? raw.detail : undefined,
  };
}

function statusLabel(status: string | undefined, zh: boolean): string {
  const labels: Record<string, { zh: string; en: string }> = {
    available: { zh: '已接入', en: 'Connected' },
    completed: { zh: '已完成', en: 'Completed' },
    confirmed: { zh: '已确认', en: 'Confirmed' },
    explicit: { zh: '显式证据', en: 'Explicit evidence' },
    suggested: { zh: '系统建议', en: 'Suggested' },
    clinical: { zh: '临床输入', en: 'Clinical input' },
    proxy: { zh: '几何代理', en: 'Geometry proxy' },
    derived: { zh: '派生特征', en: 'Derived feature' },
    missing: { zh: '缺少证据', en: 'Missing evidence' },
    not_assessable: { zh: '不可评估', en: 'Not assessable' },
    unevaluated: { zh: '未评估', en: 'Not assessed' },
    pending: { zh: '待分析', en: 'Pending' },
  };
  const item = labels[status || ''] || { zh: status || '待分析', en: status || 'Pending' };
  return zh ? item.zh : item.en;
}

function statusClass(status: string | undefined): string {
  if (status === 'available' || status === 'completed' || status === 'confirmed') {
    return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200';
  }
  if (status === 'proxy' || status === 'derived' || status === 'suggested' || status === 'pending') {
    return 'border-amber-400/30 bg-amber-400/10 text-amber-200';
  }
  return 'border-slate-400/25 bg-slate-400/10 text-slate-300';
}

function kindLabel(kind: GcUsSignModelSpec['evidenceKind'], zh: boolean): string {
  if (kind === 'clinical') return zh ? '临床' : 'Clinical';
  if (kind === 'derived') return zh ? '派生' : 'Derived';
  return zh ? '代理' : 'Proxy';
}

function fieldValue(snapshot: FieldSnapshot | null, local: GcUsField<unknown> | null): string {
  if (snapshot?.grade !== undefined && snapshot.grade !== null) {
    const max = asFiniteNumber(asRecord(snapshot)?.grade_max);
    return max != null ? `${snapshot.grade}/${max}` : String(snapshot.grade);
  }
  if (snapshot?.value !== undefined && snapshot.value !== null && snapshot.value !== '') {
    return String(snapshot.value);
  }
  if (snapshot?.detail) return snapshot.detail;
  if (local?.value !== undefined && local.value !== null && local.value !== '') return String(local.value);
  return '—';
}

function confidenceValue(snapshot: FieldSnapshot | null, local: GcUsField<unknown> | null): number | null {
  const direct = snapshot?.confidence ?? local?.confidence;
  const value = asFiniteNumber(direct);
  return value == null ? null : Math.max(0, Math.min(1, value));
}

function geometryPayload(signAnalysis: AgentToolResult | null | undefined): {
  audit: UnknownRecord;
  viz: UnknownRecord;
} | null {
  const explanation = asRecord(signAnalysis?.explanation);
  const audit = asRecord(explanation?.geometry_audit);
  const viz = asRecord(audit?.viz);
  if (!audit || !viz) return null;
  return { audit, viz };
}

function pointsFrom(value: unknown): number[][] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => Array.isArray(item) && item.length >= 2)
    .map((item) => [Number(item[0]), Number(item[1])])
    .filter((item) => item.every((coordinate) => Number.isFinite(coordinate)));
}

function GeometryPreview({
  signAnalysis,
  zh,
  compact,
}: {
  signAnalysis?: AgentToolResult | null;
  zh: boolean;
  compact: boolean;
}) {
  const geometry = useMemo(() => geometryPayload(signAnalysis), [signAnalysis]);
  const contour = pointsFrom(geometry?.viz.contour_xy);
  if (!geometry || contour.length < 3) return null;

  const centers = [
    pointsFrom([geometry.viz.lesion_center])[0],
    pointsFrom([geometry.viz.lumen_center])[0],
  ].filter(Boolean) as number[][];
  const arrow = pointsFrom([geometry.viz.outward_arrow])[0];
  const allPoints = [...contour, ...centers, ...(arrow ? [arrow.slice(0, 2), arrow.slice(2, 4)] : [])];
  const xs = allPoints.map((item) => item[0]);
  const ys = allPoints.map((item) => item[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = Math.max(8, Math.max(maxX - minX, maxY - minY) * 0.12);
  const viewBox = `${minX - pad} ${minY - pad} ${Math.max(1, maxX - minX + pad * 2)} ${Math.max(1, maxY - minY + pad * 2)}`;
  const pointString = contour.map((item) => item.join(',')).join(' ');
  const lesionCenter = pointsFrom([geometry.viz.lesion_center])[0];
  const lumenCenter = pointsFrom([geometry.viz.lumen_center])[0];
  const direction = typeof geometry.audit.direction_source === 'string'
    ? geometry.audit.direction_source
    : 'unknown';
  const contact = asFiniteNumber(geometry.audit.contact_arc_ratio);
  const sectors = asRecord(geometry.audit.sector_frac);

  return (
    <div className={`mt-2 rounded border border-fuchsia-300/20 bg-fuchsia-400/[0.04] ${compact ? 'p-1.5' : 'p-2'}`}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className={`${compact ? 'text-[9px]' : 'text-[10px]'} font-semibold text-fuchsia-100`}>
          {zh ? '方向几何可视化' : 'Directional geometry preview'}
        </span>
        <span className="text-[9px] text-slate-500">{direction}</span>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_7rem] items-stretch gap-2">
        <svg
          viewBox={viewBox}
          className="h-24 w-full rounded border border-white/10 bg-black/35"
          role="img"
          aria-label={zh ? '病灶轮廓和胃腔方向代理' : 'Lesion contour and lumen direction proxy'}
        >
          <polyline points={pointString} fill="rgba(217,70,239,0.18)" stroke="#e879f9" strokeWidth="2" />
          {lesionCenter && (
            <circle cx={lesionCenter[0]} cy={lesionCenter[1]} r="3" fill="#fef08a" />
          )}
          {lumenCenter && (
            <circle cx={lumenCenter[0]} cy={lumenCenter[1]} r="3" fill="#67e8f9" />
          )}
          {arrow && (
            <line x1={arrow[0]} y1={arrow[1]} x2={arrow[2]} y2={arrow[3]} stroke="#bef264" strokeWidth="2.5" />
          )}
        </svg>
        <div className="space-y-1 text-[9px] text-slate-400">
          <div>
            {zh ? '接触弧' : 'Contact arc'}:{' '}
            <span className="font-mono text-fuchsia-100">{contact == null ? '—' : `${Math.round(contact * 100)}%`}</span>
          </div>
          <div>
            {zh ? '向外' : 'Outward'}:{' '}
            <span className="font-mono text-lime-100">{asFiniteNumber(sectors?.outward) == null ? '—' : `${Math.round(Number(sectors?.outward) * 100)}%`}</span>
          </div>
          <div>
            {zh ? '方向' : 'Direction'}:{' '}
            <span className="font-mono text-cyan-100">{direction}</span>
          </div>
        </div>
      </div>
      <div className="mt-1 text-[9px] leading-relaxed text-slate-500">
        {zh
          ? '轮廓、胃腔中心和向外方向用于解释几何代理，不代表真实病理浸润。'
          : 'Contour, lumen center, and outward direction explain the geometry proxy; they are not pathological invasion.'}
      </div>
    </div>
  );
}

export function GcUsSignModelMap({
  signs = null,
  signAnalysis = null,
  zh = true,
  compact = false,
  showGeometry = true,
}: Props) {
  const overallStatus = typeof signAnalysis?.status === 'string'
    ? signAnalysis.status
    : signAnalysis?.available
      ? 'available'
      : undefined;
  const normalized = asFiniteNumber(signAnalysis?.normalized_i);
  const backendId = typeof signAnalysis?.backend_id === 'string'
    ? signAnalysis.backend_id
    : 'gc_us_sign_scorer_v1';

  return (
    <section className={`rounded-xl border border-violet-300/20 bg-violet-400/[0.04] ${compact ? 'p-2' : 'p-3'}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className={`${compact ? 'text-[11px]' : 'text-xs'} font-semibold text-violet-100`}>
            {zh ? '核心征象算法链' : 'Core sign model chain'}
          </div>
          <div className="mt-0.5 text-[9px] leading-relaxed text-slate-500">
            {zh
              ? '逐项显示算法、上游网络和证据性质；代理项不会自动升级为确定 cT。'
              : 'Each row shows the algorithm, upstream network, and evidence type; proxies never auto-promote to definite cT.'}
          </div>
        </div>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] ${statusClass(overallStatus)}`}>
          {statusLabel(overallStatus, zh)}
        </span>
      </div>

      <div className="mt-2 space-y-1.5">
        {GC_US_SIGN_MODEL_SPECS.map((spec) => {
          const local = getLocalField(signs, spec.id);
          const agent = getAgentField(signAnalysis, spec.id);
          const status = agent?.status || local?.status || spec.evidenceKind;
          const confidence = confidenceValue(agent, local);
          const value = fieldValue(agent, local);
          return (
            <div key={spec.id} className="rounded border border-white/10 bg-black/25 px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className={`${compact ? 'text-[10px]' : 'text-[11px]'} font-medium text-slate-200`}>
                  {zh ? spec.labelZh : spec.labelEn}
                </span>
                <div className="flex shrink-0 items-center gap-1">
                  <span className="rounded border border-white/10 px-1 text-[8px] text-slate-400">
                    {kindLabel(spec.evidenceKind, zh)}
                  </span>
                  <span className={`rounded border px-1 text-[8px] ${statusClass(status)}`}>
                    {statusLabel(status, zh)}
                  </span>
                </div>
              </div>
              <div className="mt-1 grid grid-cols-1 gap-0.5 text-[9px] leading-relaxed text-slate-500 xl:grid-cols-2 xl:gap-x-2">
                <div>
                  <span className="text-slate-600">{zh ? '算法' : 'Algorithm'}: </span>
                  {zh ? spec.algorithmZh : spec.algorithmEn}
                </div>
                <div>
                  <span className="text-slate-600">{zh ? '网络/实现' : 'Network / implementation'}: </span>
                  {zh ? spec.networkZh : spec.networkEn}
                </div>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-900">
                  <div
                    className={`h-full rounded-full ${status === 'available' || status === 'confirmed' ? 'bg-emerald-300' : 'bg-amber-300'}`}
                    style={{ width: `${confidence == null ? 0 : Math.round(confidence * 100)}%` }}
                  />
                </div>
                <span className="max-w-[10rem] truncate font-mono text-[9px] text-violet-100" title={value}>
                  {value}
                </span>
                <span className="w-8 shrink-0 text-right font-mono text-[9px] text-slate-500">
                  {confidence == null ? '—' : `${Math.round(confidence * 100)}%`}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {signAnalysis ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-slate-500">
          <span>{zh ? '后端' : 'Backend'}: <span className="font-mono text-violet-200">{backendId}</span></span>
          {normalized != null ? <span>{zh ? '归一化软评分' : 'Normalized soft score'}: <span className="font-mono text-violet-200">{normalized.toFixed(3)}</span></span> : null}
          <span>{zh ? '信任' : 'Trust'}: <span className="font-mono text-amber-200">{String(signAnalysis.trust_label || 'caution')}</span></span>
        </div>
      ) : null}
      {showGeometry ? <GeometryPreview signAnalysis={signAnalysis} zh={zh} compact={compact} /> : null}
    </section>
  );
}
