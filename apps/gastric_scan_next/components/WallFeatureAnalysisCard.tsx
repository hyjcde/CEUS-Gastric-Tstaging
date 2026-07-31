'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, BookOpen, Loader2, RefreshCw } from 'lucide-react';
import {
  ensureHumanAssistGeometry,
  formatPenetration,
  toNormPolygon,
  type LayerAnalyzeResult,
} from '@/lib/human-assist/load-contact-geom';
import { HUMAN_ASSIST_ALGO_SOURCE, HUMAN_ASSIST_MEETING_BULLETS } from '@/lib/human-assist/meeting-notes';

type Props = {
  zh?: boolean;
  lesionPolygon: number[][];
  wallPolygon: number[][];
  /** Image or current video frame size */
  frameSize: { width: number; height: number } | null;
  /** Optional JPEG/PNG data URL of current frame for echo-ray analysis */
  frameDataUrl?: string | null;
  /** Optional infiltration pick in image pixels */
  pick?: { x: number; y: number } | null;
  wallOffsetPx?: number;
  /** Skip auto-run while contour is being dragged */
  paused?: boolean;
  onResult?: (result: LayerAnalyzeResult | null) => void;
};

export function WallFeatureAnalysisCard({
  zh = true,
  lesionPolygon,
  wallPolygon,
  frameSize,
  frameDataUrl,
  pick,
  wallOffsetPx,
  paused = false,
  onResult,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LayerAnalyzeResult | null>(null);
  const [showNotes, setShowNotes] = useState(false);
  const [offset, setOffset] = useState(wallOffsetPx ?? 0);

  useEffect(() => {
    if (Number.isFinite(wallOffsetPx)) setOffset(wallOffsetPx as number);
  }, [wallOffsetPx]);

  const canRun = lesionPolygon.length >= 3 && !!frameSize?.width && !!frameSize?.height;

  const run = useCallback(async () => {
    if (!canRun || !frameSize) {
      setError(zh ? '需要病灶轮廓（≥3 点）与帧尺寸' : 'Need lesion polygon and frame size');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { ContactGeom, LayerBridge } = await ensureHumanAssistGeometry();
      const maskNorm = toNormPolygon(lesionPolygon, frameSize.width, frameSize.height);
      const analyzed = await LayerBridge.analyzeLayersFromMask({
        maskPolygon: maskNorm,
        wallPts: wallPolygon.length >= 3 ? wallPolygon : undefined,
        frameDataUrl: frameDataUrl || undefined,
        videoW: frameSize.width,
        videoH: frameSize.height,
        wallOffsetPx: offset || undefined,
        halfWidth: 8,
        pickX: pick?.x,
        pickY: pick?.y,
      });
      setResult(analyzed);
      onResult?.(analyzed);
      if (!analyzed.ok) setError(analyzed.message || (zh ? '分层失败' : 'Layer analysis failed'));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'analyze failed';
      setError(msg);
      setResult(null);
      onResult?.(null);
    } finally {
      setBusy(false);
    }
  }, [canRun, frameSize, lesionPolygon, wallPolygon, frameDataUrl, offset, pick, onResult, zh]);

  // Auto-run when lesion contour changes (debounced); skip while dragging
  useEffect(() => {
    if (!canRun || paused) return;
    const t = window.setTimeout(() => {
      void run();
    }, 320);
    return () => window.clearTimeout(t);
  }, [canRun, paused, lesionPolygon, wallPolygon, frameDataUrl, offset, pick?.x, pick?.y]); // eslint-disable-line react-hooks/exhaustive-deps

  const penText = useMemo(() => {
    if (!result?.ok || !window.ContactGeom) return '—';
    return formatPenetration(window.ContactGeom, result.pen);
  }, [result]);

  const stackHtml = useMemo(() => {
    if (!result?.ok || !window.ContactGeom?.wallStackSvg) return '';
    const fracs = result.analysis?.edgeFracs || result.plan?.edgeFracs || [];
    if (!fracs.length) return '';
    const occ = Number.isFinite(result.pen?.ratio)
      ? Number(result.pen?.ratio)
      : Number(result.analysis?.ratioHint || 0);
    try {
      return window.ContactGeom.wallStackSvg(fracs, occ, { w: 220, h: 120 }) || '';
    } catch {
      return '';
    }
  }, [result]);

  return (
    <div className="rounded-xl border border-emerald-400/25 bg-emerald-950/30 p-3 text-[11px] text-emerald-50/90">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold text-emerald-100">
          <Activity size={13} />
          {zh ? '胃壁特征分析（人机互助算法）' : 'Wall feature analysis'}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowNotes((v) => !v)}
            className="rounded border border-white/15 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-white/5"
            title={zh ? '会议纪要要点' : 'Meeting notes'}
          >
            <BookOpen size={12} className="inline" /> {zh ? '纪要' : 'Notes'}
          </button>
          <button
            type="button"
            disabled={!canRun || busy}
            onClick={() => void run()}
            className="inline-flex items-center gap-1 rounded border border-emerald-400/40 px-1.5 py-0.5 text-[10px] text-emerald-100 disabled:opacity-40"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {zh ? '重算' : 'Re-run'}
          </button>
        </div>
      </div>

      <div className="mb-2 text-[10px] text-emerald-200/70">
        {zh
          ? '迁自 direction_demo / ContactGeom: 接触门控, 占壁厚, 达层, 回声分层'
          : 'Migrated from ContactGeom human-assist stack'}
      </div>

      {showNotes && (
        <div className="mb-2 max-h-36 space-y-1 overflow-y-auto rounded-lg border border-white/10 bg-black/30 p-2 text-[10px] text-slate-300">
          <div className="font-semibold text-amber-200/90">
            {zh ? '会议纪要 → 算法验收点' : 'Meeting → acceptance'}
          </div>
          {HUMAN_ASSIST_MEETING_BULLETS.map((b) => (
            <div key={b.id}>
              <span className="text-amber-300/90">{b.id}</span> {b.title}：{b.detail}
            </div>
          ))}
          <div className="pt-1 text-[9px] text-slate-500">
            src: {HUMAN_ASSIST_ALGO_SOURCE.origin}
          </div>
        </div>
      )}

      {!canRun && (
        <div className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1.5 text-[10px] text-amber-100">
          {zh
            ? '先 SAM / 编辑得到青, 病灶轮廓（可选橙, 胃壁），再自动计算。'
            : 'Create cyan lesion contour first (optional orange wall).'}
        </div>
      )}

      {error && (
        <div className="mb-2 rounded border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] text-rose-100">
          {error}
        </div>
      )}

      {result?.ok && (
        <div className="space-y-1.5">
          <div
            className="rounded-lg border px-2 py-2"
            style={{ borderColor: `${result.layer?.tone || '#8b93a1'}66` }}
          >
            <div className="text-[10px] text-slate-400">{zh ? '达层读数' : 'Layer read'}</div>
            <div
              className="text-sm font-bold"
              style={{ color: result.layer?.tone || '#e2e8f0' }}
            >
              {result.inContact
                ? `${result.layer?.label || '—'}, ${result.layer?.tHint || ''}`
                : (zh ? '未接触, 不可分期' : 'No contact, no staging')}
            </div>
          </div>

          {stackHtml ? (
            <div
              className="overflow-hidden rounded-lg border border-white/10 bg-black/40 p-1"
              // ContactGeom returns trusted static SVG markup from local vendor copy
              dangerouslySetInnerHTML={{ __html: stackHtml }}
            />
          ) : null}

          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
            <div className="flex justify-between gap-2">
              <span className="text-slate-400">{zh ? '接触' : 'Contact'}</span>
              <strong>{result.inContact ? (zh ? '接触弧内' : 'In contact') : (zh ? '未接触' : 'No')}</strong>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-slate-400">{zh ? '占壁厚' : 'Penetration'}</span>
              <strong>{penText}</strong>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-slate-400">{zh ? '接触弧' : 'Arc'}</span>
              <strong>
                {Number.isFinite(result.geom?.contact_ratio)
                  ? `${Math.round(Number(result.geom?.contact_ratio) * 100)}%`
                  : '—'}
              </strong>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-slate-400">{zh ? '层界' : 'Edges'}</span>
              <strong>{result.analysis?.edgeFracs?.length || result.plan?.edgeFracs?.length || 0}</strong>
            </div>
            <div className="flex justify-between gap-2 col-span-2">
              <span className="text-slate-400">{zh ? '胃壁来源' : 'Wall source'}</span>
              <strong className="text-right">
                {result.source?.badge
                  || (result.wallEstimated
                    ? (zh ? '分割外推胃壁' : 'Estimated wall')
                    : (zh ? '手绘/预置胃壁' : 'Manual wall'))}
              </strong>
            </div>
            <div className="flex justify-between gap-2 col-span-2">
              <span className="text-slate-400">{zh ? '浆膜提示' : 'Serosa hint'}</span>
              <strong className="text-right">
                {/L5|浆膜|T4|T3–T4|T3-T4/i.test(`${result.layer?.label || ''} ${result.layer?.tHint || ''}`)
                  ? (zh ? '浆膜面欠光整/中断倾向' : 'Serosa irregular/disrupted')
                  : (zh ? '浆膜面尚光整倾向' : 'Serosa relatively intact')}
              </strong>
            </div>
            <div className="flex justify-between gap-2 col-span-2">
              <span className="text-slate-400">{zh ? '影像描述要点' : 'Imaging cues'}</span>
              <strong className="text-right text-[9px] leading-snug">
                {zh
                  ? [
                      result.inContact ? '胃壁连续性破坏' : '接触关系不确定',
                      Number(result.pen?.ratio || result.analysis?.ratioHint || 0) >= 0.7
                        ? '活动度下降/脂肪间隙模糊'
                        : Number(result.pen?.ratio || result.analysis?.ratioHint || 0) >= 0.35
                          ? '局部增厚僵硬感'
                          : '胃周间隙尚清',
                    ].join('; ')
                  : 'wall continuity / motility cues'}
              </strong>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <span className="text-[10px] text-slate-400">{zh ? '壁偏移' : 'Offset'}</span>
            <button
              type="button"
              className="rounded border border-white/15 px-2 py-0.5"
              onClick={() => setOffset((v) => Math.max(8, (v || Math.round(result.offsetPx || 24)) - 8))}
            >
              −
            </button>
            <span className="font-mono text-[10px]">{Math.round(offset || result.offsetPx || 0)} px</span>
            <button
              type="button"
              className="rounded border border-white/15 px-2 py-0.5"
              onClick={() => setOffset((v) => (v || Math.round(result.offsetPx || 24)) + 8)}
            >
              +
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
