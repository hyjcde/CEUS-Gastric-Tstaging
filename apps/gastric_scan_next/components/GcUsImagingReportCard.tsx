'use client';

import React, { useMemo } from 'react';
import { FileText, Gauge } from 'lucide-react';
import type { Patient } from '@/types';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import {
  bboxShortAxisRatio,
  buildImagingNarrative,
  computeGcUsTscore,
  estimateAxesMm,
  polygonIrregularity,
  type GcUsTscoreResult,
} from '@/lib/gc-us-tscore';

export type ImagingAssistState = {
  layerResult: LayerAnalyzeResult | null;
  lesionPolygon: number[][];
  wallPolygon: number[][];
  frameSize: { width: number; height: number } | null;
};

type Props = {
  patient: Patient | null;
  assist: ImagingAssistState | null;
  zh?: boolean;
  onApplyCtStage?: (ct: string) => void;
};

function mmFromCm(cm?: number | null): number | null {
  if (cm == null || !Number.isFinite(cm) || cm <= 0) return null;
  return cm * 10;
}

export function GcUsImagingReportCard({ patient, assist, zh = true, onApplyCtStage }: Props) {
  const packed = useMemo(() => {
    const clin = patient?.clinical;
    const lengthCmClin = clin?.tumorSize?.length ?? null;
    const thicknessCmClin = clin?.tumorSize?.thickness ?? null;
    const poly = assist?.lesionPolygon || [];
    const axes =
      poly.length >= 3 && assist?.frameSize ? estimateAxesMm(poly, assist.frameSize) : null;
    const lengthCm =
      lengthCmClin ?? (axes ? axes.lengthMm / 10 : null);
    const thicknessCm =
      thicknessCmClin ?? (axes ? axes.thicknessMm / 10 : null);
    const irreg = polygonIrregularity(poly);
    const shortR = bboxShortAxisRatio(poly);
    const layer = assist?.layerResult;
    const label = layer?.layer?.label || null;
    const tHint = layer?.layer?.tHint || null;
    const inContact = layer?.inContact ?? null;
    const occ = layer?.pen?.ratio ?? layer?.analysis?.ratioHint ?? null;
    const serosaDisrupted = /L5|浆膜|T4|T3–T4|T3-T4/i.test(`${label || ''} ${tHint || ''}`);

    const ceaRaw = (clin as { cea?: string | number | boolean } | undefined)?.cea;
    const ceaPositive =
      typeof ceaRaw === 'boolean'
        ? ceaRaw
        : typeof ceaRaw === 'string'
          ? /阳|\+|positive/i.test(ceaRaw)
          : null;

    const tscore: GcUsTscoreResult = computeGcUsTscore({
      lengthCm,
      thicknessCm,
      irregularity: irreg,
      shortAxisRatio: shortR,
      ceaPositive,
      layerLabel: label,
      tHint,
      inContact,
      occupationRatio: typeof occ === 'number' ? occ : null,
      serosaDisrupted,
    });

    const narrative = buildImagingNarrative({
      location: clin?.location || null,
      lengthMm: mmFromCm(lengthCmClin) ?? axes?.lengthMm ?? null,
      thicknessMm: mmFromCm(thicknessCmClin) ?? axes?.thicknessMm ?? null,
      irregularity: irreg,
      inContact,
      layerLabel: label,
      tHint,
      occupationRatio: typeof occ === 'number' ? occ : null,
      serosaDisrupted,
      tscore,
      zh,
    });

    return { tscore, narrative, label, tHint, inContact, occ };
  }, [patient, assist, zh]);

  if (!patient) return null;

  const { tscore, narrative } = packed;
  const hasFeatures = Boolean(assist?.layerResult || (assist?.lesionPolygon?.length || 0) >= 3);

  return (
    <div className="rounded-xl border border-cyan-400/25 bg-cyan-950/25 p-3 text-[11px] text-cyan-50/90">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold text-cyan-100">
          <Gauge size={13} />
          {zh ? 'GC-US T-score / 影像描述' : 'GC-US T-score / imaging'}
        </div>
        <span className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-200">
          {tscore.total}/{tscore.maxTotal}, {tscore.ctStage}
        </span>
      </div>

      {!hasFeatures ? (
        <div className="mb-2 rounded-lg border border-dashed border-white/15 bg-black/20 p-2 text-[10px] text-slate-400">
          {zh
            ? '打开「边界编辑 / SAM」点选病灶后，此处自动生成超声所见与 GC-US 评分。'
            : 'Open boundary edit / SAM and click the lesion to generate findings and score.'}
        </div>
      ) : (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-white/10 bg-black/30 p-2 text-[10px] leading-relaxed text-slate-200">
          <FileText size={12} className="mt-0.5 shrink-0 text-cyan-300" />
          <span>{narrative}</span>
        </div>
      )}

      <div className="space-y-1">
        {tscore.items.map((it) => (
          <div key={it.id} className="flex items-center justify-between gap-2 text-[9px] text-slate-400">
            <span className="truncate">
              <span className="text-slate-300">{it.label}</span>
              <span className="ml-1 opacity-70">{it.detail}</span>
            </span>
            <span className="shrink-0 font-mono text-cyan-200">
              {it.points}/{it.max}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-2 text-[9px] leading-relaxed text-slate-500">{tscore.mappingNote}</div>

      {onApplyCtStage && hasFeatures ? (
        <button
          type="button"
          onClick={() => onApplyCtStage(tscore.ctStage.replace(/^c/, ''))}
          className="mt-2 w-full rounded border border-cyan-400/40 bg-cyan-500/10 px-2 py-1.5 text-[10px] font-semibold text-cyan-100 hover:bg-cyan-500/20"
        >
          {zh ? `应用 ${tscore.ctStage} 到诊断` : `Apply ${tscore.ctStage}`}
        </button>
      ) : null}
    </div>
  );
}
