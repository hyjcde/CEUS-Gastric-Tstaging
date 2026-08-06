'use client';

import React, { useMemo } from 'react';
import { FileText, Gauge } from 'lucide-react';
import type { Patient } from '@/types';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import {
  bboxShortAxisRatio,
  computeGcUsTscore,
  polygonIrregularity,
  type GcUsTscoreResult,
} from '@/lib/gc-us-tscore';
import { GcUsEvidencePanel } from '@/components/GcUsEvidencePanel';
import type { GcUsReportState } from '@/lib/gc-us-report-template';

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
  onEvidenceStateChange?: (state: GcUsReportState) => void;
};

const EMPTY_CLINICAL: Record<string, unknown> = {};
const EMPTY_POLYGON: number[][] = [];

export function GcUsImagingReportCard({
  patient,
  assist,
  zh = true,
  onApplyCtStage,
  onEvidenceStateChange,
}: Props) {
  const packed = useMemo(() => {
    const clin = patient?.clinical;
    const lengthCmClin = clin?.tumorSize?.length ?? null;
    const thicknessCmClin = clin?.tumorSize?.thickness ?? null;
    const poly = assist?.lesionPolygon || [];
    // Pixel geometry has no device calibration. Keep it as px in the evidence
    // panel; do not convert it to pseudo-mm with a fixed FOV assumption.
    const lengthCm = lengthCmClin;
    const thicknessCm = thicknessCmClin;
    const irreg = polygonIrregularity(poly);
    const shortR = bboxShortAxisRatio(poly);
    const layer = assist?.layerResult;
    const label = layer?.layer?.label || null;
    const tHint = layer?.layer?.tHint || null;
    const inContact = layer?.inContact ?? null;
    const occ = layer?.pen?.ratio ?? layer?.analysis?.ratioHint ?? null;
    const clinicalRecord = clin as (Record<string, unknown> | undefined);
    const clinicalSerosa = String(clinicalRecord?.serosaChange || clinicalRecord?.serosa_status || '').trim();
    const serosaDisrupted = /中断|破坏|受侵|disrupt|involv/i.test(clinicalSerosa);

    const ceaRaw = clin?.biomarkers?.cea_positive ?? clin?.biomarkers?.cea;
    const ceaPositive =
      typeof ceaRaw === 'boolean'
        ? ceaRaw
        : typeof ceaRaw === 'string'
          ? /阳|\+|positive/i.test(ceaRaw)
          : typeof ceaRaw === 'number' && Number.isFinite(ceaRaw)
            ? ceaRaw > 5
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
      structuralEvidence: 'proxy',
    });

    return { tscore };
  }, [patient, assist]);

  if (!patient) return null;

  const { tscore } = packed;
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
            ? '先框选或点选病灶，质量通过后再进行胃壁和 T 分期观察。'
            : 'Create a lesion prompt before wall and T-stage analysis.'}
        </div>
      ) : (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-white/10 bg-black/30 p-2 text-[10px] leading-relaxed text-slate-200">
          <FileText size={12} className="mt-0.5 shrink-0 text-cyan-300" />
          <span>{zh ? '报告正文按七项核心影像征象生成，评分仅作为软参考。' : 'The report follows seven core imaging signs; the score is a soft reference.'}</span>
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
      {tscore.status !== 'supported' ? (
        <div className="mt-1 rounded border border-amber-400/25 bg-amber-500/10 px-2 py-1 text-[9px] leading-relaxed text-amber-100">
          {zh
            ? `阶段状态：${tscore.status === 'not_assessable' ? '不可评估' : '待补充证据'}；${tscore.uncertaintyReasons.join('、')}`
            : `Stage status: ${tscore.status}; ${tscore.uncertaintyReasons.join(', ')}`}
        </div>
      ) : null}

      <div className="mt-3">
        <GcUsEvidencePanel
          caseId={patient.patient_id}
          frameId={patient.id}
          clinical={(patient.clinical || EMPTY_CLINICAL) as unknown as Record<string, unknown>}
          lesionPolygon={assist?.lesionPolygon || EMPTY_POLYGON}
          wallPolygon={assist?.wallPolygon || EMPTY_POLYGON}
          frameSize={assist?.frameSize}
          layerResult={assist?.layerResult}
          productStage={tscore.ctStage}
          zh={zh}
          onStateChange={onEvidenceStateChange}
        />
      </div>

      {onApplyCtStage && hasFeatures && tscore.status === 'supported' && tscore.ctStage !== 'cTx' ? (
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
