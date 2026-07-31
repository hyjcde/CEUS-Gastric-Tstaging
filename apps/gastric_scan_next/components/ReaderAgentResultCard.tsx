'use client';

import React, { useEffect, useState } from 'react';
import { Compass, ExternalLink } from 'lucide-react';
import type { Patient } from '@/types';
import { buildHumanAssistUrl, buildReaderAppUrl } from '@/lib/reading-agent-url';
import { useRouter } from 'next/navigation';

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
  const [result, setResult] = useState<ReaderAgentResult | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!patient?.id && !patient?.patient_id) {
      setResult(null);
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
    router.push(buildReaderAppUrl(patient));
  };

  const openHumanAssist = () => {
    window.open(buildHumanAssistUrl(patient), '_blank', 'noopener,noreferrer');
  };

  if (!result) {
    return (
      <div className="absolute top-3 right-3 z-30 max-w-xs rounded-lg border border-white/10 bg-black/70 px-3 py-2 text-[11px] text-gray-300 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between gap-2">
          <span className="text-gray-400">阅片 / 分层回写</span>
          <button
            type="button"
            onClick={openAgent}
            className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300"
            title="打开 /reader：SAM + 胃壁分层"
          >
            打开 <ExternalLink size={11} />
          </button>
        </div>
        <div className="mt-1 text-[10px] text-gray-500">
          尚无回写。可用「阅片Agent」或人机互助 HTML（带 callback）对当前帧分割分层，结果会回到此处。
        </div>
        <button
          type="button"
          onClick={openHumanAssist}
          className="mt-2 inline-flex w-full items-center justify-center gap-1 rounded border border-orange-500/30 bg-orange-500/10 px-2 py-1 text-[10px] text-orange-200 hover:bg-orange-500/20"
        >
          <Compass size={11} /> 人机互助 HTML（可回写）
        </button>
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
      ? '来源：人机互助'
      : String(result.source).includes('interactive')
        ? '来源：HTML 阅片 Agent'
        : `来源：${result.source}`
    : null;

  return (
    <div className="absolute top-3 right-3 z-30 max-w-xs rounded-lg border border-emerald-500/30 bg-black/80 px-3 py-2 text-[11px] text-emerald-100 shadow-lg backdrop-blur">
      <div className="flex items-center justify-between gap-2">
        <div className="font-semibold text-emerald-300">辅助回写</div>
        <button
          type="button"
          onClick={openAgent}
          className="inline-flex items-center gap-1 text-emerald-400/90 hover:text-emerald-300"
          title="再次打开 /reader"
        >
          再开 <ExternalLink size={11} />
        </button>
      </div>
      <div className="mt-1 text-gray-200">
        分层：{label}{hint ? ` · ${hint}` : ''}
      </div>
      <div className="mt-0.5 text-gray-400">
        {result.in_contact ? '已接触胃壁' : '未接触 / 待确认'}
        {pts ? ` · 灶 ${pts} 点` : ''}
        {wallPts ? ` · 壁 ${wallPts} 点` : ''}
        {result.case_id ? ` · ${result.case_id}` : ''}
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
          应用 {stage} 到 CBM
        </button>
      ) : null}
      {maskPoly && onImportMaskPolygon ? (
        <button
          type="button"
          onClick={() => onImportMaskPolygon(maskPoly)}
          className="mt-1.5 w-full rounded border border-cyan-500/40 bg-cyan-500/10 px-2 py-1 text-[10px] font-semibold text-cyan-200 hover:bg-cyan-500/20"
        >
          导入病灶边界到编辑
        </button>
      ) : null}
      {wallPoly && onImportWallPolygon ? (
        <button
          type="button"
          onClick={() => onImportWallPolygon(wallPoly)}
          className="mt-1.5 w-full rounded border border-orange-500/40 bg-orange-500/10 px-2 py-1 text-[10px] font-semibold text-orange-200 hover:bg-orange-500/20"
        >
          导入胃壁边界到编辑
        </button>
      ) : null}
      <button
        type="button"
        onClick={openHumanAssist}
        className="mt-1.5 inline-flex w-full items-center justify-center gap-1 rounded border border-white/10 bg-white/5 px-2 py-1 text-[10px] text-gray-300 hover:bg-white/10"
      >
        <Compass size={11} /> 人机互助 HTML
      </button>
    </div>
  );
}
