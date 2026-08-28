'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import {
  ensureHumanAssistGeometry,
  toNormPolygon,
  type LayerEchoBand,
  type LayerGeometry,
  type LayerEchoAnalysis,
  type LayerAnalyzeResult,
} from '@/lib/human-assist/load-contact-geom';
import {
  WALL_LAYER_GUIDES,
  cropChannelOverview,
  cropSquareZoom,
  lerpPoint,
  loadFrameImage,
  type WallLayerCode,
} from '@/lib/human-assist/wall-layer-medical';

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

const ECHO_LAYER_NAMES = [
  { zh: '黏膜', en: 'Mucosa' },
  { zh: '黏膜肌', en: 'MM' },
  { zh: '黏膜下', en: 'SM' },
  { zh: '固有肌', en: 'MP' },
  { zh: '浆膜', en: 'Serosa' },
] as const;

function buildEchoProfileSvg(
  values: number[],
  bands: Array<{ kind?: 'bright' | 'dark'; f0?: number; f1?: number }>,
  wallFrac: number | null,
  peakFrac: number | null,
  zh: boolean,
): string {
  if (values.length < 4) return '';
  const w = 360;
  const h = 148;
  const padL = 28;
  const padR = 10;
  const padT = 16;
  const padB = 22;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const vmin = Math.min(...values);
  const vmax = Math.max(...values);
  const span = Math.max(1, vmax - vmin);
  const xAt = (frac: number) => padL + Math.max(0, Math.min(1, frac)) * plotW;
  const yAt = (value: number) => padT + plotH * (1 - (value - vmin) / span);
  const points = values.map((value, index) => {
    const x = padL + (index / Math.max(1, values.length - 1)) * plotW;
    return `${x.toFixed(1)},${yAt(value).toFixed(1)}`;
  });
  const area = `${padL.toFixed(1)},${(padT + plotH).toFixed(1)} ${points.join(' ')} ${(padL + plotW).toFixed(1)},${(padT + plotH).toFixed(1)}`;
  const bandList = bands.length
    ? bands
    : ECHO_LAYER_NAMES.map((_, index) => ({
      kind: index % 2 === 0 ? 'dark' : 'bright',
      f0: index / ECHO_LAYER_NAMES.length,
      f1: (index + 1) / ECHO_LAYER_NAMES.length,
    }));
  const bandRects = bandList.map((band) => {
    const x0 = xAt(Number(band.f0) || 0);
    const x1 = xAt(Number(band.f1) || 1);
    const fill = band.kind === 'bright' ? '#fbbf24' : '#38bdf8';
    return `<rect x="${x0.toFixed(1)}" y="${padT}" width="${Math.max(2, x1 - x0).toFixed(1)}" height="${plotH}" fill="${fill}" opacity="${band.kind === 'bright' ? '.18' : '.10'}"/>`;
  }).join('');
  const wallX = wallFrac != null ? xAt(wallFrac) : null;
  const peakX = peakFrac != null ? xAt(peakFrac) : null;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#020617;border:1px solid rgba(255,255,255,.14);border-radius:8px">
    ${bandRects}
    <polygon points="${area}" fill="#e2e8f0" opacity=".10"/>
    <polyline points="${points.join(' ')}" fill="none" stroke="#f8fafc" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + plotH}" stroke="#22d3ee" stroke-width="2"/>
    <line x1="${padL + plotW}" y1="${padT}" x2="${padL + plotW}" y2="${padT + plotH}" stroke="#fde68a" stroke-width="2"/>
    ${wallX != null ? `<line x1="${wallX.toFixed(1)}" y1="${padT}" x2="${wallX.toFixed(1)}" y2="${padT + plotH}" stroke="#fb923c" stroke-width="1.5" stroke-dasharray="3 2"/>` : ''}
    ${peakX != null ? `<line x1="${peakX.toFixed(1)}" y1="${padT}" x2="${peakX.toFixed(1)}" y2="${padT + plotH}" stroke="#facc15" stroke-width="2"/>` : ''}
    <text x="${padL}" y="12" fill="#67e8f9" font-size="9">${zh ? '灶' : 'Lesion'}</text>
    <text x="${padL + plotW}" y="12" fill="#fde68a" font-size="9" text-anchor="end">${zh ? '浆膜' : 'Serosa'}</text>
    ${WALL_LAYER_GUIDES.map((guide) => {
      const mid = xAt((guide.frac0 + guide.frac1) / 2);
      return `<text x="${mid.toFixed(1)}" y="${(padT + plotH + 11).toFixed(1)}" text-anchor="middle" fill="${guide.color}" font-size="8">${zh ? guide.shortZh : guide.shortEn}</text>`;
    }).join('')}
  </svg>`;
}

function buildLocalChannelSvg(
  geom: LayerGeometry,
  centerIdx: number,
  edgeFracs: number[],
  analysis: LayerEchoAnalysis | null,
  frameDataUrl?: string | null,
  frameWidth?: number,
  frameHeight?: number,
  zh = true,
  overlayBandCols?: string[],
): string {
  if (typeof window === 'undefined') return '';
  const wall = geom.wall_pts || [];
  const lesionFace = geom.wall_lesion_pts || [];
  if (wall.length < 3 || lesionFace.length < 3) return '';
  const center = Math.max(0, Math.min(wall.length - 1, centerIdx));
  const half = 16;
  const indices = window.ContactGeom?.localArcIndices?.(wall.length, center, half)
    || Array.from({ length: Math.min(wall.length, half * 2 + 1) }, (_, index) => (
      (center - half + index + wall.length * 2) % wall.length
    ));
  const lesionArc = indices
    .map((index) => lesionFace[index])
    .filter((point): point is number[] => Array.isArray(point) && point.length >= 2);
  const denseLesion = window.ContactGeom?.resamplePoly?.(lesionArc, Math.max(180, Math.min(720, lesionArc.length * 12)), false)
    || lesionArc;
  const points = denseLesion;
  if (points.length < 4) return '';
  const minX = Math.min(...points.map((point) => point[0])) - 10;
  const maxX = Math.max(...points.map((point) => point[0])) + 10;
  const minY = Math.min(...points.map((point) => point[1])) - 10;
  const maxY = Math.max(...points.map((point) => point[1])) + 10;
  const width = Math.max(20, maxX - minX);
  const height = Math.max(20, maxY - minY);
  const polyline = (items: number[][]) => items
    .map((point) => `${svgNumber(point[0])},${svgNumber(point[1])}`)
    .join(' ');
  const pixelOverlay = Boolean(analysis?.pixelBands?.length);
  const hugFracs = edgeFracs.length ? edgeFracs : [0.22, 0.5, 0.82];
  const layerCurves = window.ContactGeom?.channelLayerCurvesSvg?.(
    geom,
    center,
    hugFracs,
    {
      half: 16,
      minDot: 0.3,
      maxSpanPx: 80,
      denseN: 480,
      bandOpacity: 0.2,
      showBands: true,
      showLines: true,
      dashed: Boolean(analysis?.imaginary),
      imaginary: Boolean(analysis?.imaginary),
      pixelBands: pixelOverlay,
      pxStroke: 0.55,
      bandCols: overlayBandCols,
      lineCols: overlayBandCols,
    },
  ) || window.ContactGeom?.wallLayerArcsSvg?.(
    geom,
    center,
    16,
    hugFracs,
    { showBands: true, bandOpacity: 0.2, pxStroke: 0.55 },
  ) || '';
  const wallPoint = wall[center];
  const lesionPoint = lesionFace[center];
  const remain = Number(geom.wall_dists?.[center] || 0);
  const strip = window.ContactGeom?.channelStripOverlaySvg?.(
    wallPoint,
    lesionPoint,
    hugFracs,
    Math.max(2.5, Math.min(7.2, remain || 5)),
    {
      halfWidth: 2.4,
      bandOpacity: 0.28,
      showBands: true,
      showLines: true,
      dashed: Boolean(analysis?.imaginary),
      imaginary: Boolean(analysis?.imaginary),
      pxStroke: 0.55,
      pixelBands: pixelOverlay,
      bandCols: overlayBandCols,
      lineCols: overlayBandCols,
    },
  ) || '';
  const wallNearby = indices
    .map((index) => wall[index])
    .filter((point): point is number[] => {
      if (!Array.isArray(point) || point.length < 2) return false;
      const hit = window.ContactGeom?.closestPointOnPoly?.(point, lesionArc, false);
      return !hit || hit.dist <= 14;
    });
  const wallLine = polyline(wallNearby);
  const lesionLine = polyline(denseLesion);
  const sourceInfo = analysis && window.ContactGeom?.layerSourceInfo?.(analysis);
  const sourceBadge = sourceInfo?.badge || '';
  const sourceText = sourceBadge || (analysis?.pixelBands?.length
    ? (zh ? '像素亮暗' : 'Pixel bands')
    : analysis?.imaginary
      ? (zh ? '几何参考' : 'Geometry')
      : (zh ? '回声层界' : 'Echo edges'));
  const centerWall = wall[center];
  const centerLesion = lesionFace[center];
  const imageLayer = frameDataUrl && frameWidth && frameHeight
    ? `<image href="${frameDataUrl}" x="0" y="0" width="${svgNumber(frameWidth)}" height="${svgNumber(frameHeight)}" preserveAspectRatio="none" opacity=".78"/>`
    : '';
  return `<svg viewBox="${svgNumber(minX)} ${svgNumber(minY)} ${svgNumber(width)} ${svgNumber(height)}" width="100%" height="180" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#020617;border:1px solid rgba(255,255,255,.12);border-radius:8px">
    ${imageLayer}
    <rect x="${svgNumber(minX)}" y="${svgNumber(minY)}" width="${svgNumber(width)}" height="${svgNumber(height)}" fill="#020617" opacity="${imageLayer ? '0.16' : '1'}"/>
    ${wallLine ? `<polyline points="${wallLine}" fill="none" stroke="#fb923c" stroke-width="0.9" stroke-linecap="round" stroke-linejoin="round" opacity=".75"/>` : ''}
    <polyline points="${lesionLine}" fill="none" stroke="#22d3ee" stroke-width="0.85" stroke-linecap="round" stroke-linejoin="round"/>
    ${layerCurves}
    ${strip}
    <line x1="${svgNumber(centerWall[0])}" y1="${svgNumber(centerWall[1])}" x2="${svgNumber(centerLesion[0])}" y2="${svgNumber(centerLesion[1])}" stroke="#f8fafc" stroke-width="1.2" stroke-dasharray="4 3" opacity=".85"/>
    <circle cx="${svgNumber(centerWall[0])}" cy="${svgNumber(centerWall[1])}" r="3.2" fill="#fb923c" stroke="#fff" stroke-width="1"/>
    <circle cx="${svgNumber(centerLesion[0])}" cy="${svgNumber(centerLesion[1])}" r="3.2" fill="#22d3ee" stroke="#fff" stroke-width="1"/>
    <text x="${svgNumber(minX + 5)}" y="${svgNumber(minY + 11)}" fill="#94a3b8" font-size="9">${sourceText}</text>
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
  const [offset, setOffset] = useState(wallOffsetPx ?? 0);
  const [selectedLayer, setSelectedLayer] = useState<WallLayerCode>('L5');
  const [corridorZoom, setCorridorZoom] = useState<string>('');
  const [layerZooms, setLayerZooms] = useState<Partial<Record<WallLayerCode, string>>>({});

  useEffect(() => {
    if (Number.isFinite(wallOffsetPx)) setOffset(wallOffsetPx as number);
  }, [wallOffsetPx]);

  const canRun = lesionPolygon.length >= 3 && !!frameSize?.width && !!frameSize?.height && !!frameDataUrl;
  const orientationReady = wallPolygon.length >= 3
    || (Array.isArray(lumenPrefer)
      && Number.isFinite(lumenPrefer[0])
      && Number.isFinite(lumenPrefer[1]));
  const autoReady = canRun && orientationReady;

  const run = useCallback(async (force = false) => {
    if (!frameSize || lesionPolygon.length < 3) {
      setError(zh ? '先框出病灶' : 'Draw the lesion first');
      return;
    }
    if (!frameDataUrl) {
      setError(zh ? '请先暂停画面' : 'Pause the frame first');
      return;
    }
    if (!orientationReady && !force) {
      setError(zh ? '再画出胃腔，用来对准胃壁方向' : 'Draw the lumen to orient the wall');
      setResult(null);
      onResult?.(null);
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
        frameDataUrl,
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
      if (!analyzed.ok) {
        setError(analyzed.message || (zh ? '这一帧看不清层界' : 'Layer edges are unclear on this frame'));
      } else if (!orientationReady) {
        setError(zh ? '没有胃腔方向，请补画后重算' : 'Add the lumen, then re-run');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'analyze failed';
      setError(msg);
      setResult(null);
      onResult?.(null);
    } finally {
      setBusy(false);
    }
  }, [frameSize, lesionPolygon, wallPolygon, frameDataUrl, offset, pick, lumenPrefer, orientationReady, onResult, zh]);

  // Auto-run only when lesion + freeze + lumen/wall orientation are ready; skip while dragging.
  useEffect(() => {
    if (!autoReady || paused) return;
    const t = window.setTimeout(() => {
      void run(false);
    }, 320);
    return () => window.clearTimeout(t);
  }, [autoReady, paused, lesionPolygon, wallPolygon, frameDataUrl, offset, pick?.x, pick?.y, lumenPrefer?.[0], lumenPrefer?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps

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
    const overlay = analysis?.pixelBands?.length && window.ContactGeom?.pixelBandOverlay
      ? window.ContactGeom.pixelBandOverlay(analysis.pixelBands, analysis.outwardWallFrac)
      : null;
    const edgeFracs = overlay?.edges?.length
      ? overlay.edges
      : (result.pixelBased && !analysis?.imaginary
        ? (analysis?.pixelEdges || analysis?.edgeFracs || [])
        : [0.22, 0.5, 0.82]);
    const overlayBandCols = overlay?.bandCols || analysis?.overlayBandCols || [];
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
      zh,
      overlayBandCols,
    );
    const echoValues = (analysis?.outwardValues && analysis.outwardValues.length
      ? analysis.outwardValues
      : analysis?.values) || [];
    const profileSvg = buildEchoProfileSvg(
      echoValues.map((value) => Number(value)).filter((value) => Number.isFinite(value)),
      analysis?.pixelBands || [],
      Number.isFinite(analysis?.outwardWallFrac) ? Number(analysis?.outwardWallFrac) : null,
      analysis?.serosa && Number.isFinite(Number((analysis.serosa as { peak?: { frac?: number } }).peak?.frac))
        ? Number((analysis.serosa as { peak?: { frac?: number } }).peak?.frac)
        : null,
      zh,
    );
    let remainSvg = '';
    try {
      remainSvg = window.ContactGeom?.remainProfileSvg
        ? window.ContactGeom.remainProfileSvg(result.geom, center, 18, 280, 64) || ''
        : '';
    } catch {
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

  const nextStep = !canRun
    ? (zh ? '先框出病灶，并暂停画面' : 'Draw the lesion and pause the frame')
    : !orientationReady
      ? (zh ? '再画出胃腔，用来对准胃壁方向' : 'Draw the lumen to orient the wall')
      : null;
  const serosa = result?.serosa || result?.analysis?.serosa || null;
  const layerLabel = result?.ok
    ? (result.layer?.label || '').replace(/[()（）]/g, '').trim()
    : '';
  const serosaLine = !result?.inContact
    ? (zh ? '未贴壁' : 'Not against the wall')
    : serosa?.status === 'not_reached'
      ? (zh ? '未贴到' : 'Not reached')
      : serosa?.status === 'continuous'
        ? (zh ? '亮线还在' : 'Line intact')
        : serosa?.status === 'interrupted'
          ? (zh ? '亮线中断' : 'Line broken')
          : (zh ? '看不清' : 'Unclear');

  const headline = layerLabel || serosaLine;
  const showLineChip = Boolean(result?.ok && serosaLine && serosaLine !== headline);
  const remainText = fineVisuals.remain != null ? `${fineVisuals.remain.toFixed(1)} px` : null;
  const pixelBands: LayerEchoBand[] = result?.analysis?.pixelBands || [];
  const layerRows = WALL_LAYER_GUIDES.map((guide) => {
    const hit = pixelBands.find((band) => {
      const mid = ((Number(band.f0) || 0) + (Number(band.f1) || 1)) / 2;
      return mid >= guide.frac0 && mid < guide.frac1;
    }) || null;
    const cropFrac = hit
      ? ((Number(hit.f0) || 0) + (Number(hit.f1) || 1)) / 2
      : (guide.frac0 + guide.frac1) / 2;
    return { guide, band: hit, cropFrac };
  });

  useEffect(() => {
    let cancelled = false;
    const geom = result?.ok ? result.geom : null;
    const center = fineVisuals.center;
    const wall = geom?.wall_pts || [];
    const lesionFace = geom?.wall_lesion_pts || [];
    if (!frameDataUrl || center == null || !wall[center] || !lesionFace[center]) {
      setCorridorZoom('');
      setLayerZooms({});
      return undefined;
    }
    const remain = Math.max(12, fineVisuals.remain || 24);
    void loadFrameImage(frameDataUrl).then((image) => {
      if (cancelled) return;
      const lesion = lesionFace[center];
      const wallPt = wall[center];
      setCorridorZoom(cropChannelOverview(image, lesion, wallPt, Math.max(28, remain * 0.55), 420, 200));
      const next: Partial<Record<WallLayerCode, string>> = {};
      layerRows.forEach((row) => {
        const point = lerpPoint(lesion, wallPt, row.cropFrac);
        const src = Math.max(36, Math.min(140, remain * 0.85));
        next[row.guide.code] = cropSquareZoom(image, point[0], point[1], src, 168, row.guide.color);
      });
      setLayerZooms(next);
    }).catch(() => {
      if (!cancelled) {
        setCorridorZoom('');
        setLayerZooms({});
      }
    });
    return () => {
      cancelled = true;
    };
  }, [frameDataUrl, result?.ok, result?.geom, fineVisuals.center, fineVisuals.remain, pixelBands.length]);

  const serosaDetail = (() => {
    const status = serosa?.status;
    if (!result?.inContact) {
      return zh
        ? '病灶前缘还没贴到外缘。先不要谈浆膜亮线断不断。'
        : 'The front is not against the outer edge yet. Do not score serosal continuity.';
    }
    if (status === 'not_reached') {
      return zh
        ? '已经贴壁，但低回声还没贴到最外亮线。更像浆膜还在外侧。'
        : 'Against the wall, but the hypoechoic front has not reached the outer bright line.';
    }
    if (status === 'continuous') {
      return zh
        ? '贴到浆膜亮线，这条高回声带在接触弧上还在。邻帧再看一次。'
        : 'The front reached the serosal bright line and that line still reads along the contact arc. Recheck a neighbor frame.';
    }
    if (status === 'interrupted') {
      return zh
        ? '贴到浆膜亮线，接触弧上亮峰弱或断了。单帧更像伪像，请换邻帧。'
        : 'The front reached the line and the bright peak is weak or broken on this arc. A single frame is often artifact; check a neighbor.';
    }
    return zh
      ? '贴到外缘，但亮线本帧看不清。看不清不等于中断。'
      : 'Against the outer edge, but the bright line is unseen on this frame. Unseen is not interruption.';
  })();

  return (
    <div className="space-y-3 text-[12px] text-slate-200">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {result?.ok ? (
            <div
              className="text-[16px] font-semibold leading-snug"
              style={{
                color:
                  (typeof result.layer?.color === 'string' && result.layer.color) ||
                  result.layer?.tone ||
                  '#e2e8f0',
              }}
            >
              {headline}
            </div>
          ) : nextStep ? (
            <div className="text-[12px] leading-relaxed text-slate-400">{nextStep}</div>
          ) : error ? (
            <div className="text-[12px] text-rose-100">{error}</div>
          ) : (
            <div className="text-[12px] text-slate-500">{zh ? '框灶并暂停后自动出图' : 'Box the lesion and pause'}</div>
          )}
          {result?.ok ? (
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-400">
              <span>{result.inContact ? (zh ? '贴壁' : 'Against wall') : (zh ? '未贴' : 'Free')}</span>
              {remainText ? <span className="font-mono text-slate-200">{remainText}</span> : null}
              {showLineChip ? <span>{serosaLine}</span> : null}
              {fineVisuals.source ? <span>{fineVisuals.source}</span> : null}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          disabled={!canRun || busy}
          onClick={() => void run(true)}
          className="inline-flex shrink-0 items-center gap-1 rounded border border-white/15 px-2 py-1 text-[11px] text-slate-200 hover:bg-white/5 disabled:opacity-40"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {zh ? '重算' : 'Re-run'}
        </button>
      </div>

      {result?.ok ? (
        <p className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[11px] leading-relaxed text-slate-400">
          {zh
            ? '下面按黏膜到浆膜逐层放大。这是本帧回声草稿，不是病理五层，也不解锁确定 cT。'
            : 'Each band below is a magnified echo draft from mucosa to serosa. Not a pathologic five-layer map, and it does not unlock a definite cT.'}
        </p>
      ) : null}

      {error && result?.ok ? (
        <div className="text-[11px] text-rose-200">{error}</div>
      ) : null}

      {result?.ok ? (
        <div className="space-y-3">
          <section className="space-y-1.5">
            <div className="text-[11px] font-semibold text-slate-100">
              {zh ? '走廊放大' : 'Corridor zoom'}
            </div>
            {corridorZoom ? (
              <img
                src={corridorZoom}
                alt={zh ? '病灶到浆膜走廊放大' : 'Lesion-to-serosa corridor zoom'}
                className="w-full rounded-md border border-white/10 bg-slate-950"
              />
            ) : null}
            {fineVisuals.channelSvg ? (
              <div
                className="overflow-hidden rounded-md"
                dangerouslySetInnerHTML={{ __html: fineVisuals.channelSvg }}
              />
            ) : null}
            <p className="text-[10px] leading-relaxed text-slate-500">
              {zh
                ? '青点是灶前缘，橙点是几何外缘。中间走廊才是分层采样区。'
                : 'Cyan is the lesion front, orange is the geometric outer edge. Layers are sampled in the corridor between them.'}
            </p>
          </section>

          {fineVisuals.profileSvg ? (
            <section className="space-y-1">
              <div className="text-[11px] font-semibold text-slate-100">
                {zh ? '回声剖面，灶到浆膜' : 'Echo profile, lesion to serosa'}
              </div>
              <div
                className="overflow-hidden rounded-md"
                dangerouslySetInnerHTML={{ __html: fineVisuals.profileSvg }}
              />
              <p className="text-[10px] leading-relaxed text-slate-500">
                {zh
                  ? '黄实线是浆膜亮峰。橙虚线是几何外缘。亮带偏黄，暗带偏蓝。假想分层表示本帧像素不够，只是等分参考。'
                  : 'Solid gold is the serosal bright peak. Dashed orange is the geometric outer edge. Bright bands are gold, dark bands are blue. Imaginary layers mean this frame was split evenly because pixels were unclear.'}
              </p>
            </section>
          ) : null}

          {!fineVisuals.profileSvg && fineVisuals.remainSvg ? (
            <div
              className="overflow-hidden rounded-md"
              dangerouslySetInnerHTML={{ __html: fineVisuals.remainSvg }}
            />
          ) : null}

          <section className="space-y-2">
            <div>
              <div className="text-[11px] font-semibold text-slate-100">
                {zh ? '逐层放大与医学说明' : 'Per-layer zoom and medical reading'}
              </div>
              <p className="mt-0.5 text-[10px] text-slate-500">
                {zh ? '点一层看放大图。默认打开浆膜。' : 'Tap a layer for its zoom. Serosa is open by default.'}
              </p>
            </div>
            <div className="flex flex-wrap gap-1">
              {layerRows.map((row) => (
                <button
                  key={row.guide.code}
                  type="button"
                  onClick={() => setSelectedLayer(row.guide.code)}
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${
                    selectedLayer === row.guide.code
                      ? 'border-white/40 bg-white/10 text-white'
                      : 'border-white/10 text-slate-400 hover:bg-white/5'
                  }`}
                  style={{ color: selectedLayer === row.guide.code ? row.guide.color : undefined }}
                >
                  {zh ? row.guide.shortZh : row.guide.shortEn}
                </button>
              ))}
            </div>
            {layerRows.map((row) => {
              const open = selectedLayer === row.guide.code;
              const zoom = layerZooms[row.guide.code];
              const kind = row.band?.kind;
              const isSerosa = row.guide.code === 'L5';
              return (
                <article
                  key={row.guide.code}
                  className={`rounded-lg border px-2.5 py-2 ${
                    open ? 'border-white/20 bg-white/[0.04]' : 'border-white/10 bg-transparent'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedLayer(row.guide.code)}
                    className="flex w-full items-center justify-between gap-2 text-left"
                  >
                    <span className="font-semibold" style={{ color: row.guide.color }}>
                      {row.guide.code} {zh ? row.guide.zh : row.guide.en}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {kind === 'bright'
                        ? (zh ? '亮带' : 'Bright')
                        : kind === 'dark'
                          ? (zh ? '暗带' : 'Dark')
                          : (zh ? '本帧未单独分出' : 'Not split on this frame')}
                    </span>
                  </button>
                  {open ? (
                    <div className="mt-2 space-y-2">
                      {zoom ? (
                        <img
                          src={zoom}
                          alt={zh ? `${row.guide.zh}放大` : `${row.guide.en} zoom`}
                          className="w-full rounded-md border border-white/10 bg-slate-950"
                        />
                      ) : (
                        <div className="rounded-md border border-dashed border-white/10 px-2 py-6 text-center text-[10px] text-slate-500">
                          {zh ? '这一层的放大图还在生成' : 'Layer zoom is still building'}
                        </div>
                      )}
                      <p className="text-[11px] leading-relaxed text-slate-300">
                        {zh ? row.guide.echoZh : row.guide.echoEn}
                      </p>
                      <p className="text-[11px] leading-relaxed text-slate-400">
                        {zh ? row.guide.lookZh : row.guide.lookEn}
                      </p>
                      <p className="text-[11px] leading-relaxed text-slate-500">
                        {zh ? row.guide.stagingZh : row.guide.stagingEn}
                      </p>
                      {isSerosa ? (
                        <div className="rounded-md border border-rose-300/20 bg-rose-400/[0.06] px-2 py-1.5 text-[11px] leading-relaxed text-rose-50/90">
                          <div className="font-semibold text-rose-100">
                            {zh ? `浆膜本帧：${serosaLine}` : `Serosa this frame: ${serosaLine}`}
                          </div>
                          <p className="mt-1">{serosaDetail}</p>
                          {serosa?.continuityFrac != null ? (
                            <p className="mt-1 font-mono text-[10px] text-rose-100/80">
                              {zh
                                ? `接触弧亮线保留 ${Math.round(Number(serosa.continuityFrac) * 100)}%`
                                : `Bright-line kept on ${Math.round(Number(serosa.continuityFrac) * 100)}% of the contact arc`}
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-slate-500">
                      {zh ? row.guide.echoZh : row.guide.echoEn}
                    </p>
                  )}
                </article>
              );
            })}
          </section>

          <section className="space-y-1.5 border-t border-white/10 pt-2">
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span>{zh ? '外推' : 'Offset'}</span>
              <button
                type="button"
                className="rounded border border-white/15 px-2 py-0.5 text-slate-200"
                onClick={() => setOffset((v) => Math.max(8, (v || Math.round(result.offsetPx || 24)) - 8))}
              >
                −
              </button>
              <span className="font-mono text-slate-200">{Math.round(offset || result.offsetPx || 0)} px</span>
              <button
                type="button"
                className="rounded border border-white/15 px-2 py-0.5 text-slate-200"
                onClick={() => setOffset((v) => (v || Math.round(result.offsetPx || 24)) + 8)}
              >
                +
              </button>
            </div>
            <p className="text-[10px] leading-relaxed text-slate-500">
              {zh
                ? '外推只改几何参考外缘，不改 Assist 数字。假想分层时用它把参考壁挪近或挪远。'
                : 'Offset only moves the geometric outer edge. It does not change Assist numbers. Use it when layers are imaginary.'}
            </p>
          </section>
        </div>
      ) : null}
    </div>
  );
}
