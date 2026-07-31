'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Check, Eraser, Loader2, MousePointer2, Pause, Pencil, Play, Plus, Save, Sparkles, Trash2, Video, X, ZoomIn,
} from 'lucide-react';
import type { MaskBoundaryOverride, Patient, VideoInfo } from '@/types';
import { bboxFromPolygon } from '@/lib/mask-override';
import { parseLesionMaskFromLabelMe, parseWallMaskFromLabelMe } from '@/lib/direction-annotation/labelme-utils';
import { useSettings } from '@/contexts/SettingsContext';
import { WallFeatureAnalysisCard } from '@/components/WallFeatureAnalysisCard';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import {
  LESION_CTRL_COUNT,
  LESION_SOFT_SIGMA,
  WALL_CTRL_COUNT,
  WALL_SOFT_SIGMA,
  clonePoly,
  controlIndices,
  prepareEditableContour,
  softDeform,
  strokeSmoothClosed,
} from '@/lib/human-assist/contour-edit';

type EditMode = 'soft' | 'hard' | 'add' | 'delete' | 'sam';
type MediaMode = 'image' | 'video';
type ContourLayer = 'lesion' | 'wall';
type DragLayer = ContourLayer;
interface InteractiveSegPanelProps {
  patient: Patient | null;
  override: MaskBoundaryOverride | null;
  onOverrideChange: (next: MaskBoundaryOverride | null) => void;
  /** Optional: wall-layer + GC-US assist payload for DiagnosisPanel */
  onImagingAssist?: (payload: ImagingAssistPayload | null) => void;
}

export type ImagingAssistPayload = {
  layerResult: LayerAnalyzeResult | null;
  lesionPolygon: number[][];
  wallPolygon: number[][];
  frameSize: { width: number; height: number } | null;
};

function dist2(a: number[], b: number[]) {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

function nearestVertex(points: number[][], imgPt: number[], thresholdPx: number): number {
  let best = -1;
  let bestD = thresholdPx * thresholdPx;
  for (let i = 0; i < points.length; i += 1) {
    const d = dist2(points[i], imgPt);
    if (d <= bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

function nearestEdgeInsert(points: number[][], imgPt: number[], thresholdPx: number): number {
  if (points.length < 2) return -1;
  let bestEdge = -1;
  let bestD = thresholdPx * thresholdPx;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    const apx = imgPt[0] - a[0];
    const apy = imgPt[1] - a[1];
    const ab2 = abx * abx + aby * aby || 1;
    const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / ab2));
    const cx = a[0] + t * abx;
    const cy = a[1] + t * aby;
    const d = dist2([cx, cy], imgPt);
    if (d <= bestD) {
      bestD = d;
      bestEdge = i;
    }
  }
  return bestEdge;
}

async function videoOrImageToSamFrame(
  video: HTMLVideoElement | null,
  img: HTMLImageElement | null,
  preferVideo: boolean,
  maxSide = 1024,
): Promise<{ b64: string; width: number; height: number; fullWidth: number; fullHeight: number; scale: number }> {
  let fullW = 0;
  let fullH = 0;
  const draw = (ctx: CanvasRenderingContext2D, dw: number, dh: number) => {
    if (preferVideo && video && video.videoWidth > 0) {
      ctx.drawImage(video, 0, 0, dw, dh);
      return;
    }
    if (!img) throw new Error('no frame');
    ctx.drawImage(img, 0, 0, dw, dh);
  };
  if (preferVideo && video && video.videoWidth > 0) {
    fullW = video.videoWidth;
    fullH = video.videoHeight;
  } else if (img) {
    fullW = img.naturalWidth || img.width;
    fullH = img.naturalHeight || img.height;
  } else {
    throw new Error('no frame');
  }
  const scale = Math.min(1, maxSide / Math.max(fullW, fullH));
  const width = Math.max(1, Math.round(fullW * scale));
  const height = Math.max(1, Math.round(fullH * scale));
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('canvas unavailable');
  draw(ctx, width, height);
  const b64 = c.toDataURL('image/jpeg', 0.85).replace(/^data:image\/jpeg;base64,/, '');
  return { b64, width, height, fullWidth: fullW, fullHeight: fullH, scale };
}

function polygonCentroid(points: number[][]): number[] | null {
  if (!points.length) return null;
  let sx = 0;
  let sy = 0;
  for (const p of points) {
    sx += p[0];
    sy += p[1];
  }
  return [sx / points.length, sy / points.length];
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function InteractiveSegPanel({ patient, override, onOverrideChange, onImagingAssist }: InteractiveSegPanelProps) {
  const { language } = useSettings();
  const zh = language === 'zh';
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<EditMode>('soft');
  const [mediaMode, setMediaMode] = useState<MediaMode>('image');
  const [activeLayer, setActiveLayer] = useState<ContourLayer>('lesion');
  const [points, setPoints] = useState<number[][]>([]);
  const [wallPoints, setWallPoints] = useState<number[][]>([]);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragLayer, setDragLayer] = useState<DragLayer | null>(null);
  const [saving, setSaving] = useState(false);
  const [samBusy, setSamBusy] = useState(false);
  const [samClicks, setSamClicks] = useState<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const [samBoxPreview, setSamBoxPreview] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [samAvailable, setSamAvailable] = useState<boolean | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [roiMode, setRoiMode] = useState<'predicted' | 'doctor' | 'auto'>('predicted');
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [trackOnPlay, setTrackOnPlay] = useState(true);
  const [keyCandidates, setKeyCandidates] = useState<Array<{
    timestamp_sec: number;
    score: number;
    reasons?: string[];
    thumb_url?: string;
  }>>([]);
  const [keyBusy, setKeyBusy] = useState(false);
  const [pendingOpenVideoSam, setPendingOpenVideoSam] = useState(false);
  /** Freeze display frame while editing vertices / after SAM — prevents click refresh flicker. */
  const [frameFrozen, setFrameFrozen] = useState(false);
  const [propagateBusy, setPropagateBusy] = useState(false);
  const [propagateProgress, setPropagateProgress] = useState<string | null>(null);
  const [frameDataUrl, setFrameDataUrl] = useState<string | null>(null);
  const [layerResult, setLayerResult] = useState<LayerAnalyzeResult | null>(null);
  const [layerPick, setLayerPick] = useState<{ x: number; y: number } | null>(null);
  const [undoLen, setUndoLen] = useState(0);
  const [hasOriginal, setHasOriginal] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trackBusyRef = useRef(false);
  const lastTrackAtRef = useRef(0);
  const pointsRef = useRef<number[][]>([]);
  const wallPointsRef = useRef<number[][]>([]);
  const dragIndexRef = useRef<number | null>(null);
  const dragLayerRef = useRef<DragLayer | null>(null);
  const dragSoftRef = useRef(true);
  const frameFrozenRef = useRef(false);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const undoStackRef = useRef<Array<{ lesion: number[][]; wall: number[][] }>>([]);
  const originalRef = useRef<{ lesion: number[][]; wall: number[][] } | null>(null);
  const samAbortRef = useRef<AbortController | null>(null);
  const samGenRef = useRef(0);
  const draggingRef = useRef(false);
  const samBusyRef = useRef(false);
  const samClicksRef = useRef<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const samBoxDragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  useEffect(() => {
    pointsRef.current = points;
  }, [points]);
  useEffect(() => {
    wallPointsRef.current = wallPoints;
  }, [wallPoints]);
  useEffect(() => {
    dragIndexRef.current = dragIndex;
  }, [dragIndex]);
  useEffect(() => {
    dragLayerRef.current = dragLayer;
  }, [dragLayer]);
  useEffect(() => {
    frameFrozenRef.current = frameFrozen;
  }, [frameFrozen]);

  const snapshotOriginal = useCallback((lesion: number[][], wall: number[][]) => {
    originalRef.current = { lesion: clonePoly(lesion), wall: clonePoly(wall) };
    undoStackRef.current = [];
    setUndoLen(0);
    setHasOriginal(true);
  }, []);

  const pushEditUndo = useCallback(() => {
    undoStackRef.current.push({
      lesion: clonePoly(pointsRef.current),
      wall: clonePoly(wallPointsRef.current),
    });
    if (undoStackRef.current.length > 40) undoStackRef.current.shift();
    setUndoLen(undoStackRef.current.length);
  }, []);

  const undoEdit = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    pointsRef.current = prev.lesion;
    wallPointsRef.current = prev.wall;
    setPoints(prev.lesion);
    setWallPoints(prev.wall);
    setUndoLen(undoStackRef.current.length);
    setMessage(zh ? '已撤销上一步轮廓编辑' : 'Undid last contour edit');
  }, [zh]);

  const restoreOriginal = useCallback(() => {
    const orig = originalRef.current;
    if (!orig) return;
    pushEditUndo();
    pointsRef.current = clonePoly(orig.lesion);
    wallPointsRef.current = clonePoly(orig.wall);
    setPoints(clonePoly(orig.lesion));
    setWallPoints(clonePoly(orig.wall));
    setMessage(zh ? '已恢复分割原始轮廓' : 'Restored original SAM/LabelMe contour');
  }, [pushEditUndo, zh]);

  const activePoints = activeLayer === 'wall' ? wallPoints : points;
  const setActivePoints = activeLayer === 'wall' ? setWallPoints : setPoints;

  useEffect(() => {
    if (!patient) {
      setPoints([]);
      setWallPoints([]);
      setImgLoaded(false);
      return;
    }
    setRoiMode(override?.roi_mode || 'predicted');
    if (override?.mask_polygon?.length || override?.wall_polygon?.length) {
      const lesion = override?.mask_polygon?.length
        ? prepareEditableContour(
          override.mask_polygon.map((p) => [Number(p[0]), Number(p[1])]),
          120,
        )
        : [];
      const wall = override?.wall_polygon?.length
        ? prepareEditableContour(
          override.wall_polygon.map((p) => [Number(p[0]), Number(p[1])]),
          96,
        )
        : [];
      setPoints(lesion);
      setWallPoints(wall);
      snapshotOriginal(lesion, wall);
      return;
    }
    setPoints([]);
    setWallPoints([]);
    const annotationUrl = patient.segmentation?.annotation_url || patient.json_url;
    if (!annotationUrl) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(annotationUrl);
        if (!res.ok) return;
        const data = await res.json();
        const lesionRaw = parseLesionMaskFromLabelMe(data);
        const wallRaw = parseWallMaskFromLabelMe(data);
        const lesion = lesionRaw?.points?.length
          ? prepareEditableContour(lesionRaw.points.map((p) => [Number(p[0]), Number(p[1])]), 120)
          : [];
        const wall = wallRaw?.points?.length
          ? prepareEditableContour(wallRaw.points.map((p) => [Number(p[0]), Number(p[1])]), 96)
          : [];
        if (cancelled) return;
        if (lesion.length) setPoints(lesion);
        if (wall.length) setWallPoints(wall);
        if (lesion.length || wall.length) {
          snapshotOriginal(lesion, wall);
          setMessage(
            zh
              ? `已从 LabelMe 载入稠密轮廓（病灶 ${lesion.length} / 胃壁 ${wall.length}）, 拖控制点软变形`
              : `Loaded LabelMe dense contours (lesion ${lesion.length} / wall ${wall.length})`,
          );
        }
      } catch {
        /* ignore */
      }
    })();
    return () => { cancelled = true; };
  }, [patient?.id, override?.updated_at, override?.mask_polygon, override?.wall_polygon, patient?.json_url, patient?.segmentation?.annotation_url, zh, snapshotOriginal]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/agent/sam-interactive');
        const data = await res.json();
        if (!cancelled) setSamAvailable(Boolean(data.available));
      } catch {
        if (!cancelled) setSamAvailable(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => {
    if (!open || !patient) return;
    let cancelled = false;
    (async () => {
      // Always resolve from disk index (crop_ui / qualified / public) — no upload.
      const fromPatient = patient.video_urls || [];
      let list = fromPatient;
      try {
        const res = await fetch(
          `/api/patients/videos?patientId=${encodeURIComponent(patient.patient_id)}&limit=40`,
        );
        const data = await res.json();
        const remote = (data.videos || []) as VideoInfo[];
        if (remote.length) {
          const seen = new Set(list.map((v) => v.url));
          list = [...list, ...remote.filter((v) => !seen.has(v.url))];
        }
      } catch {
        /* keep fromPatient */
      }
      if (cancelled) return;
      setVideos(list);
      setVideoUrl((prev) => {
        if (prev && list.some((v) => v.url === prev)) return prev;
        return list[0]?.url || '';
      });
      if (pendingOpenVideoSam && list.length) {
        setPendingOpenVideoSam(false);
        setVideoUrl(list[0].url);
        setMediaMode('video');
        setMode('sam');
        setMessage(
          zh
            ? `已打开对应视频：${list[0].filename}, 点击画面做 SAM`
            : `Opened ${list[0].filename}, click for SAM`,
        );
      } else if (pendingOpenVideoSam && !list.length) {
        setPendingOpenVideoSam(false);
        setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      }
    })();
    return () => { cancelled = true; };
  }, [open, patient?.patient_id, patient?.video_urls, pendingOpenVideoSam, zh]);

  const openPatientVideoSam = useCallback(() => {
    if (!videos.length) {
      setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      return;
    }
    const url = videoUrl || videos[0].url;
    setVideoUrl(url);
    setMediaMode('video');
    setMode('sam');
    setMessage(
      zh
        ? `已打开对应视频：${videos.find((v) => v.url === url)?.filename || 'video'}, 点击画面做 SAM`
        : `Opened patient video, click canvas for SAM`,
    );
  }, [videos, videoUrl, zh]);

  const captureFrameDataUrl = useCallback(() => {
    const video = videoRef.current;
    if (mediaMode === 'video' && video && video.videoWidth) {
      const c = document.createElement('canvas');
      c.width = video.videoWidth;
      c.height = video.videoHeight;
      const ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(video, 0, 0);
      const url = c.toDataURL('image/jpeg', 0.92);
      setFrameDataUrl(url);
      return url;
    }
    const img = imgRef.current;
    if (img?.naturalWidth) {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(img, 0, 0);
      const url = c.toDataURL('image/jpeg', 0.92);
      setFrameDataUrl(url);
      return url;
    }
    return null;
  }, [mediaMode]);

  const frameSize = useMemo(() => {
    const video = videoRef.current;
    if (mediaMode === 'video' && video?.videoWidth) {
      return { width: video.videoWidth, height: video.videoHeight };
    }
    const img = imgRef.current;
    if (img?.naturalWidth) return { width: img.naturalWidth, height: img.naturalHeight };
    return null;
  }, [mediaMode, videoTime, imgLoaded, points.length]);

  const freezeCurrentFrame = useCallback(() => {
    const video = videoRef.current;
    if (video && !video.paused) video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    setTrackOnPlay(false);
    captureFrameDataUrl();
  }, [captureFrameDataUrl]);

  const syncFrameFromVideo = useCallback((opts?: { force?: boolean }) => {
    if (!opts?.force && (frameFrozenRef.current || dragIndexRef.current !== null)) return;
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setVideoTime(video.currentTime || 0);
    setImgLoaded(true);
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (canvas && container) {
      const rect = container.getBoundingClientRect();
      const w = Math.max(320, Math.floor(rect.width));
      const h = Math.max(240, Math.floor(rect.height));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    }
  }, []);

  const runSamAtPoint = useCallback(async (
    imgPt: number[] | null,
    opts?: {
      silent?: boolean;
      source?: MaskBoundaryOverride['source'];
      box?: { x1: number; y1: number; x2: number; y2: number };
      clicks?: Array<{ x: number; y: number; label: 'positive' | 'negative' }>;
      keepEditing?: boolean;
      stayInSam?: boolean;
    },
  ): Promise<number[][] | null> => {
    if (!patient) return null;
    // Supersede in-flight interactive requests instead of dropping clicks.
    if (!opts?.silent) {
      samAbortRef.current?.abort();
      samGenRef.current += 1;
      samBusyRef.current = true;
      setSamBusy(true);
      setMessage(zh ? 'SAM 推理中…' : 'Running SAM…');
    } else {
      samAbortRef.current?.abort();
    }
    const ac = new AbortController();
    samAbortRef.current = ac;
    const myGen = samGenRef.current;
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const payload: Record<string, unknown> = {
        case_id: patient.patient_id,
        frame_png_b64: frame.b64,
        image_width: frame.width,
        image_height: frame.height,
      };
      const promptClicks = opts?.clicks?.length
        ? opts.clicks
        : imgPt
          ? [{ x: imgPt[0], y: imgPt[1], label: 'positive' as const }]
          : [];
      if (opts?.box) {
        payload.box = {
          x1: opts.box.x1 * scale,
          y1: opts.box.y1 * scale,
          x2: opts.box.x2 * scale,
          y2: opts.box.y2 * scale,
        };
      }
      if (promptClicks.length) {
        payload.clicks = promptClicks.map((c) => ({
          x: c.x * scale,
          y: c.y * scale,
          label: c.label,
        }));
        const firstPos = promptClicks.find((c) => c.label !== 'negative') || promptClicks[0];
        payload.click = {
          x: firstPos.x * scale,
          y: firstPos.y * scale,
          label: firstPos.label,
        };
      } else if (!opts?.box) {
        throw new Error('missing click/box');
      }
      const res = await fetch('/api/agent/sam-interactive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ac.signal,
      });
      const data = await res.json();
      if (!data.ok || !data.result?.mask_polygon) {
        throw new Error(data.error || data.result?.message || 'SAM returned no polygon');
      }
      const rawPoly = (data.result.mask_polygon as number[][]).map((p) => [Number(p[0]), Number(p[1])]);
      if (rawPoly.length < 3) {
        throw new Error(
          zh
            ? 'SAM 未检出有效区域（可换点 / Shift+排除 / 框选再试）'
            : 'SAM empty mask — try another click, Shift+neg, or box',
        );
      }
      const maxCoord = Math.max(...rawPoly.flatMap((p) => p));
      const polyFull =
        maxCoord <= 1.5
          ? rawPoly.map((p) => [p[0] * frame.fullWidth, p[1] * frame.fullHeight])
          : rawPoly.map((p) => [p[0] / scale, p[1] / scale]);
      const poly = prepareEditableContour(polyFull, 96);
      const targetLayer = opts?.source === 'video_track' || opts?.source === 'video_propagate'
        ? 'lesion'
        : activeLayer;
      if (targetLayer === 'wall') {
        setWallPoints(poly);
        wallPointsRef.current = poly;
        snapshotOriginal(pointsRef.current, poly);
      } else {
        setPoints(poly);
        pointsRef.current = poly;
        snapshotOriginal(poly, wallPointsRef.current);
      }

      if (opts?.keepEditing !== false && opts?.source !== 'video_track') {
        freezeCurrentFrame();
        if (opts?.stayInSam || opts?.source === 'sam') {
          setMode('sam');
        } else {
          setMode('soft');
        }
      }

      if (!opts?.silent) {
        const nCtrl = controlIndices(poly.length, LESION_CTRL_COUNT).length;
        const nPrompt = promptClicks.length;
        setMessage(
          zh
            ? `SAM 完成: 稠密 ${poly.length} 点 / ${nCtrl} 控制点; 提示 ${nPrompt} 个（Shift=排除, 拖框=区域）`
            : `SAM done: ${poly.length} pts / ${nCtrl} controls; ${nPrompt} prompts`,
        );
      } else {
        setMessage(
          zh
            ? `视频跟随 t=${(videoRef.current?.currentTime || 0).toFixed(2)}s, ${poly.length}pt`
            : `Video track t=${(videoRef.current?.currentTime || 0).toFixed(2)}s, ${poly.length}pt`,
        );
      }
      setSamAvailable(true);
      return poly;
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return null;
      if (!opts?.silent) {
        setSamAvailable(false);
        setMessage(err instanceof Error ? err.message : 'SAM failed');
      }
      return null;
    } finally {
      if (!opts?.silent && samGenRef.current === myGen) {
        samBusyRef.current = false;
        setSamBusy(false);
      }
    }
  }, [patient, zh, activeLayer, mediaMode, freezeCurrentFrame, snapshotOriginal]);

  const maybeTrackWhilePlaying = useCallback(async () => {
    if (!trackOnPlay || mediaMode !== 'video' || !isPlaying) return;
    if (frameFrozenRef.current || dragIndexRef.current !== null) return;
    if (trackBusyRef.current || samAvailable === false) return;
    const now = Date.now();
    if (now - lastTrackAtRef.current < 1200) return;
    const poly = pointsRef.current;
    if (poly.length < 3) return;
    const bbox = bboxFromPolygon(poly);
    const centroid = polygonCentroid(poly);
    if (!bbox || !centroid) return;
    trackBusyRef.current = true;
    lastTrackAtRef.current = now;
    try {
      await runSamAtPoint(centroid, {
        silent: true,
        source: 'video_track',
        box: bbox,
        keepEditing: false,
      });
    } finally {
      trackBusyRef.current = false;
    }
  }, [trackOnPlay, mediaMode, isPlaying, samAvailable, runSamAtPoint]);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !imgLoaded) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo =
      mediaMode === 'video'
      && !!video
      && video.videoWidth > 0
      && video.readyState >= 2;

    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 0);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 0);
    if (!iw || !ih) return;

    const cw = canvas.width;
    const ch = canvas.height;
    const scale = Math.min(cw / iw, ch / ih);
    const dw = iw * scale;
    const dh = ih * scale;
    const dx = (cw - dw) / 2;
    const dy = (ch - dh) / 2;

    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, cw, ch);
    if (useVideo) ctx.drawImage(video!, dx, dy, dw, dh);
    else if (img) ctx.drawImage(img, dx, dy, dw, dh);

    const map = (x: number, y: number) => ({ x: dx + x * scale, y: dy + y * scale });

    const drawPoly = (poly: number[][], fill: string, stroke: string) => {
      if (poly.length < 2) return;
      strokeSmoothClosed(ctx, poly, map);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 2;
      ctx.stroke();
    };

    // Screen-stable handle radius (direction_demo: clamp(7.5/√scale, 3.2…12))
    const hr = Math.max(3.5, Math.min(11, 7.5 / Math.sqrt(Math.max(scale, 0.15))));

    const drawHandles = (
      poly: number[][],
      count: number,
      fill: string,
      layer: DragLayer,
    ) => {
      if (poly.length < 3) return;
      controlIndices(poly.length, count).forEach((i) => {
        const p = poly[i];
        if (!p) return;
        const { x, y } = map(p[0], p[1]);
        const active = dragLayer === layer && dragIndex === i;
        ctx.beginPath();
        ctx.arc(x, y, active ? hr + 2 : hr, 0, Math.PI * 2);
        ctx.fillStyle = active ? '#fbbf24' : fill;
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });
    };

    drawPoly(wallPoints, 'rgba(251, 146, 60, 0.16)', 'rgba(251, 146, 60, 0.95)');
    drawPoly(points, 'rgba(34, 211, 238, 0.18)', 'rgba(34, 211, 238, 0.95)');
    // Dual handles like direction_demo (both editable without layer switch)
    drawHandles(wallPoints, WALL_CTRL_COUNT, '#ea580c', 'wall');
    drawHandles(points, LESION_CTRL_COUNT, '#16a34a', 'lesion');

    // SAM prompt markers
    for (const c of samClicks) {
      const { x, y } = map(c.x, c.y);
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = c.label === 'negative' ? '#f43f5e' : '#22c55e';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    if (samBoxPreview) {
      const a = map(samBoxPreview.x1, samBoxPreview.y1);
      const b = map(samBoxPreview.x2, samBoxPreview.y2);
      ctx.strokeStyle = 'rgba(168, 85, 247, 0.95)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(
        Math.min(a.x, b.x),
        Math.min(a.y, b.y),
        Math.abs(b.x - a.x),
        Math.abs(b.y - a.y),
      );
      ctx.setLineDash([]);
    }

    if (layerResult?.ok && window.LayerBridge?.drawLayerOverlay) {
      try {
        window.LayerBridge.drawLayerOverlay(layerResult, ctx, map, useVideo ? video : null);
      } catch {
        /* overlay is best-effort */
      }
    }
  }, [points, wallPoints, imgLoaded, dragIndex, dragLayer, mediaMode, videoTime, layerResult, samClicks, samBoxPreview]);

  useEffect(() => {
    redraw();
  }, [redraw]);
  useEffect(() => {
    if (!open || mediaMode !== 'image' || !patient?.image_url) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      setImgLoaded(true);
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (canvas && container) {
        const rect = container.getBoundingClientRect();
        canvas.width = Math.max(320, Math.floor(rect.width));
        canvas.height = Math.max(240, Math.floor(rect.height));
      }
      try {
        const c = document.createElement('canvas');
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext('2d');
        if (ctx) {
          ctx.drawImage(img, 0, 0);
          setFrameDataUrl(c.toDataURL('image/jpeg', 0.92));
        }
      } catch {
        /* CORS / tainted canvas — analysis without echo rays still works */
      }
      redraw();
    };
    img.onerror = () => {
      setMessage(zh ? '图像加载失败' : 'Failed to load image');
      setImgLoaded(false);
    };
    img.src = patient.image_url;
  }, [open, mediaMode, patient?.image_url, patient?.id, zh, redraw]);

  useEffect(() => {
    if (!open || mediaMode !== 'video' || !videoUrl) return;
    const video = videoRef.current;
    if (!video) return;
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    const onMeta = () => {
      setVideoDuration(video.duration || 0);
      syncFrameFromVideo({ force: true });
      redraw();
    };
    const onTime = () => {
      if (frameFrozenRef.current || dragIndexRef.current !== null) {
        // Still update clock when scrubbing while frozen? only if not dragging
        if (dragIndexRef.current === null && video.paused) {
          setVideoTime(video.currentTime || 0);
        }
        return;
      }
      setVideoTime(video.currentTime || 0);
      if (!video.paused) {
        syncFrameFromVideo();
        redraw();
        void maybeTrackWhilePlaying();
      }
    };
    const onPlay = () => {
      setIsPlaying(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
    };
    const onPause = () => {
      setIsPlaying(false);
      syncFrameFromVideo({ force: true });
      redraw();
    };
    video.addEventListener('loadedmetadata', onMeta);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    video.src = videoUrl;
    video.load();
    return () => {
      video.removeEventListener('loadedmetadata', onMeta);
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
    };
  }, [open, mediaMode, videoUrl, syncFrameFromVideo, maybeTrackWhilePlaying, redraw]);

  useEffect(() => {
    if (!open) return;
    const onResize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      const rect = container.getBoundingClientRect();
      canvas.width = Math.max(320, Math.floor(rect.width));
      canvas.height = Math.max(240, Math.floor(rect.height));
      redraw();
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [open, redraw]);

  const canvasToImage = useCallback((e: { clientX: number; clientY: number }): number[] | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 0);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 0);
    if (!iw || !ih) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const cx = (e.clientX - rect.left) * scaleX;
    const cy = (e.clientY - rect.top) * scaleY;
    const scale = Math.min(canvas.width / iw, canvas.height / ih);
    const dw = iw * scale;
    const dh = ih * scale;
    const dx = (canvas.width - dw) / 2;
    const dy = (canvas.height - dh) / 2;
    const ix = (cx - dx) / scale;
    const iy = (cy - dy) / scale;
    if (ix < 0 || iy < 0 || ix > iw || iy > ih) return null;
    return [ix, iy];
  }, [mediaMode]);

  const hitThreshold = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 1);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 1);
    if (!canvas) return 24;
    const rect = canvas.getBoundingClientRect();
    // Map ~14 CSS pixels to image space (easy to grab handles)
    const scale = Math.min(canvas.width / iw, canvas.height / ih) * (rect.width / Math.max(1, canvas.width));
    return Math.max(18, 14 / Math.max(scale, 1e-6));
  }, [mediaMode]);

  const clearSamPrompts = useCallback(() => {
    samClicksRef.current = [];
    setSamClicks([]);
    samBoxDragRef.current = null;
    setSamBoxPreview(null);
  }, []);

  const runSamClick = useCallback(async (
    imgPt: number[],
    label: 'positive' | 'negative' = 'positive',
    box?: { x1: number; y1: number; x2: number; y2: number } | null,
  ) => {
    freezeCurrentFrame();
    let next = samClicksRef.current;
    if (!box) {
      next = [...samClicksRef.current, { x: imgPt[0], y: imgPt[1], label }];
      samClicksRef.current = next;
      setSamClicks(next);
    }
    await runSamAtPoint(imgPt, {
      keepEditing: true,
      stayInSam: true,
      source: 'sam',
      clicks: next.length ? next : undefined,
      box: box || undefined,
    });
  }, [runSamAtPoint, freezeCurrentFrame]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const imgPt = canvasToImage(e);
    if (!imgPt) return;

    // Alt/Option+click：设置浸润通道取样点（会议纪要：接触弧内点选）
    if (e.altKey && points.length >= 3) {
      setLayerPick({ x: imgPt[0], y: imgPt[1] });
      captureFrameDataUrl();
      setMessage(zh ? `已设取样点 (${Math.round(imgPt[0])},${Math.round(imgPt[1])})` : `Pick set (${Math.round(imgPt[0])},${Math.round(imgPt[1])})`);
      return;
    }

    const thr = hitThreshold() * 1.6;
    const lesionCtrls = points.length >= 3 ? controlIndices(points.length, LESION_CTRL_COUNT) : [];
    const wallCtrls = wallPoints.length >= 3 ? controlIndices(wallPoints.length, WALL_CTRL_COUNT) : [];

    const nearestCtrl = (
      poly: number[][],
      idxs: number[],
      thresholdPx: number,
    ): number => {
      let best = -1;
      let bestD = thresholdPx * thresholdPx;
      for (const i of idxs) {
        const p = poly[i];
        if (!p) continue;
        const d = dist2(p, imgPt);
        if (d <= bestD) {
          bestD = d;
          best = i;
        }
      }
      return best;
    };

    // Prefer control handles on BOTH contours (direction_demo dual handles)
    const nearLes = nearestCtrl(points, lesionCtrls, thr);
    const nearWall = nearestCtrl(wallPoints, wallCtrls, thr);
    let pickLayer: DragLayer | null = null;
    let pickIdx = -1;
    if (nearLes >= 0 && nearWall >= 0) {
      const dL = dist2(points[nearLes], imgPt);
      const dW = dist2(wallPoints[nearWall], imgPt);
      if (dW <= dL) {
        pickLayer = 'wall';
        pickIdx = nearWall;
      } else {
        pickLayer = 'lesion';
        pickIdx = nearLes;
      }
    } else if (nearWall >= 0) {
      pickLayer = 'wall';
      pickIdx = nearWall;
    } else if (nearLes >= 0) {
      pickLayer = 'lesion';
      pickIdx = nearLes;
    }

    if (pickLayer && pickIdx >= 0 && (mode === 'soft' || mode === 'hard' || mode === 'sam' || mode === 'add')) {
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      freezeCurrentFrame();
      pushEditUndo();
      setActiveLayer(pickLayer);
      const useSoft = mode !== 'hard';
      if (mode === 'sam' || mode === 'add') setMode('soft');
      dragSoftRef.current = useSoft;
      dragIndexRef.current = pickIdx;
      dragLayerRef.current = pickLayer;
      setDragIndex(pickIdx);
      setDragLayer(pickLayer);
      return;
    }

    const layerPts = activePoints;

    // Hard / add: edge insert on active layer
    if ((mode === 'hard' || mode === 'add') && layerPts.length >= 3) {
      const edge = nearestEdgeInsert(layerPts, imgPt, thr);
      if (edge >= 0) {
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        freezeCurrentFrame();
        pushEditUndo();
        const next = [...layerPts];
        next.splice(edge + 1, 0, imgPt);
        if (activeLayer === 'wall') {
          wallPointsRef.current = next;
          setWallPoints(next);
        } else {
          pointsRef.current = next;
          setPoints(next);
        }
        const newIdx = edge + 1;
        setMode('hard');
        dragSoftRef.current = false;
        dragIndexRef.current = newIdx;
        dragLayerRef.current = activeLayer;
        setDragIndex(newIdx);
        setDragLayer(activeLayer);
        return;
      }
    }

    if (mode === 'sam') {
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      freezeCurrentFrame();
      // Start potential box drag; commit on pointerup (click or box).
      samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
      setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
      (e.currentTarget as HTMLCanvasElement).dataset.samNeg = e.shiftKey ? '1' : '0';
      return;
    }
    if (mode === 'add') {
      freezeCurrentFrame();
      pushEditUndo();
      setActivePoints([...layerPts, imgPt]);
      return;
    }
    if (mode === 'delete') {
      freezeCurrentFrame();
      // Delete nearest control handle on active layer (or any vertex in hard mode)
      const idxs = activeLayer === 'wall' ? wallCtrls : lesionCtrls;
      const idx = nearestCtrl(layerPts, idxs.length ? idxs : layerPts.map((_, i) => i), thr);
      if (idx >= 0 && layerPts.length > 3) {
        pushEditUndo();
        setActivePoints(layerPts.filter((_, i) => i !== idx));
      }
      return;
    }

    // soft mode fallback: grab nearest dense vertex with soft deform
    if (mode === 'soft' && layerPts.length >= 3) {
      const fallback = nearestVertex(layerPts, imgPt, thr * 3);
      if (fallback >= 0) {
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        freezeCurrentFrame();
        pushEditUndo();
        dragSoftRef.current = true;
        dragIndexRef.current = fallback;
        dragLayerRef.current = activeLayer;
        setDragIndex(fallback);
        setDragLayer(activeLayer);
      }
    }
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const boxDrag = samBoxDragRef.current;
    if (boxDrag) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      boxDrag.x1 = imgPt[0];
      boxDrag.y1 = imgPt[1];
      setSamBoxPreview({ x1: boxDrag.x0, y1: boxDrag.y0, x2: boxDrag.x1, y2: boxDrag.y1 });
      redraw();
      return;
    }
    const idx = dragIndexRef.current;
    const layer = dragLayerRef.current;
    if (idx === null || !layer) return;
    e.preventDefault();
    const imgPt = canvasToImage(e);
    if (!imgPt) return;
    const src = layer === 'wall' ? wallPointsRef.current : pointsRef.current;
    if (!src[idx]) return;
    const next = clonePoly(src);
    if (dragSoftRef.current) {
      softDeform(
        next,
        idx,
        imgPt[0],
        imgPt[1],
        layer === 'wall' ? WALL_SOFT_SIGMA : LESION_SOFT_SIGMA,
      );
    } else {
      next[idx] = [imgPt[0], imgPt[1]];
    }
    if (layer === 'wall') {
      wallPointsRef.current = next;
    } else {
      pointsRef.current = next;
    }
    draggingRef.current = true;
    redraw();
  };

  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const boxDrag = samBoxDragRef.current;
    if (boxDrag) {
      samBoxDragRef.current = null;
      setSamBoxPreview(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      const dx = Math.abs(boxDrag.x1 - boxDrag.x0);
      const dy = Math.abs(boxDrag.y1 - boxDrag.y0);
      const neg = e.currentTarget.dataset.samNeg === '1' || e.shiftKey;
      delete e.currentTarget.dataset.samNeg;
      if (dx > 12 || dy > 12) {
        const box = {
          x1: Math.min(boxDrag.x0, boxDrag.x1),
          y1: Math.min(boxDrag.y0, boxDrag.y1),
          x2: Math.max(boxDrag.x0, boxDrag.x1),
          y2: Math.max(boxDrag.y0, boxDrag.y1),
        };
        const cx = (box.x1 + box.x2) / 2;
        const cy = (box.y1 + box.y2) / 2;
        // Box prompt resets click history (cleaner region seed).
        samClicksRef.current = [{ x: cx, y: cy, label: 'positive' }];
        setSamClicks(samClicksRef.current);
        void runSamClick([cx, cy], 'positive', box);
      } else {
        void runSamClick([boxDrag.x0, boxDrag.y0], neg ? 'negative' : 'positive');
      }
      return;
    }
    if (dragIndexRef.current !== null) {
      draggingRef.current = false;
      setPoints(clonePoly(pointsRef.current));
      setWallPoints(clonePoly(wallPointsRef.current));
      setMessage(
        zh
          ? '轮廓已软变形, 可继续拖手柄, 或「撤销 / 恢复原始」'
          : 'Soft-deformed; drag more, or undo / restore',
      );
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
    }
    dragIndexRef.current = null;
    dragLayerRef.current = null;
    setDragIndex(null);
    setDragLayer(null);
  };

  const propagateMaskAcrossVideo = useCallback(async () => {
    if (mediaMode !== 'video' || !videoRef.current || points.length < 3) {
      setMessage(zh ? '请先在视频帧上得到可编辑区域' : 'Need an editable region on a video frame');
      return;
    }
    const video = videoRef.current;
    const start = video.currentTime || 0;
    const duration = video.duration || 0;
    if (!duration || duration <= start + 0.05) {
      setMessage(zh ? '已在视频末尾' : 'Already at end of video');
      return;
    }
    freezeCurrentFrame();
    setPropagateBusy(true);
    setTrackOnPlay(false);
    const step = Math.max(0.2, Math.min(0.5, duration / 40));
    const maxSteps = 12;
    let currentPoly = points.map((p) => [p[0], p[1]]);
    let okSteps = 0;
    try {
      for (let i = 1; i <= maxSteps; i += 1) {
        const t = Math.min(duration - 0.01, start + step * i);
        if (t <= start) break;
        setPropagateProgress(`${i}/${maxSteps}, t=${t.toFixed(2)}s`);
        video.currentTime = t;
        await new Promise<void>((resolve) => {
          const done = () => {
            video.removeEventListener('seeked', done);
            resolve();
          };
          video.addEventListener('seeked', done);
        });
        await sleep(40);
        const bbox = bboxFromPolygon(currentPoly);
        const centroid = polygonCentroid(currentPoly);
        if (!bbox || !centroid) break;
        const prev = currentPoly;
        const nextPoly = await runSamAtPoint(centroid, {
          silent: true,
          source: 'video_propagate',
          box: bbox,
          keepEditing: false,
        });
        if (!nextPoly || nextPoly.length < 3) {
          setPoints(prev);
          break;
        }
        currentPoly = nextPoly;
        setPoints(nextPoly);
        okSteps += 1;
        setVideoTime(t);
        redraw();
      }
      setFrameFrozen(true);
      frameFrozenRef.current = true;
      setMode('soft');
      setMessage(
        zh
          ? `已扩散 ${okSteps} 帧, 可再拖橙/绿手柄软变形后保存`
          : `Propagated ${okSteps} frames; soft-deform handles, then save`,
      );
    } finally {
      setPropagateBusy(false);
      setPropagateProgress(null);
    }
  }, [mediaMode, points, zh, freezeCurrentFrame, runSamAtPoint, redraw]);

  const buildOverride = useCallback((): MaskBoundaryOverride | null => {
    if (!patient || points.length < 3) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const width =
      mediaMode === 'video' && video?.videoWidth
        ? video.videoWidth
        : (img?.naturalWidth || 0);
    const height =
      mediaMode === 'video' && video?.videoHeight
        ? video.videoHeight
        : (img?.naturalHeight || 0);
    if (!width || !height) return null;
    return {
      patientId: patient.patient_id,
      frameId: patient.id,
      imageWidth: width,
      imageHeight: height,
      mask_polygon: points.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
      wall_polygon:
        wallPoints.length >= 3
          ? wallPoints.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10])
          : undefined,
      roi_bbox: bboxFromPolygon(points),
      roi_mode: roiMode,
      source: mode === 'sam' ? 'sam' : 'manual',
      video_time_sec: mediaMode === 'video' ? Number(videoTime.toFixed(3)) : undefined,
      video_url: mediaMode === 'video' ? videoUrl || undefined : undefined,
      updated_at: new Date().toISOString(),
    };
  }, [patient, points, wallPoints, roiMode, mode, mediaMode, videoTime, videoUrl]);

  const handleSave = async () => {
    const next = buildOverride();
    if (!next) {
      setMessage(zh ? '至少需要 3 个顶点' : 'Need at least 3 vertices');
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/patients/mask-overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override: next }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Save failed');
      onOverrideChange(data.override || next);
      setMessage(zh ? '边界已保存，分析将使用此覆盖' : 'Boundary saved — analyze will use this override');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!patient) return;
    setSaving(true);
    try {
      await fetch(
        `/api/patients/mask-overrides?patientId=${encodeURIComponent(patient.patient_id)}&frameId=${encodeURIComponent(patient.id)}`,
        { method: 'DELETE' },
      );
      setPoints([]);
      pointsRef.current = [];
      setWallPoints([]);
      wallPointsRef.current = [];
      clearSamPrompts();
      setLayerResult(null);
      onImagingAssist?.(null);
      onOverrideChange(null);
      setMessage(zh ? '已清除覆盖，将使用模型分割' : 'Override cleared; model seg will be used');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Clear failed');
    } finally {
      setSaving(false);
    }
  };

  const openEditor = useCallback((opts?: { videoSam?: boolean; sam?: boolean }) => {
    if (opts?.videoSam) setPendingOpenVideoSam(true);
    const useSam = Boolean(opts?.videoSam || opts?.sam);
    setMode(useSam ? 'sam' : 'soft');
    samClicksRef.current = [];
    setSamClicks([]);
    setSamBoxPreview(null);
    // Keep dense contours — soft-deform uses sparse control handles (direction_demo)
    setOpen(true);
    setMessage(
      useSam
        ? (zh
          ? 'SAM: 单击前景; Shift+单击排除; 拖框区域分割; 连续点选精修'
          : 'SAM: click include; Shift+click exclude; drag box; multi-click refine')
        : (zh
          ? '拖橙/绿控制点软变形边界（同人机互助 HTML）; 硬拖/加点/删点为辅助'
          : 'Drag orange/green handles to soft-deform (same as HTML demo)'),
    );
  }, [zh]);

  // AssistHub / external open request (additive; floating buttons unchanged)
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ videoSam?: boolean; sam?: boolean }>).detail;
      openEditor(detail || { sam: true });
    };
    window.addEventListener('gastric:open-boundary-edit', handler);
    return () => window.removeEventListener('gastric:open-boundary-edit', handler);
  }, [openEditor]);

  const simplifyActiveLayer = useCallback(() => {
    const src = activeLayer === 'wall' ? wallPoints : points;
    if (src.length < 8) return;
    pushEditUndo();
    const next = prepareEditableContour(src, activeLayer === 'wall' ? 64 : 72);
    if (activeLayer === 'wall') {
      wallPointsRef.current = next;
      setWallPoints(next);
    } else {
      pointsRef.current = next;
      setPoints(next);
    }
    setMode('soft');
    setMessage(
      zh
        ? `已弧长重采样为 ${next.length} 点, 控制手柄 ${controlIndices(next.length, activeLayer === 'wall' ? WALL_CTRL_COUNT : LESION_CTRL_COUNT).length} 个`
        : `Resampled to ${next.length} pts with sparse control handles`,
    );
  }, [activeLayer, points, wallPoints, zh, pushEditUndo]);

  if (!patient) return null;

  const modal = open ? (
        <div className="pointer-events-auto fixed inset-0 z-[200500] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm">
          <div className="flex h-[min(94vh,920px)] w-[min(1380px,98vw)] flex-col overflow-hidden rounded-2xl border border-cyan-400/25 bg-slate-950 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <div>
                <div className="text-sm font-bold text-cyan-100">
                  {zh ? '交互分割 / 边界编辑' : 'Interactive seg / boundary edit'}
                </div>
                <div className="mt-0.5 text-[11px] text-slate-400">
                  {patient.id_short}, {zh ? '橙/绿手柄软变形（direction_demo 同款）; 保存后 Agent 用编辑边界' : 'Soft-deform like direction_demo; save feeds Agent'}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={undoLen <= 0}
                  onClick={undoEdit}
                  className="rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                >
                  {zh ? `撤销 (${undoLen})` : `Undo (${undoLen})`}
                </button>
                <button
                  type="button"
                  disabled={!hasOriginal}
                  onClick={restoreOriginal}
                  className="rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                >
                  {zh ? '恢复原始' : 'Restore'}
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg border border-white/15 p-2 text-slate-300 hover:bg-white/5"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-2">
              {([
                ['soft', zh ? '软变形' : 'Soft', MousePointer2],
                ['hard', zh ? '硬拖点' : 'Hard', Pencil],
                ['add', zh ? '加点' : 'Add', Plus],
                ['delete', zh ? '删点' : 'Delete', Eraser],
                ['sam', 'SAM click', Sparkles],
              ] as const).map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  disabled={id === 'sam' && samAvailable === false}
                  onClick={() => {
                    setMode(id);
                    if (id === 'sam') {
                      setMessage(
                        zh
                          ? 'SAM: 单击前景; Shift+排除; 拖框区域; 连续点选精修'
                          : 'SAM: click include; Shift exclude; drag box; refine',
                      );
                    }
                  }}
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                    mode === id
                      ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                      : 'border-white/10 text-slate-300 hover:bg-white/5'
                  } disabled:opacity-40`}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
              {mode === 'sam' && (
                <button
                  type="button"
                  onClick={() => {
                    clearSamPrompts();
                    setMessage(zh ? '已清除 SAM 提示点' : 'SAM prompts cleared');
                  }}
                  className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-100"
                >
                  {zh ? `清除提示 (${samClicks.length})` : `Clear prompts (${samClicks.length})`}
                </button>
              )}
              <button
                type="button"
                disabled={activePoints.length < 8}
                onClick={simplifyActiveLayer}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-100 disabled:opacity-40"
                title={zh ? '弧长重采样稠密轮廓（不砍成稀少折线）' : 'Arc-length resample dense contour'}
              >
                {zh ? '重采样' : 'Resample'}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                onClick={() => setActiveLayer('wall')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  activeLayer === 'wall'
                    ? 'border-orange-400/50 bg-orange-500/20 text-orange-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '橙, 胃壁' : 'Orange wall'} ({wallPoints.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveLayer('lesion')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  activeLayer === 'lesion'
                    ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '青, 病灶' : 'Cyan lesion'} ({points.length})
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                onClick={() => setMediaMode('image')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  mediaMode === 'image'
                    ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '静图' : 'Image'}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (videos.length) openPatientVideoSam();
                  else setMediaMode('video');
                }}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  mediaMode === 'video'
                    ? 'border-violet-400/50 bg-violet-500/20 text-violet-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                <Video size={13} />
                {zh ? `视频 SAM${videos.length ? ` (${videos.length})` : ''}` : `Video SAM${videos.length ? ` (${videos.length})` : ''}`}
              </button>
              <div className="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                <span>ROI</span>
                <select
                  value={roiMode}
                  onChange={(e) => setRoiMode(e.target.value as typeof roiMode)}
                  className="rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                >
                  <option value="predicted">{zh ? '编辑框' : 'Edited bbox'}</option>
                  <option value="doctor">{zh ? '磁盘医生 ROI' : 'Disk doctor ROI'}</option>
                  <option value="auto">Auto</option>
                </select>
              </div>
            </div>

            {mediaMode === 'video' && (
              <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-violet-950/30 px-4 py-2">
                <video ref={videoRef} className="hidden" muted playsInline crossOrigin="anonymous" />
                <select
                  value={videoUrl}
                  onChange={(e) => {
                    setVideoUrl(e.target.value);
                    setIsPlaying(false);
                  }}
                  className="max-w-[280px] rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                >
                  <option value="">{zh ? '选择视频…' : 'Select video…'}</option>
                  {videos.map((v) => (
                    <option key={v.url} value={v.url}>
                      {v.filename}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!videoUrl}
                  onClick={() => {
                    const v = videoRef.current;
                    if (!v) return;
                    if (v.paused) void v.play();
                    else v.pause();
                  }}
                  className="flex items-center gap-1 rounded-lg border border-violet-400/40 px-2.5 py-1.5 text-[11px] text-violet-100 disabled:opacity-40"
                >
                  {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                  {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
                </button>
                <input
                  type="range"
                  min={0}
                  max={Math.max(videoDuration, 0.01)}
                  step={0.01}
                  value={videoTime}
                  disabled={!videoUrl}
                  onChange={(e) => {
                    const t = Number(e.target.value);
                    const v = videoRef.current;
                    if (v) {
                      v.pause();
                      v.currentTime = t;
                      setVideoTime(t);
                      // Seeking chooses a new edit frame
                      setFrameFrozen(false);
                      frameFrozenRef.current = false;
                      syncFrameFromVideo({ force: true });
                      // freeze again after seek so edit doesn't flicker
                      requestAnimationFrame(() => {
                        setFrameFrozen(true);
                        frameFrozenRef.current = true;
                        redraw();
                      });
                    }
                  }}
                  className="min-w-[140px] flex-1"
                />
                <span className="font-mono text-[10px] text-violet-200/90">
                  {videoTime.toFixed(2)}s / {videoDuration.toFixed(2)}s
                </span>
                <label className="flex items-center gap-1.5 text-[10px] text-violet-100/90">
                  <input
                    type="checkbox"
                    checked={trackOnPlay}
                    disabled={frameFrozen}
                    onChange={(e) => {
                      setTrackOnPlay(e.target.checked);
                      if (e.target.checked) {
                        setFrameFrozen(false);
                        frameFrozenRef.current = false;
                      }
                    }}
                  />
                  {zh ? '播放时自动跟随（编辑时请关）' : 'Auto-track on play'}
                </label>
                <button
                  type="button"
                  disabled={!videoUrl || keyBusy}
                  onClick={async () => {
                    setKeyBusy(true);
                    setMessage(zh ? '邻域关键帧打分中…' : 'Scoring neighborhood keyframes…');
                    try {
                      const res = await fetch('/api/agent/video/keyframes', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                          video_url: videoUrl,
                          anchor_sec: videoTime,
                          window_sec: 2.0,
                          top_k: 5,
                        }),
                      });
                      const data = await res.json();
                      if (!data.ok) throw new Error(data.error || 'keyframe failed');
                      setKeyCandidates(data.keyframes || []);
                      setMessage(
                        zh
                          ? `关键帧候选 ${data.keyframes?.length || 0} 帧（锚点 ${videoTime.toFixed(2)}s）`
                          : `${data.keyframes?.length || 0} keyframe candidates`,
                      );
                    } catch (err) {
                      setMessage(err instanceof Error ? err.message : 'keyframe failed');
                    } finally {
                      setKeyBusy(false);
                    }
                  }}
                  className="rounded-lg border border-violet-400/40 px-2 py-1 text-[10px] text-violet-100 disabled:opacity-40"
                >
                  {keyBusy ? (zh ? '打分中…' : 'Scoring…') : (zh ? '邻域关键帧' : 'Near keyframes')}
                </button>
                <button
                  type="button"
                  disabled={!videoUrl || samBusy || propagateBusy || points.length < 3}
                  onClick={() => {
                    freezeCurrentFrame();
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) void runSamAtPoint(c, { source: 'sam', box, keepEditing: true });
                    else setMessage(zh ? '先 SAM 点选或载入边界' : 'Seed a polygon first');
                  }}
                  className="rounded-lg border border-violet-400/40 px-2 py-1 text-[10px] text-violet-100 disabled:opacity-40"
                >
                  {zh ? '本帧用当前区域重算' : 'Re-SAM with region'}
                </button>
                <button
                  type="button"
                  disabled={!videoUrl || propagateBusy || points.length < 3}
                  onClick={() => void propagateMaskAcrossVideo()}
                  className="rounded-lg border border-emerald-400/50 bg-emerald-500/20 px-2 py-1 text-[10px] font-semibold text-emerald-100 disabled:opacity-40"
                  title={zh ? '把当前可编辑区域固定为 mask/box prompt，向后续帧扩散' : 'Lock region as mask prompt and propagate'}
                >
                  {propagateBusy
                    ? (propagateProgress || (zh ? '扩散中…' : 'Propagating…'))
                    : (zh ? '固定并扩散到邻帧' : 'Lock & propagate')}
                </button>
                {frameFrozen && (
                  <button
                    type="button"
                    onClick={() => {
                      setFrameFrozen(false);
                      frameFrozenRef.current = false;
                      syncFrameFromVideo({ force: true });
                      redraw();
                      setMessage(zh ? '已解除帧冻结，可继续播放' : 'Frame unfrozen');
                    }}
                    className="rounded-lg border border-amber-400/40 px-2 py-1 text-[10px] text-amber-100"
                  >
                    {zh ? '解除冻结' : 'Unfreeze'}
                  </button>
                )}
                {!videos.length && (
                  <span className="text-[10px] text-amber-300/90">
                    {zh
                      ? '未命中 crop_ui/阅片库视频：可换病例或用样例目录'
                      : 'No crop_ui/reader video match — try another case or sample catalog'}
                  </span>
                )}
                {!!videos.length && mediaMode === 'video' && !videoUrl && (
                  <button
                    type="button"
                    onClick={openPatientVideoSam}
                    className="rounded-lg border border-violet-400/50 bg-violet-500/30 px-2 py-1 text-[10px] text-violet-50"
                  >
                    {zh ? '打开对应视频' : 'Open matched video'}
                  </button>
                )}
                {!videos.length && (
                  <button
                    type="button"
                    onClick={async () => {
                      const res = await fetch('/api/patients/videos?list=1&limit=30');
                      const data = await res.json();
                      const list = (data.videos || []).map((v: VideoInfo & { patient_key?: string }) => ({
                        url: v.url,
                        filename: v.filename,
                        treatment: v.treatment || 'direct_surgery',
                        water_filled: Boolean(v.water_filled),
                      }));
                      setVideos(list);
                      if (list[0]) setVideoUrl(list[0].url);
                    }}
                    className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300"
                  >
                    {zh ? '载入样例视频' : 'Load sample videos'}
                  </button>
                )}
              </div>
            )}

            {mediaMode === 'video' && keyCandidates.length > 0 && (
              <div className="flex gap-2 overflow-x-auto border-b border-white/10 bg-black/50 px-4 py-2">
                {keyCandidates.map((kf) => (
                  <button
                    key={`${kf.timestamp_sec}-${kf.score}`}
                    type="button"
                    onClick={() => {
                      const v = videoRef.current;
                      if (!v) return;
                      v.pause();
                      v.currentTime = kf.timestamp_sec;
                      setVideoTime(kf.timestamp_sec);
                      syncFrameFromVideo();
                      setMessage(
                        zh
                          ? `跳转到候选 ${kf.timestamp_sec.toFixed(2)}s, score=${kf.score}`
                          : `Seek ${kf.timestamp_sec.toFixed(2)}s, score=${kf.score}`,
                      );
                    }}
                    className="flex w-[108px] shrink-0 flex-col overflow-hidden rounded-lg border border-violet-400/30 bg-violet-950/40 text-left hover:border-violet-300/60"
                  >
                    {kf.thumb_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={kf.thumb_url} alt="" className="h-14 w-full object-cover" />
                    ) : (
                      <div className="flex h-14 items-center justify-center text-[10px] text-slate-500">no thumb</div>
                    )}
                    <div className="px-1.5 py-1 font-mono text-[9px] text-violet-100">
                      {kf.timestamp_sec.toFixed(2)}s, {kf.score.toFixed(2)}
                    </div>
                    <div className="truncate px-1.5 pb-1 text-[8px] text-slate-400">
                      {(kf.reasons || []).join(',')}
                    </div>
                  </button>
                ))}
              </div>
            )}

            <div className="flex min-h-0 flex-1 flex-col md:flex-row">
              <div ref={containerRef} className="relative min-h-0 flex-1 bg-black">
                <canvas
                  ref={canvasRef}
                  className="h-full w-full touch-none"
                  style={{ cursor: dragIndex !== null ? 'grabbing' : mode === 'soft' || mode === 'hard' ? 'grab' : 'crosshair' }}
                  onPointerDown={onPointerDown}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onPointerCancel={onPointerUp}
                />
                {(samBusy || propagateBusy || (mediaMode === 'image' && !imgLoaded)) && (
                  <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="animate-spin text-cyan-300" size={28} />
                  </div>
                )}
              </div>
              <aside className="max-h-[42vh] w-full shrink-0 overflow-y-auto border-t border-white/10 bg-slate-950/90 p-3 md:max-h-none md:w-[300px] md:border-l md:border-t-0">
                <WallFeatureAnalysisCard
                  zh={zh}
                  lesionPolygon={points}
                  wallPolygon={wallPoints}
                  frameSize={frameSize}
                  frameDataUrl={frameDataUrl}
                  pick={layerPick}
                  paused={dragIndex !== null || samBusy || propagateBusy}
                  onResult={(r) => {
                    setLayerResult(r);
                    onImagingAssist?.({
                      layerResult: r,
                      lesionPolygon: pointsRef.current,
                      wallPolygon: wallPointsRef.current,
                      frameSize,
                    });
                  }}
                />
                <p className="mt-2 text-[9px] leading-relaxed text-slate-500">
                  {zh
                    ? '算法迁自人机互助 ContactGeom / LayerBridge；达层为软提示，不作病理金标准。Alt+点击设取样点；「纪要」看会议验收点。'
                    : 'Migrated ContactGeom/LayerBridge; Alt+click sets pick. Layer read is soft hint only.'}
                </p>
              </aside>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-white/10 px-4 py-3">              <button
                type="button"
                disabled={saving || points.length < 3}
                onClick={() => void handleSave()}
                className="flex items-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold text-emerald-100 disabled:opacity-40"
              >
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {zh ? '保存覆盖' : 'Save override'}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => void handleClear()}
                className="flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
              >
                <Trash2 size={13} />
                {zh ? '清除' : 'Clear'}
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[11px] text-cyan-100"
              >
                <Check size={13} />
                {zh ? '完成并关闭' : 'Done'}
              </button>
              <div className="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                <ZoomIn size={12} />
                <span>
                  {zh ? '当前层' : 'Layer'} {activeLayer === 'wall' ? wallPoints.length : points.length}pt
                  {wallPoints.length >= 3 ? `, ${zh ? '壁' : 'wall'}${wallPoints.length}` : ''}
                </span>
                {samAvailable === false && (
                  <span className="text-amber-300/90">
                    {zh ? 'SAM 未启动（可手动编辑）' : 'SAM offline (manual edit OK)'}
                  </span>
                )}
              </div>
            </div>
            {message && (
              <div className="border-t border-white/5 px-4 py-2 text-[11px] text-slate-300">{message}</div>
            )}
          </div>
        </div>
  ) : null;

  return (
    <>
      <div className="pointer-events-auto absolute bottom-[5.75rem] left-3 z-[110] flex flex-col gap-2">
        <button
          type="button"
          onClick={() => openEditor({ sam: true })}
          className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-[11px] font-semibold shadow-lg backdrop-blur transition hover:-translate-y-0.5 ${
            override
              ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
              : 'border-white/15 bg-black/70 text-gray-200 hover:border-cyan-400/40'
          }`}
          title={zh ? '打开交互 SAM 分割与边界编辑' : 'Open interactive SAM + boundary edit'}
        >
          <Pencil size={14} />
          <span>{zh ? '边界编辑 / SAM' : 'Edit / SAM'}</span>
          {override && (
            <span className="rounded-full bg-cyan-400/20 px-1.5 py-0.5 text-[9px] text-cyan-200">
              {override.mask_polygon.length}pt
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => openEditor({ videoSam: true })}
          className="flex items-center gap-2 rounded-xl border border-violet-400/40 bg-violet-500/20 px-3 py-2 text-[11px] font-semibold text-violet-100 shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:border-violet-300/60"
          title={zh ? '免上传：直接打开本例对应视频并进入 SAM' : 'Open matched patient video for SAM (no upload)'}
        >
          <Video size={14} />
          <span>{zh ? '视频 SAM' : 'Video SAM'}</span>
        </button>
      </div>
      {typeof document !== 'undefined' ? createPortal(modal, document.body) : modal}
    </>
  );
}
