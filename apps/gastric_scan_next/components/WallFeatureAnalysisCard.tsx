'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, BookOpen, Loader2, RefreshCw } from 'lucide-react';
import {
  ensureHumanAssistGeometry,
  formatPenetration,
  toNormPolygon,
  type LayerGeometry,
  type LayerEchoAnalysis,
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
  /** Unit vector from lesion toward lumen; orients estimated wall when wall polygon is missing. */
  lumenPrefer?: [number, number] | null;
  /** Skip auto-run while contour is being dragged */
  paused?: boolean;
  onResult?: (result: LayerAnalyzeResult | null) => void;
};

function svgNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : '0';
}

function buildLocalChannelSvg(
  geom: LayerGeometry,
  centerIdx: number,
  edgeFracs: number[],
  analysis: LayerEchoAnalysis | null,
  frameDataUrl?: string | null,
  frameWidth?: number,
  frameHeight?: number,
): string {
  if (typeof window === 'undefined') return '';
  const wall = geom.wall_pts || [];
  const lesionFace = geom.wall_lesion_pts || [];
  if (wall.length < 3 || lesionFace.length < 3) return '';
  const center = Math.max(0, Math.min(wall.length - 1, centerIdx));
  const half = 10;
  const indices = window.ContactGeom?.localArcIndices?.(wall.length, center, half)
    || Array.from({ length: Math.min(wall.length, half * 2 + 1) }, (_, index) => (
      (center - half + index + wall.length * 2) % wall.length
    ));
  const points = indices.flatMap((index) => [wall[index], lesionFace[index]]).filter(
    (point): point is number[] => Array.isArray(point) && point.length >= 2,
  );
  if (points.length < 4) return '';
  const minX = Math.min(...points.map((point) => point[0])) - 12;
  const maxX = Math.max(...points.map((point) => point[0])) + 12;
  const minY = Math.min(...points.map((point) => point[1])) - 12;
  const maxY = Math.max(...points.map((point) => point[1])) + 12;
  const width = Math.max(24, maxX - minX);
  const height = Math.max(24, maxY - minY);
  const polyline = (items: number[][]) => items
    .map((point) => `${svgNumber(point[0])},${svgNumber(point[1])}`)
    .join(' ');
  const layerCurves = window.ContactGeom?.channelLayerCurvesSvg?.(
    geom,
    center,
    edgeFracs,
    {
      half: 10,
      minDot: 0.55,
      maxSpanPx: 64,
      bandOpacity: 0.28,
      showBands: true,
      showLines: true,
      dashed: Boolean(analysis?.imaginary),
      imaginary: Boolean(analysis?.imaginary),
    },
  ) || window.ContactGeom?.wallLayerArcsSvg?.(
    geom,
    center,
    10,
    edgeFracs,
    { showBands: true, bandOpacity: 0.28 },
  ) || '';
  const wallPoint = wall[center];
  const lesionPoint = lesionFace[center];
  const remain = Number(geom.wall_dists?.[center] || 0);
  const strip = window.ContactGeom?.channelStripOverlaySvg?.(
    wallPoint,
    lesionPoint,
    edgeFracs,
    Math.max(2.5, remain),
    {
      halfWidth: Math.max(2.5, Math.min(8, remain * 0.22)),
      bandOpacity: 0.34,
      showBands: true,
      showLines: true,
      dashed: Boolean(analysis?.imaginary),
      imaginary: Boolean(analysis?.imaginary),
      pxStroke: 0.85,
    },
  ) || '';
  const wallLine = polyline(indices.map((index) => wall[index]).filter(Boolean));
  const lesionLine = polyline(indices.map((index) => lesionFace[index]).filter(Boolean));
  const sourceInfo = analysis && window.ContactGeom?.layerSourceInfo?.(analysis);
  const sourceText = sourceInfo?.badge || (analysis?.imaginary ? '几何参考' : '回声层界');
  const centerWall = wall[center];
  const centerLesion = lesionFace[center];
  const imageLayer = frameDataUrl && frameWidth && frameHeight
    ? `<image href="${frameDataUrl}" x="0" y="0" width="${svgNumber(frameWidth)}" height="${svgNumber(frameHeight)}" preserveAspectRatio="none" opacity=".78"/>`
    : '';
  return `<svg viewBox="${svgNumber(minX)} ${svgNumber(minY)} ${svgNumber(width)} ${svgNumber(height)}" width="100%" height="148" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#020617;border:1px solid rgba(255,255,255,.12);border-radius:8px">
    ${imageLayer}
    <rect x="${svgNumber(minX)}" y="${svgNumber(minY)}" width="${svgNumber(width)}" height="${svgNumber(height)}" fill="#020617" opacity="${imageLayer ? '0.16' : '1'}"/>
    <polyline points="${wallLine}" fill="none" stroke="#fb923c" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    <polyline points="${lesionLine}" fill="none" stroke="#22d3ee" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    ${layerCurves}
    ${strip}
    <line x1="${svgNumber(centerWall[0])}" y1="${svgNumber(centerWall[1])}" x2="${svgNumber(centerLesion[0])}" y2="${svgNumber(centerLesion[1])}" stroke="#f8fafc" stroke-width="1.2" stroke-dasharray="4 3" opacity=".85"/>
    <circle cx="${svgNumber(centerWall[0])}" cy="${svgNumber(centerWall[1])}" r="3.2" fill="#fb923c" stroke="#fff" stroke-width="1"/>
    <circle cx="${svgNumber(centerLesion[0])}" cy="${svgNumber(centerLesion[1])}" r="3.2" fill="#22d3ee" stroke="#fff" stroke-width="1"/>
    <text x="${svgNumber(minX + 5)}" y="${svgNumber(minY + 11)}" fill="#94a3b8" font-size="9">${sourceText}</text>
    <text x="${svgNumber(maxX - 5)}" y="${svgNumber(minY + 11)}" fill="#cbd5e1" font-size="9" text-anchor="end">局部通道</text>
  </svg>`;
}

export function WallFeatureAnalysisCard({
  zh = true,
  lesionPolygon,
  wallPolygon,
  frameSize,
  frameDataUrl,
  pick,
  wallOffsetPx,
  lumenPrefer = null,
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
      const { LayerBridge } = await ensureHumanAssistGeometry();
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
        lumenPrefer: lumenPrefer || undefined,
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
  }, [canRun, frameSize, lesionPolygon, wallPolygon, frameDataUrl, offset, pick, lumenPrefer, onResult, zh]);

  // Auto-run when lesion contour changes (debounced); skip while dragging
  useEffect(() => {
    if (!canRun || paused) return;
    const t = window.setTimeout(() => {
      void run();
    }, 320);
    return () => window.clearTimeout(t);
  }, [canRun, paused, lesionPolygon, wallPolygon, frameDataUrl, offset, pick?.x, pick?.y, lumenPrefer?.[0], lumenPrefer?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const fineVisuals = useMemo(() => {
    if (typeof window === 'undefined' || !result?.ok || !result.geom) {
      return {
        channelSvg: '',
        profileSvg: '',
        remainSvg: '',
        center: null as number | null,
        remain: null as number | null,
        snr: null as number | null,
        clarity: null as number | null,
        source: '',
      };
    }
    const analysis = result.analysis || null;
    const edgeFracs = analysis?.edgeFracs || result.plan?.edgeFracs || [];
    const center = Number.isInteger(result.pickIdx)
      ? Number(result.pickIdx)
      : Number(result.geom.deep_idx || 0);
    const channelSvg = buildLocalChannelSvg(
      result.geom,
      center,
      edgeFracs,
      analysis,
      frameDataUrl,
      result.videoW,
      result.videoH,
    );
    let profileSvg = '';
    let remainSvg = '';
    try {
      profileSvg = analysis && window.ContactGeom?.echoClusterSvg
        ? window.ContactGeom.echoClusterSvg(analysis, 280, 92) || ''
        : '';
      remainSvg = window.ContactGeom?.remainProfileSvg
        ? window.ContactGeom.remainProfileSvg(result.geom, center, 18, 280, 64) || ''
        : '';
    } catch {
      profileSvg = '';
      remainSvg = '';
    }
    const sourceInfo = analysis && window.ContactGeom?.layerSourceInfo?.(analysis);
    return {
      channelSvg,
      profileSvg,
      remainSvg,
      center,
      remain: Number.isFinite(result.pen?.remain)
        ? Number(result.pen?.remain)
        : Number.isFinite(result.geom.wall_dists?.[center])
          ? Number(result.geom.wall_dists?.[center])
          : null,
      snr: Number.isFinite(analysis?.snr) ? Number(analysis?.snr) : null,
      clarity: Number.isFinite(analysis?.clarity) ? Number(analysis?.clarity) : null,
      source: sourceInfo?.badge || analysis?.source || '',
    };
  }, [frameDataUrl, result]);

  return (
    <div className="rounded-xl border border-emerald-400/25 bg-emerald-950/30 p-3 text-[11px] text-emerald-50/90">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold text-emerald-100">
          <Activity size={13} />
          {zh ? '组织层观察（系统辅助）' : 'Tissue layer observation'}
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
          ? '先观察胃壁组织层次，再结合病灶范围和连续帧进行判断'
          : 'Observe tissue layers first, then combine lesion extent and continuous frames'}
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
                : (zh ? '未形成稳定接触, 不输出层次读数' : 'No stable contact, no layer readout')}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[9px] text-slate-500">
              <span>{zh ? '证据模式' : 'Evidence mode'}:</span>
              <span className="text-slate-300">
                {result.source?.badge
                  || (result.analysis?.imaginary
                    ? (zh ? '几何参考' : 'Geometric reference')
                    : result.analysis
                      ? (zh ? '当前帧回声剖面' : 'Current-frame echo profile')
                      : (zh ? '几何参考' : 'Geometric reference'))}
              </span>
              {result.analysis?.imaginary ? (
                <span className="rounded border border-amber-300/20 bg-amber-400/10 px-1 text-amber-200">
                  {zh ? '推断层界' : 'Inferred interfaces'}
                </span>
              ) : null}
            </div>
          </div>

          {stackHtml ? (
            <div
              className="overflow-hidden rounded-lg border border-white/10 bg-black/40 p-1"
              // ContactGeom returns trusted static SVG markup from local vendor copy
              dangerouslySetInnerHTML={{ __html: stackHtml }}
            />
          ) : null}

          {fineVisuals.channelSvg || fineVisuals.profileSvg || fineVisuals.remainSvg ? (
            <details open className="rounded-lg border border-cyan-300/20 bg-slate-950/40">
              <summary className="cursor-pointer list-none px-2 py-1.5 text-[10px] font-semibold text-cyan-100">
                <span className="inline-flex items-center gap-1.5">
                  <Activity size={11} />
                  {zh ? '细粒度胃壁通道' : 'Fine-grained wall channel'}
                </span>
                <span className="float-right text-[9px] font-normal text-slate-500">
                  {fineVisuals.source || (zh ? '当前帧' : 'Current frame')}
                </span>
              </summary>
              <div className="space-y-2 border-t border-white/10 p-2">
                {fineVisuals.channelSvg ? (
                  <div>
                    <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-slate-400">
                      <span className="inline-flex items-center gap-1">
                        <span className="h-1.5 w-4 rounded-full bg-orange-400" />
                        {zh ? '胃壁参考边界' : 'Wall reference'}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span className="h-1.5 w-4 rounded-full bg-cyan-300" />
                        {zh ? '病灶前沿' : 'Lesion front'}
                      </span>
                      <span>{zh ? '彩线=局部层界' : 'Color lines = local interfaces'}</span>
                    </div>
                    <div
                      className="overflow-hidden rounded-lg"
                      dangerouslySetInnerHTML={{ __html: fineVisuals.channelSvg }}
                    />
                  </div>
                ) : null}
                {fineVisuals.profileSvg ? (
                  <div>
                    <div className="mb-1 text-[9px] text-slate-500">
                      {zh ? '局部回声剖面, 腔侧 → 浆膜侧' : 'Local echo profile, lumen → serosa'}
                    </div>
                    <div
                      className="overflow-hidden rounded-lg"
                      dangerouslySetInnerHTML={{ __html: fineVisuals.profileSvg }}
                    />
                  </div>
                ) : null}
                {!fineVisuals.profileSvg && fineVisuals.remainSvg ? (
                  <div>
                    <div className="mb-1 text-[9px] text-slate-500">
                      {zh ? '局部剩余壁厚剖面' : 'Local remaining-wall profile'}
                    </div>
                    <div
                      className="overflow-hidden rounded-lg"
                      dangerouslySetInnerHTML={{ __html: fineVisuals.remainSvg }}
                    />
                  </div>
                ) : null}
                <div className="grid grid-cols-4 gap-1 text-[9px]">
                  <div className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-1">
                    <div className="text-slate-500">{zh ? '局部余厚' : 'Remain'}</div>
                    <div className="font-mono text-slate-200">
                      {fineVisuals.remain != null ? `${fineVisuals.remain.toFixed(1)} px` : '—'}
                    </div>
                  </div>
                  <div className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-1">
                    <div className="text-slate-500">{zh ? '占壁厚' : 'Pen.'}</div>
                    <div className="font-mono text-cyan-100">
                      {Number.isFinite(result.pen?.ratio) ? `${Math.round(Number(result.pen?.ratio) * 100)}%` : '—'}
                    </div>
                  </div>
                  <div className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-1">
                    <div className="text-slate-500">SNR</div>
                    <div className="font-mono text-amber-100">
                      {fineVisuals.snr != null ? fineVisuals.snr.toFixed(1) : '—'}
                    </div>
                  </div>
                  <div className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-1">
                    <div className="text-slate-500">{zh ? '清晰度' : 'Clarity'}</div>
                    <div className="font-mono text-emerald-100">
                      {fineVisuals.clarity != null ? fineVisuals.clarity.toFixed(1) : '—'}
                    </div>
                  </div>
                </div>
                <p className="text-[9px] leading-relaxed text-slate-500">
                  {zh
                    ? '该局部通道用于定位可疑层界和接触弧，不是组织学切片，也不单独作为病理浸润结论。'
                    : 'This local channel locates candidate interfaces and contact arcs. It is not histology and is not a standalone pathology conclusion.'}
                </p>
              </div>
            </details>
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
              <span className="text-slate-400">{zh ? '外侧边界代理' : 'Outer-boundary proxy'}</span>
              <strong className="text-right">
                {result.analysis
                  ? result.analysis.imaginary
                    ? (zh ? '层界为几何/假想参考, 需回看原始回声' : 'Geometric/inferred reference, review raw echo')
                    : (result.analysis.stable
                      ? (zh ? '当前帧回声层界相对稳定' : 'Current-frame echo interfaces relatively stable')
                      : (zh ? '当前帧层界稳定性有限' : 'Current-frame interface stability is limited'))
                  : (zh ? '未提供像素层界, 仅作几何参考' : 'No pixel-derived interfaces, geometric reference only')}
              </strong>
            </div>
            <div className="flex justify-between gap-2 col-span-2">
              <span className="text-slate-400">{zh ? '当前帧几何要点' : 'Current-frame geometry'}</span>
              <strong className="text-right text-[9px] leading-snug">
                {zh
                  ? [
                      result.inContact ? '与胃壁参考边界形成接触弧' : '未形成稳定接触弧',
                      Number.isFinite(result.pen?.ratio)
                        ? `局部占壁厚几何代理 ${Math.round(Number(result.pen?.ratio) * 100)}%`
                        : '局部占壁厚代理待测',
                      result.analysis?.imaginary
                        ? '层界为推断参考'
                        : result.analysis
                          ? '含当前帧回声剖面'
                          : '未使用像素层界',
                    ].join('; ')
                  : 'current-frame contour, contact, and layer proxies; not tissue or pathology findings'}
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
