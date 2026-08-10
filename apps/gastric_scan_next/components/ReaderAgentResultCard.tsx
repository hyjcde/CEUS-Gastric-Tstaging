'use client';

import React, { useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { Patient } from '@/types';
import { buildReaderAppUrl } from '@/lib/reading-agent-url';
import { navigateTo } from '@/lib/navigation';
import { useSettings } from '@/contexts/SettingsContext';

type ReaderAgentResult = {
  key?: string;
  updated_at?: string;
  case_id?: string;
  layer_label?: string | null;
  t_hint?: string | null;
  in_contact?: boolean;
  ok?: boolean;
  message?: string;
  mask_polygon?: unknown;
  wall_polygon?: unknown;
  source?: string;
  layer?: { label?: string; tHint?: string } | null;
};

interface ReaderAgentResultCardProps {
  patient: Patient | null;
  onApplyStage?: (stage: string, meta?: { t_hint?: string; layer_label?: string | null }) => void;
  onImportMaskPolygon?: (polygon: number[][]) => void;
  onImportWallPolygon?: (polygon: number[][]) => void;
}

function normalizeTHint(raw?: string | null): string | null {
  if (!raw) return null;
  const m = String(raw).toUpperCase().match(/T\s*([1-4])/);
  if (!m) return null;
  return m[1] === '4' ? 'T4' : `T${m[1]}`;
}

function asPolygon(raw: unknown): number[][] | null {
  if (!Array.isArray(raw) || raw.length < 3) return null;
  return raw as number[][];
}

export function ReaderAgentResultCard({
  patient,
  onApplyStage,
  onImportMaskPolygon,
  onImportWallPolygon,
}: ReaderAgentResultCardProps) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const [result, setResult] = useState<ReaderAgentResult | null>(null);

  useEffect(() => {
    if (!patient?.id && !patient?.patient_id) {
      return;
    }
    let cancelled = false;
    const keys = [patient.id, patient.patient_id].filter(Boolean) as string[];
    const load = async () => {
      try {
        for (const key of keys) {
          const res = await fetch(`/api/reader-agent/result?frame_id=${encodeURIComponent(key)}`);
          if (!res.ok) continue;
          const data = await res.json();
          if (data?.result && !cancelled) {
            setResult(data.result as ReaderAgentResult);
            return;
          }
        }
        if (!cancelled) setResult(null);
      } catch {
        if (!cancelled) setResult(null);
      }
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [patient?.id, patient?.patient_id]);

  if (!patient) return null;

  const openAgent = () => {
    navigateTo(buildReaderAppUrl(patient));
  };

  if (!result) {
    return (
      <div
        className="absolute right-3 z-30 max-w-xs rounded-lg border border-white/10 bg-black/70 px-3 py-2 text-[11px] text-gray-300 shadow-lg backdrop-blur"
        style={{ top: '7rem' }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-gray-400">{zh ? '阅片 / 分层回写' : 'Reader / layer write-back'}</span>
          <button
            type="button"
            onClick={openAgent}
            className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300"
            title={zh ? '打开 /reader：SAM + 胃壁分层' : 'Open /reader: SAM + wall layers'}
          >
            {zh ? '打开' : 'Open'} <ExternalLink size={11} />
          </button>
        </div>
        <div className="mt-1 text-[10px] text-gray-500">
          {zh
            ? '尚无回写。可从当前 Next 阅片工作台完成分割、分层与报告，结果会回到此处。'
            : 'No write-back yet. Finish segmentation, layers, and report in the Next reader workbench; results return here.'}
        </div>
      </div>
    );
  }

  const label = result.layer_label || result.layer?.label || '—';
  const hint = result.t_hint || result.layer?.tHint || '';
  const stage = normalizeTHint(hint);
  const when = result.updated_at ? new Date(result.updated_at).toLocaleString() : '';
  const maskPoly = asPolygon(result.mask_polygon);
  const wallPoly = asPolygon(result.wall_polygon);
  const pts = maskPoly?.length || 0;
  const wallPts = wallPoly?.length || 0;
  const sourceHint = result.source
    ? String(result.source).includes('direction')
      ? (zh ? '来源：方向标注' : 'Source: direction annotator')
      : String(result.source).includes('interactive')
        ? (zh ? '来源：阅片工作台' : 'Source: reader workbench')
        : (zh ? `来源：${result.source}` : `Source: ${result.source}`)
    : null;

  return (
    <div
      className="absolute right-3 z-30 max-w-xs rounded-lg border border-emerald-500/30 bg-black/80 px-3 py-2 text-[11px] text-emerald-100 shadow-lg backdrop-blur"
      style={{ top: '7rem' }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="font-semibold text-emerald-300">{zh ? '辅助回写' : 'Assist write-back'}</div>
        <button
          type="button"
          onClick={openAgent}
          className="inline-flex items-center gap-1 text-emerald-400/90 hover:text-emerald-300"
          title={zh ? '再次打开 /reader' : 'Open /reader again'}
        >
          {zh ? '再开' : 'Reopen'} <ExternalLink size={11} />
        </button>
      </div>
      <div className="mt-1 text-gray-200">
        {zh ? '分层：' : 'Layer: '}{label}{hint ? ` / ${hint}` : ''}
      </div>
      <div className="mt-0.5 text-gray-400">
        {result.in_contact
          ? (zh ? '已接触胃壁' : 'In contact with wall')
          : (zh ? '未接触 / 待确认' : 'No contact / pending')}
        {pts ? (zh ? ` / 灶 ${pts} 点` : ` / lesion ${pts} pts`) : ''}
        {wallPts ? (zh ? ` / 壁 ${wallPts} 点` : ` / wall ${wallPts} pts`) : ''}
        {result.case_id ? ` / ${result.case_id}` : ''}
      </div>
      {sourceHint ? <div className="mt-0.5 text-[10px] text-gray-500">{sourceHint}</div> : null}
      {when ? <div className="mt-0.5 text-[10px] text-gray-500">{when}</div> : null}
      {result.message ? <div className="mt-0.5 text-[10px] text-amber-200/80">{result.message}</div> : null}
      {stage && onApplyStage ? (
        <button
          type="button"
          onClick={() => onApplyStage(stage, { t_hint: hint, layer_label: label })}
          className="mt-2 w-full rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-300 hover:bg-emerald-500/20"
        >
          {zh ? `应用 ${stage} 到 CBM` : `Apply ${stage} to CBM`}
        </button>
      ) : null}
      {maskPoly && onImportMaskPolygon ? (
        <button
          type="button"
          onClick={() => onImportMaskPolygon(maskPoly)}
          className="mt-1.5 w-full rounded border border-cyan-500/40 bg-cyan-500/10 px-2 py-1 text-[10px] font-semibold text-cyan-200 hover:bg-cyan-500/20"
        >
          {zh ? '导入病灶边界到编辑' : 'Import lesion contour'}
        </button>
      ) : null}
      {wallPoly && onImportWallPolygon ? (
        <button
          type="button"
          onClick={() => onImportWallPolygon(wallPoly)}
          className="mt-1.5 w-full rounded border border-orange-500/40 bg-orange-500/10 px-2 py-1 text-[10px] font-semibold text-orange-200 hover:bg-orange-500/20"
        >
          {zh ? '导入胃壁边界到编辑' : 'Import wall contour'}
        </button>
      ) : null}
    </div>
  );
}
