'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Check, Eraser, Layers, Loader2, MousePointer2, PanelTop, Pause, Pencil, Play, Plus, Save, SkipBack, SkipForward, Sparkles, Trash2, Video, X, ZoomIn,
} from 'lucide-react';
import type { MaskBoundaryOverride, Patient, VideoInfo, VideoMaskFrameOverride } from '@/types';
import type { SamReport } from '@/lib/reader/types';
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
type LesionSegmentationModel = 'dinov3' | 'convnext';
const VIDEO_PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
type KeyframeCandidate = {
  timestamp_sec: number;
  score: number;
  reasons?: string[];
  thumb_url?: string;
  predicted_polygon?: number[][];
  prediction_status?: 'pending' | 'predicted' | 'needs_roi' | 'failed';
  prediction_error?: string;
};

export type DinoFeatureResult = {
  available?: boolean;
  case_id?: string;
  frame_time?: number;
  model?: string;
  layer_index?: number;
  input_size?: number;
  token_grid?: [number, number];
  feature_dim?: number;
  feature_vector?: number[];
  feature_names?: string[];
  scalars?: Record<string, number>;
  feature_overlay_png?: string;
  wall_evidence_overlay_png?: string;
  elapsed_ms?: number;
  error?: string;
};
interface InteractiveSegPanelProps {
  patient: Patient | null;
  override: MaskBoundaryOverride | null;
  onOverrideChange: (next: MaskBoundaryOverride | null) => void;
  /** Optional: wall-layer + GC-US assist payload for DiagnosisPanel */
  onImagingAssist?: (payload: ImagingAssistPayload | null) => void;
  /** Current-frame system evidence shown in the AI-assisted task panel. */
  onSystemReport?: (report: SamReport | null) => void;
  /** Current-frame DINO region feature result shown in the workbench evidence panel. */
  onDinoFeatures?: (result: DinoFeatureResult | null) => void;
  /** Route the current video evidence into the unified research Agent. */
  onUnifiedAgentRun?: (capture: UnifiedAgentCapture) => Promise<void> | void;
  unifiedAgentBusy?: boolean;
  inline?: boolean;
}

export type UnifiedAgentFrame = {
  frame_png_b64: string;
  frame_id: string;
  frame_index: number;
  timestamp_sec: number;
  quality_score: number;
};

export type UnifiedAgentCapture = {
  frames: UnifiedAgentFrame[];
  current_time: number;
  image_width: number;
  image_height: number;
  mask_polygon: number[][];
  roi_bbox?: { x1: number; y1: number; x2: number; y2: number };
};

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

function seekVideoForAgent(video: HTMLVideoElement, time: number): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      video.removeEventListener('seeked', done);
      resolve();
    };
    video.addEventListener('seeked', done, { once: true });
    video.currentTime = time;
    window.setTimeout(done, 1200);
  });
}

function sanitizeSystemCopy(value: unknown): string {
  return String(value ?? '')
    .replace(/\bSAM(?:2)?\b/gi, 'system analysis')
    .replace(/\bSegment Anything(?: Model)?\b/gi, 'system analysis');
}

function buildModelAssistReport(
  patient: Patient,
  polygon: number[][],
  frameWidth: number,
  frameHeight: number,
  model: LesionSegmentationModel,
  areaRatio?: number,
): SamReport {
  const clinicalText = [
    patient.report?.ultrasound_findings,
    patient.report?.ultrasound_impression,
    patient.report?.ct_findings,
    patient.report?.ct_impression,
    patient.report?.enhanced_ct_report,
    patient.report?.endoscopy_report,
  ].filter(Boolean).join(' ');
  const text = clinicalText.toLowerCase();
  const bbox = bboxFromPolygon(polygon);
  const lengthPx = bbox ? Math.max(bbox.x2 - bbox.x1, bbox.y2 - bbox.y1) : 0;
  const thicknessPx = bbox ? Math.min(bbox.x2 - bbox.x1, bbox.y2 - bbox.y1) : 0;
  const polygonArea = polygon.reduce((sum, point, index) => {
    const next = polygon[(index + 1) % polygon.length] || point;
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
  const boxArea = Math.max(1, (bbox?.x2 || 0) - (bbox?.x1 || 0)) * Math.max(1, (bbox?.y2 || 0) - (bbox?.y1 || 0));
  const solidity = Math.abs(polygonArea) / boxArea;
  const shape = solidity < 0.72 || (lengthPx > 0 && lengthPx / Math.max(thicknessPx, 1) > 2.8)
    ? '局部浸润型'
    : '局限隆起型';
  const boundary = solidity < 0.72 ? '边界不规则' : '边界相对清晰，需结合连续帧复核';
  const layer = /突破肌层|侵犯肌层|固有肌层.*(破坏|受累)/.test(text)
    ? '固有肌层受累/结构破坏'
    : /层次.*(完整|清晰)|肌层结构完整/.test(text)
      ? '胃壁层次结构相对完整'
      : '当前帧层次显示有限，需多切面复核';
  const serosa = /浆膜.*(中断|破坏|侵犯|不完整)/.test(text)
    ? '浆膜连续性中断/受侵犯'
    : /浆膜.*(完整|连续|光滑)/.test(text)
      ? '浆膜连续'
      : '当前帧未能确认浆膜连续性';
  const perigastric = /胃周|脂肪间隙|邻近器官/.test(text)
    ? '已从影像文字资料纳入胃周组织评估'
    : '当前帧未能确认胃周组织';
  const stage = /浆膜.*(中断|破坏|侵犯|不完整)/.test(text)
    ? 'T4+'
    : /突破肌层|侵犯肌层|浆膜下/.test(text)
      ? 'T3'
      : /固有肌层.*(受累|侵犯)|肌层.*受累/.test(text)
        ? 'T2'
        : /黏膜下|肌层结构完整/.test(text)
          ? 'T1'
          : 'cTx';
  const location = patient.clinical?.location || '胃';
  const clinicalLength = patient.clinical?.tumorSize?.length;
  const clinicalThickness = patient.clinical?.tumorSize?.thickness;
  const lengthText = clinicalLength
    ? `${clinicalLength} mm（临床资料）`
    : `${Math.round(lengthPx)} px（当前帧几何估计）`;
  const thicknessText = clinicalThickness
    ? `${clinicalThickness} mm（临床资料）`
    : `${Math.round(thicknessPx)} px（当前帧几何估计）`;
  const modelLabel = model === 'dinov3' ? 'DINOv3 lesion candidate' : 'ConvNeXt-Base UNet';
  const signs = {
    size: {
      length: {
        value: lengthText,
        status: 'suggested',
        source: clinicalLength ? 'clinical_data' : 'model_geometry',
        confidence: 0.62,
        evidence_ref: ['lesion_mask.bbox', 'clinical.tumor_size'],
      },
      thickness: {
        value: thicknessText,
        status: 'suggested',
        source: clinicalThickness ? 'clinical_data' : 'model_geometry',
        confidence: 0.62,
        evidence_ref: ['lesion_mask.bbox', 'clinical.tumor_size'],
      },
    },
    layer_structure: { value: layer, status: /当前帧/.test(layer) ? 'uncertain' : 'suggested', source: /当前帧/.test(layer) ? 'limited_frame' : 'clinical_text', confidence: 0.5, evidence_ref: ['clinical.imaging_text'] },
    morphology: { value: shape, status: 'suggested', source: 'mask_geometry', confidence: 0.58, evidence_ref: ['lesion_mask.solidity', 'lesion_mask.aspect_ratio'] },
    boundary: { value: boundary, status: 'suggested', source: 'mask_geometry', confidence: 0.55, evidence_ref: ['lesion_mask.boundary'] },
    growth_pattern: { value: shape, status: 'suggested', source: 'mask_geometry', confidence: 0.45, evidence_ref: ['lesion_mask.shape'] },
    serosa_change: { value: serosa, status: /当前帧/.test(serosa) ? 'uncertain' : 'suggested', source: /当前帧/.test(serosa) ? 'limited_frame' : 'clinical_text', confidence: 0.45, evidence_ref: ['clinical.imaging_text'] },
    perigastric_tissue: { value: perigastric, status: /未能/.test(perigastric) ? 'uncertain' : 'suggested', source: /未能/.test(perigastric) ? 'limited_frame' : 'clinical_text', confidence: 0.4, evidence_ref: ['clinical.imaging_text'] },
  } as unknown as NonNullable<SamReport['signs']>;
  const prose = `【超声所见】${location}见低回声占位性病变，大小约${lengthText}，最大厚度${thicknessText}。病灶呈${shape}，${boundary}。胃壁层次：${layer}；浆膜：${serosa}；胃周组织：${perigastric}。\n\n【辅助分析】${modelLabel} 当前帧病灶面积占比 ${areaRatio != null ? `${(areaRatio * 100).toFixed(2)}%` : '未返回'}。该结果为模型辅助证据，需医生在关键帧上修正。\n\n【分期倾向】${stage}（仅基于当前模型与影像文字证据，非病理结论）。`;
  return {
    recommended_stage: stage,
    recommendation_status: stage === 'cTx' ? 'uncertain' : 'suggested',
    signs,
    calibrated_confidence: stage === 'cTx' ? 0.4 : 0.58,
    summary: prose,
    template_id: 'gc_us_t_report_template_v1',
    schema_version: 'gc_us_report_signs_v1',
    source_doc: '胃癌T分期自进化智能辅助诊断_报告模板_讨论版.docx',
    template_prose: prose,
    evidence: [
      { title: '病灶分割', detail: `${modelLabel} · ${polygon.length} contour points`, status: 'suggested', source: modelLabel },
      { title: '形态与边界', detail: `${shape} · ${boundary}`, status: 'suggested', source: 'mask_geometry' },
      { title: '层次与浆膜', detail: `${layer} · ${serosa}`, status: 'uncertain', source: 'clinical_text_or_limited_frame' },
    ],
  };
}

export function InteractiveSegPanel({
  patient,
  override,
  onOverrideChange,
  onImagingAssist,
  onSystemReport,
  onDinoFeatures,
  onUnifiedAgentRun,
  unifiedAgentBusy = false,
  inline = false,
}: InteractiveSegPanelProps) {
  const { language } = useSettings();
  const zh = language === 'zh';
  const simpleVideoMode = inline && patient?.phase === 'reader_v150';
  const [simplePromptMode, setSimplePromptMode] = useState<'point' | 'box'>('box');
  const [simpleEditMode, setSimpleEditMode] = useState(false);
  const [simpleToolsOpen, setSimpleToolsOpen] = useState(true);
  const [simplePromptBox, setSimplePromptBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
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
  const [samReport, setSamReport] = useState<SamReport | null>(null);
  const [dinoBusy, setDinoBusy] = useState(false);
  const [dinoResult, setDinoResult] = useState<DinoFeatureResult | null>(null);
  const [segmentationModel, setSegmentationModel] = useState<LesionSegmentationModel>('dinov3');
  const [segmentationBusy, setSegmentationBusy] = useState(false);
  const [segmentationModelResult, setSegmentationModelResult] = useState<{
    model?: string;
    lesion_area_ratio?: number;
    validation_summary?: Record<string, unknown>;
    error?: string;
  } | null>(null);
  const [samClicks, setSamClicks] = useState<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const [samBoxPreview, setSamBoxPreview] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [samAvailable, setSamAvailable] = useState<boolean | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [roiMode, setRoiMode] = useState<'predicted' | 'doctor' | 'auto'>('predicted');
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoPlaybackRate, setVideoPlaybackRate] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [trackOnPlay, setTrackOnPlay] = useState(false);
  const [trackingPrepared, setTrackingPrepared] = useState(false);
  const [precomputeBusy, setPrecomputeBusy] = useState(false);
  const [precomputeProgress, setPrecomputeProgress] = useState<string | null>(null);
  const [keyCandidates, setKeyCandidates] = useState<KeyframeCandidate[]>([]);
  const [keyBusy, setKeyBusy] = useState(false);
  const [pendingOpenVideoSam, setPendingOpenVideoSam] = useState(false);
  const [pendingKeyframeRequest, setPendingKeyframeRequest] = useState(false);
  /** Freeze display frame while editing vertices / after SAM — prevents click refresh flicker. */
  const [frameFrozen, setFrameFrozen] = useState(false);
  const [propagateBusy, setPropagateBusy] = useState(false);
  const [propagateProgress, setPropagateProgress] = useState<string | null>(null);
  const [videoFrameOverrides, setVideoFrameOverrides] = useState<VideoMaskFrameOverride[]>([]);
  const [frameDataUrl, setFrameDataUrl] = useState<string | null>(null);
  const [layerResult, setLayerResult] = useState<LayerAnalyzeResult | null>(null);
  const [wallAnalysisOpen, setWallAnalysisOpen] = useState(false);
  const [layerPick, setLayerPick] = useState<{ x: number; y: number } | null>(null);
  const [undoLen, setUndoLen] = useState(0);
  const [hasOriginal, setHasOriginal] = useState(false);
  const trackingClientIdRef = useRef(`tab_${Math.random().toString(36).slice(2)}`);
  const trackingSessionId = useMemo(() => {
    if (mediaMode !== 'video' || !videoUrl || !patient) return '';
    const raw = `${trackingClientIdRef.current}__${patient.patient_id || patient.id}__${videoUrl}`;
    return raw.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 160);
  }, [mediaMode, patient, videoUrl]);

  useEffect(() => {
    if (!inline || patient?.phase !== 'reader_v150') return;
    setOpen(true);
    setPendingOpenVideoSam(true);
    setMediaMode('video');
    setMode('sam');
  }, [inline, patient?.id, patient?.phase]);

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
  const videoFrameOverridesRef = useRef<VideoMaskFrameOverride[]>([]);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const undoStackRef = useRef<Array<{ lesion: number[][]; wall: number[][] }>>([]);
  const originalRef = useRef<{ lesion: number[][]; wall: number[][] } | null>(null);
  const playbackRafRef = useRef<number | null>(null);
  const playbackUiAtRef = useRef(0);
  const predictKeyframesRef = useRef<(candidates: KeyframeCandidate[]) => Promise<void>>(async () => {});
  const runLesionModelRef = useRef<
    (imgPt: number[] | null, box: { x1: number; y1: number; x2: number; y2: number } | null, clicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }>) => Promise<number[][] | null>
  >(async () => null);
  const samAbortRef = useRef<AbortController | null>(null);
  const samGenRef = useRef(0);
  const draggingRef = useRef(false);
  const samBusyRef = useRef(false);
  const samClicksRef = useRef<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const samBoxDragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  // Keep playback listeners attached while React redraws the canvas or tracks a frame.
  // Re-running the source effect on every state change would call video.load() and pause playback.
  const redrawRef = useRef<() => void>(() => {});
  const maybeTrackWhilePlayingRef = useRef<() => Promise<void>>(async () => {});
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

  useEffect(() => {
    const video = videoRef.current;
    if (playbackRafRef.current !== null) {
      cancelAnimationFrame(playbackRafRef.current);
      playbackRafRef.current = null;
    }
    video?.pause();
    if (video) {
      video.removeAttribute('src');
      video.load();
    }
    setIsPlaying(false);
    setVideoTime(0);
    setVideoDuration(0);
    setVideoUrl('');
    setVideos([]);
    setImgLoaded(false);
  }, [patient?.id]);

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
      setSamReport(null);
      setPoints([]);
      setWallPoints([]);
      setVideoFrameOverrides([]);
      setImgLoaded(false);
      return;
    }
    if (!(inline && patient.phase === 'reader_v150')) setOpen(false);
    setSamReport(null);
    setDinoResult(null);
    setSegmentationModelResult(null);
    setSegmentationBusy(false);
    onDinoFeatures?.(null);
    setSimplePromptMode('box');
    setSimpleEditMode(false);
    setSimpleToolsOpen(true);
    setSimplePromptBox(null);
    videoFrameOverridesRef.current = override?.video_frames || [];
    setVideoFrameOverrides(override?.video_frames || []);
    setKeyCandidates([]);
    setPendingKeyframeRequest(false);
    setTrackingPrepared(false);
    setPrecomputeBusy(false);
    setPrecomputeProgress(null);
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
  }, [inline, patient?.id, patient?.phase, override?.updated_at, override?.mask_polygon, override?.wall_polygon, override?.video_frames, patient?.json_url, patient?.segmentation?.annotation_url, zh, snapshotOriginal, onDinoFeatures]);

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
      // Reader-study media is already case-resolved. Other queues can use the
      // allowlisted patient video catalog, including external centers.
      if (patient.phase !== 'reader_v150') {
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
            ? `已打开对应视频：${list[0].filename}，点击目标或框选 ROI`
            : `Opened ${list[0].filename}; click the target or draw an ROI box`,
        );
      } else if (pendingOpenVideoSam && !list.length) {
        setPendingOpenVideoSam(false);
        setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      }
    })();
    return () => { cancelled = true; };
  }, [open, patient?.patient_id, patient?.video_urls, pendingOpenVideoSam, zh]);

  useEffect(() => {
    if (!simpleVideoMode || mediaMode !== 'video' || !videoUrl || !videos.length) return;
    const filename = videos.find((video) => video.url === videoUrl)?.filename || videos[0].filename;
    setMessage(
      zh
        ? `已打开对应视频：${filename}，点击目标或框选 ROI`
        : `Opened ${filename}; click the target or draw an ROI box`,
    );
  }, [mediaMode, simpleVideoMode, videoUrl, videos, zh]);

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
        ? `已打开对应视频：${videos.find((v) => v.url === url)?.filename || 'video'}，点击目标或框选 ROI`
        : `Opened patient video; click the target or draw an ROI box`,
    );
  }, [videos, videoUrl, zh]);

  const scoreKeyframes = useCallback(async () => {
    if (!videoUrl || keyBusy) return;
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
      const data = await res.json() as { ok?: boolean; error?: string; keyframes?: KeyframeCandidate[] };
      if (!res.ok || !data.ok) throw new Error(data.error || 'keyframe failed');
      const candidates = (data.keyframes || []).map((candidate) => ({
        ...candidate,
        prediction_status: pointsRef.current.length >= 3 ? 'pending' as const : 'needs_roi' as const,
      }));
      setKeyCandidates(candidates);
      if (pointsRef.current.length < 3) {
        setMessage(
          zh
            ? `已选出 ${candidates.length} 个关键帧；请先框选病灶，再生成对应病灶预测`
            : `${candidates.length} keyframes selected; draw an ROI box first to predict the lesion on each frame`,
        );
      } else {
        await predictKeyframesRef.current(candidates);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'keyframe failed');
    } finally {
      setKeyBusy(false);
    }
  }, [keyBusy, videoTime, videoUrl, zh]);

  useEffect(() => {
    if (!pendingKeyframeRequest || mediaMode !== 'video' || !videoUrl || keyBusy) return;
    setPendingKeyframeRequest(false);
    void scoreKeyframes();
  }, [keyBusy, mediaMode, pendingKeyframeRequest, scoreKeyframes, videoUrl]);

  const extractDinoFeatures = useCallback(async () => {
    if (!patient || dinoBusy) return;
    setDinoBusy(true);
    setMessage(zh ? 'DINO 特征提取中，首次加载可能较慢…' : 'Extracting DINO features; first load may take longer…');
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/dino/features', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: patient.patient_id,
          frame_time: mediaMode === 'video'
            ? Number(videoRef.current?.currentTime ?? videoTime)
            : 0,
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
          lesion_polygon: pointsRef.current.map((point) => [point[0] * scale, point[1] * scale]),
          wall_polygon: wallPointsRef.current.map((point) => [point[0] * scale, point[1] * scale]),
          layer_index: 11,
        }),
      });
      const payload = await response.json() as { ok?: boolean; result?: DinoFeatureResult; error?: string };
      if (!response.ok || !payload.ok || !payload.result?.available) {
        throw new Error(payload.error || payload.result?.error || 'DINO feature extraction unavailable');
      }
      setDinoResult(payload.result);
      onDinoFeatures?.(payload.result);
      setMessage(
        zh
          ? `DINO 特征已提取：${payload.result.feature_dim || 0} 维，${payload.result.token_grid?.join(' × ') || '未知'} token 网格`
          : `DINO features extracted: ${payload.result.feature_dim || 0} dimensions`,
      );
    } catch (error) {
      const failure: DinoFeatureResult = {
        available: false,
        error: error instanceof Error ? error.message : 'DINO feature extraction failed',
      };
      setDinoResult(failure);
      onDinoFeatures?.(failure);
      setMessage(failure.error || 'DINO feature extraction failed');
    } finally {
      setDinoBusy(false);
    }
  }, [dinoBusy, mediaMode, onDinoFeatures, patient, videoTime, zh]);

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

  const runUnifiedAgent = useCallback(async () => {
    if (!onUnifiedAgentRun || !simpleVideoMode || mediaMode !== 'video' || unifiedAgentBusy) return;
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight || !videoUrl) {
      setMessage(zh ? '视频帧尚未准备好' : 'Video frame is not ready');
      return;
    }
    const originalTime = video.currentTime || videoTime;
    const duration = video.duration || 0;
    const span = duration > 0 ? Math.max(0.5, Math.min(2, duration / 8)) : 0;
    const positions = Array.from(new Set(
      [originalTime - span, originalTime, originalTime + span]
        .filter((time) => time >= 0 && (!duration || time < duration))
        .map((time) => Number(time.toFixed(3))),
    ));
    const wasPlaying = !video.paused;
    if (wasPlaying) video.pause();
    try {
      const frames: UnifiedAgentFrame[] = [];
      for (const [index, position] of positions.entries()) {
        if (Math.abs(video.currentTime - position) > 0.01) {
          await seekVideoForAgent(video, position);
        }
        const frame = await videoOrImageToSamFrame(video, null, true, 1024);
        frames.push({
          frame_png_b64: frame.b64,
          frame_id: `${patient.id}:${position}`,
          frame_index: index,
          timestamp_sec: position,
          quality_score: 1,
        });
      }
      if (Math.abs(video.currentTime - originalTime) > 0.01) {
        await seekVideoForAgent(video, originalTime);
      }
      setVideoTime(originalTime);
      if (wasPlaying) void video.play().catch(() => {});
      await onUnifiedAgentRun({
        frames,
        current_time: originalTime,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        mask_polygon: pointsRef.current,
        roi_bbox: bboxFromPolygon(pointsRef.current) || undefined,
      });
      setMessage(zh ? '统一 Agent 已返回当前证据状态' : 'Unified Agent returned the current evidence state');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '统一 Agent 分析失败' : 'Unified Agent analysis failed'));
    }
  }, [mediaMode, onUnifiedAgentRun, patient, simpleVideoMode, unifiedAgentBusy, videoTime, videoUrl, zh]);

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
      llmReport?: boolean;
    },
  ): Promise<number[][] | null> => {
    if (!patient) return null;
    // Supersede in-flight interactive requests instead of dropping clicks.
    if (!opts?.silent) {
      samAbortRef.current?.abort();
      samGenRef.current += 1;
      samBusyRef.current = true;
      setSamBusy(true);
      setMessage(zh ? '系统分析中…' : 'Running SAM…');
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
      const currentFrameTime = mediaMode === 'video'
        ? Number(videoRef.current?.currentTime ?? videoTime)
        : 0;
      const payload: Record<string, unknown> = {
        case_id: patient.patient_id,
        frame_png_b64: frame.b64,
        image_width: frame.width,
        image_height: frame.height,
        frame_time: currentFrameTime,
        video_url: mediaMode === 'video' ? videoUrl : undefined,
        tracking_session_id: trackingSessionId || undefined,
        tracking_enabled: mediaMode === 'video' && Boolean(trackingSessionId),
        tracking_reset: mediaMode === 'video'
          && opts?.source === 'sam'
          && !opts?.silent,
        llm_report: Boolean(opts?.llmReport),
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
      const nextReport = (data.result.report || null) as SamReport | null;
      setSamReport(nextReport);
      onSystemReport?.(nextReport);
      const rawPoly = (data.result.mask_polygon as number[][]).map((p) => [Number(p[0]), Number(p[1])]);
      if (rawPoly.length < 3) {
        throw new Error(
          zh
            ? '系统分析未得到有效区域，请换一个关注点重试'
            : 'No valid region returned — try another point',
        );
      }
      const promptMeta = (data.result.prompt_meta || {}) as Record<string, unknown>;
      const maskArea = Number(promptMeta.mask_area_px);
      const maskAreaRatio = Number.isFinite(maskArea) && frame.width > 0 && frame.height > 0
        ? maskArea / (frame.width * frame.height)
        : null;
      if (!opts?.silent && maskAreaRatio != null && maskAreaRatio > 0.65) {
        setSamAvailable(true);
        setMessage(
          zh
            ? `未采用过大的分割区域（${Math.round(maskAreaRatio * 100)}%），请改用框选或补充负点`
            : `Rejected an oversized region (${Math.round(maskAreaRatio * 100)}%); draw a box or add negative points`,
        );
        return null;
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
        const score = Number(data.result.sam_score);
        const scoreText = Number.isFinite(score) ? ` · score ${score.toFixed(2)}` : '';
        setMessage(
          zh
            ? `当前帧 ROI 已更新（${poly.length} 点${scoreText}）`
            : `Current-frame ROI updated (${poly.length} points${scoreText})`,
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
        setMessage(err instanceof Error ? sanitizeSystemCopy(err.message) : 'System analysis failed');
      }
      return null;
    } finally {
      if (!opts?.silent && samGenRef.current === myGen) {
        samBusyRef.current = false;
        setSamBusy(false);
      }
    }
  }, [
    patient,
    zh,
    activeLayer,
    mediaMode,
    videoTime,
    videoUrl,
    trackingSessionId,
    freezeCurrentFrame,
    snapshotOriginal,
    onSystemReport,
  ]);

  const predictKeyframes = useCallback(async (candidates: KeyframeCandidate[]) => {
    const video = videoRef.current;
    const seed = clonePoly(pointsRef.current);
    const box = bboxFromPolygon(seed);
    const centroid = polygonCentroid(seed);
    if (!simpleVideoMode || mediaMode !== 'video' || !video?.videoWidth || !video.videoHeight || !box || !centroid) {
      setKeyCandidates((current) => current.map((candidate) => ({ ...candidate, prediction_status: 'needs_roi' })));
      setMessage(zh ? '请先框选病灶，再生成关键帧病灶预测' : 'Draw an ROI box first, then generate keyframe lesion predictions');
      return;
    }

    const originalTime = video.currentTime || videoTime;
    const wasFrozen = frameFrozenRef.current;
    let predictedCount = 0;
    video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    try {
      for (const [index, candidate] of candidates.entries()) {
        const timestamp = Number(candidate.timestamp_sec || 0);
        setMessage(
          zh
            ? `关键帧病灶预测 ${index + 1}/${candidates.length}…`
            : `Predicting lesion on keyframe ${index + 1}/${candidates.length}…`,
        );
        try {
          await seekVideoForAgent(video, timestamp);
          setVideoTime(timestamp);
          const poly = simpleVideoMode
            ? await runLesionModelRef.current(centroid, box, samClicksRef.current)
            : await runSamAtPoint(centroid, {
                silent: true,
                source: 'video_track',
                box,
                keepEditing: false,
              });
          if (!poly || poly.length < 3) {
            setKeyCandidates((current) => current.map((item) => (
              item.timestamp_sec === candidate.timestamp_sec
                ? { ...item, prediction_status: 'failed', prediction_error: 'no polygon' }
                : item
            )));
            continue;
          }
          predictedCount += 1;
          const normalized = poly.map((point) => [
            Number((point[0] / video.videoWidth).toFixed(6)),
            Number((point[1] / video.videoHeight).toFixed(6)),
          ]);
          setKeyCandidates((current) => current.map((item) => (
            item.timestamp_sec === candidate.timestamp_sec
              ? { ...item, predicted_polygon: normalized, prediction_status: 'predicted' }
              : item
          )));
        } catch (error) {
          setKeyCandidates((current) => current.map((item) => (
            item.timestamp_sec === candidate.timestamp_sec
              ? {
                  ...item,
                  prediction_status: 'failed',
                  prediction_error: error instanceof Error ? error.message : 'prediction failed',
                }
              : item
          )));
        }
      }
    } finally {
      await seekVideoForAgent(video, originalTime);
      setVideoTime(originalTime);
      pointsRef.current = seed;
      setPoints(seed);
      setFrameFrozen(wasFrozen);
      frameFrozenRef.current = wasFrozen;
      redrawRef.current();
    }
    setMessage(
      zh
        ? `已完成 ${predictedCount}/${candidates.length} 个关键帧的病灶预测`
        : `Lesion predictions completed for ${predictedCount}/${candidates.length} keyframes`,
    );
  }, [mediaMode, runSamAtPoint, simpleVideoMode, videoTime, zh]);

  useEffect(() => {
    predictKeyframesRef.current = predictKeyframes;
  }, [predictKeyframes]);

  const recordVideoFrameOverride = useCallback((poly: number[][], status: 'seed' | 'accepted' = 'accepted') => {
    if (!simpleVideoMode || mediaMode !== 'video') return;
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) return;
    const timestamp = Number((video.currentTime || 0).toFixed(3));
    const frame: VideoMaskFrameOverride = {
      timestamp_sec: timestamp,
      imageWidth: video.videoWidth,
      imageHeight: video.videoHeight,
      mask_polygon: poly.map((point) => [Math.round(point[0] * 10) / 10, Math.round(point[1] * 10) / 10]),
      roi_bbox: bboxFromPolygon(poly),
      source: 'video_track',
      propagation_status: status,
    };
    const next = [
      ...videoFrameOverridesRef.current.filter((item) => Math.abs(item.timestamp_sec - timestamp) > 0.12),
      frame,
    ].sort((a, b) => a.timestamp_sec - b.timestamp_sec);
    videoFrameOverridesRef.current = next;
    setVideoFrameOverrides(next);
  }, [mediaMode, simpleVideoMode]);

  const resumeSimpleTracking = useCallback((poly: number[][] | null) => {
    if (!simpleVideoMode || !poly || poly.length < 3) return;
    recordVideoFrameOverride(poly, videoFrameOverridesRef.current.length ? 'accepted' : 'seed');
    setTrackingPrepared(false);
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    setTrackOnPlay(true);
    setMessage(zh ? '当前帧轮廓已生成，点击播放后将连续跟踪' : 'Contour ready; playback will track subsequent frames');
  }, [recordVideoFrameOverride, simpleVideoMode, zh]);

  const getCurrentTrackedPolygon = useCallback((): number[][] => {
    if (!simpleVideoMode || mediaMode !== 'video' || !videoFrameOverridesRef.current.length) {
      return pointsRef.current;
    }
    const currentTime = videoRef.current?.currentTime || 0;
    const nearest = videoFrameOverridesRef.current.reduce((best, item) => (
      Math.abs(item.timestamp_sec - currentTime) < Math.abs(best.timestamp_sec - currentTime) ? item : best
    ), videoFrameOverridesRef.current[0]);
    return nearest?.mask_polygon?.length ? nearest.mask_polygon : pointsRef.current;
  }, [mediaMode, simpleVideoMode]);

  const precomputeVideoTracking = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || precomputeBusy) return;
    const video = videoRef.current;
    const seed = pointsRef.current;
    if (!video || !video.videoWidth || seed.length < 3) {
      setMessage(zh ? '请先在当前帧生成有效轮廓' : 'Generate a valid contour first');
      return;
    }
    const duration = video.duration || 0;
    const start = video.currentTime || 0;
    if (!duration || duration <= start + 0.05) {
      setMessage(zh ? '当前视频没有可预计算的后续帧' : 'No subsequent frames to precompute');
      return;
    }
    const originalTime = start;
    const step = Math.max(0.25, Math.min(0.5, duration / 24));
    const total = Math.max(1, Math.ceil((duration - start) / step));
    const seekTo = (time: number) => new Promise<void>((resolve) => {
      let finished = false;
      const done = () => {
        if (finished) return;
        finished = true;
        video.removeEventListener('seeked', done);
        resolve();
      };
      video.addEventListener('seeked', done);
      video.currentTime = time;
      window.setTimeout(done, 2500);
    });
    video.pause();
    setTrackOnPlay(false);
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    setPrecomputeBusy(true);
    setTrackingPrepared(false);
    try {
      for (let index = 1; index <= total; index += 1) {
        const time = Math.min(duration - 0.01, start + step * index);
        setPrecomputeProgress(`${index}/${total}`);
        await seekTo(time);
        setVideoTime(time);
        const current = pointsRef.current;
        const bbox = bboxFromPolygon(current);
        const centroid = polygonCentroid(current);
        if (!bbox || !centroid) break;
        const next = await runLesionModelRef.current(centroid, bbox, samClicksRef.current);
        if (next && next.length >= 3) {
          pointsRef.current = next;
          setPoints(next);
          recordVideoFrameOverride(next);
        }
      }
      await seekTo(originalTime);
      setVideoTime(originalTime);
      setTrackingPrepared(true);
      setTrackOnPlay(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
      setMessage(zh ? '连续跟踪已预计算，点击播放即可流畅查看' : 'Tracking precomputed; playback is ready');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '预计算失败' : 'Precompute failed'));
    } finally {
      setPrecomputeBusy(false);
      setPrecomputeProgress(null);
    }
  }, [mediaMode, precomputeBusy, recordVideoFrameOverride, simpleVideoMode, zh]);

  const maybeTrackWhilePlaying = useCallback(async () => {
    if (!trackOnPlay || mediaMode !== 'video' || !isPlaying) return;
    if (simpleVideoMode && (simpleEditMode || trackingPrepared)) return;
    if (frameFrozenRef.current || dragIndexRef.current !== null) return;
    if (trackBusyRef.current || (!simpleVideoMode && samAvailable === false)) return;
    const now = Date.now();
    if (now - lastTrackAtRef.current < 500) return;
    const poly = pointsRef.current;
    if (poly.length < 3) return;
    const bbox = bboxFromPolygon(poly);
    const centroid = polygonCentroid(poly);
    if (!bbox || !centroid) return;
    trackBusyRef.current = true;
    lastTrackAtRef.current = now;
    try {
      const nextPoly = simpleVideoMode
        ? await runLesionModelRef.current(centroid, bbox, samClicksRef.current)
        : await runSamAtPoint(centroid, {
            silent: true,
            source: 'video_track',
            box: bbox,
            keepEditing: false,
          });
      if (nextPoly && nextPoly.length >= 3) recordVideoFrameOverride(nextPoly);
    } finally {
      trackBusyRef.current = false;
    }
  }, [trackOnPlay, mediaMode, isPlaying, samAvailable, runSamAtPoint, recordVideoFrameOverride, simpleEditMode, simpleVideoMode, trackingPrepared]);


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

    const nativeVideoPlayback = simpleVideoMode && useVideo;
    ctx.clearRect(0, 0, cw, ch);
    if (!nativeVideoPlayback) {
      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, cw, ch);
      if (useVideo) ctx.drawImage(video!, dx, dy, dw, dh);
      else if (img) ctx.drawImage(img, dx, dy, dw, dh);
    }

    const map = (x: number, y: number) => ({ x: dx + x * scale, y: dy + y * scale });
    const trackedFrame = simpleVideoMode && useVideo && videoFrameOverrides.length
      ? videoFrameOverrides.reduce((best, item) => {
        if (!best) return item;
        return Math.abs(item.timestamp_sec - video!.currentTime) < Math.abs(best.timestamp_sec - video!.currentTime) ? item : best;
      }, videoFrameOverrides[0])
      : null;
    const displayPoints = trackedFrame?.mask_polygon?.length ? trackedFrame.mask_polygon : points;

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

    if (simpleVideoMode) {
      drawPoly(displayPoints, 'rgba(74, 222, 128, 0.18)', 'rgba(74, 222, 128, 0.96)');
      if (simpleEditMode && displayPoints.length >= 3) {
        drawHandles(displayPoints, Math.min(12, LESION_CTRL_COUNT), '#4ade80', 'lesion');
      }
      if (samBoxPreview) {
        const a = map(samBoxPreview.x1, samBoxPreview.y1);
        const b = map(samBoxPreview.x2, samBoxPreview.y2);
        ctx.fillStyle = 'rgba(34, 211, 238, 0.08)';
        ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        ctx.strokeStyle = 'rgba(34, 211, 238, 0.9)';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      }
    } else {
      drawPoly(wallPoints, 'rgba(251, 146, 60, 0.16)', 'rgba(251, 146, 60, 0.95)');
      drawPoly(points, 'rgba(34, 211, 238, 0.18)', 'rgba(34, 211, 238, 0.95)');
      // Dual handles like direction_demo (both editable without layer switch)
      drawHandles(wallPoints, WALL_CTRL_COUNT, '#ea580c', 'wall');
      drawHandles(points, LESION_CTRL_COUNT, '#16a34a', 'lesion');

      // Prompt markers and box preview remain available only in the legacy editor.
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
    }

  }, [points, wallPoints, imgLoaded, dragIndex, dragLayer, mediaMode, samClicks, samBoxPreview, simpleVideoMode, simpleEditMode, videoFrameOverrides]);

  useEffect(() => {
    redrawRef.current = redraw;
  }, [redraw]);
  useEffect(() => {
    maybeTrackWhilePlayingRef.current = maybeTrackWhilePlaying;
  }, [maybeTrackWhilePlaying]);
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
    const stopPlaybackLoop = () => {
      if (playbackRafRef.current !== null) {
        cancelAnimationFrame(playbackRafRef.current);
        playbackRafRef.current = null;
      }
    };
    const playbackTick = () => {
      playbackRafRef.current = null;
      if (video.paused || video.ended) return;
      const now = performance.now();
      if (now - playbackUiAtRef.current >= 80) {
        playbackUiAtRef.current = now;
        setVideoTime(video.currentTime || 0);
      }
      if (!frameFrozenRef.current && dragIndexRef.current === null) {
        redrawRef.current();
        void maybeTrackWhilePlayingRef.current();
      }
      playbackRafRef.current = requestAnimationFrame(playbackTick);
    };
    const startPlaybackLoop = () => {
      if (playbackRafRef.current === null) {
        playbackRafRef.current = requestAnimationFrame(playbackTick);
      }
    };
    const onMeta = () => {
      setVideoDuration(video.duration || 0);
      video.defaultPlaybackRate = videoPlaybackRate;
      video.playbackRate = videoPlaybackRate;
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
      if (!video.paused) startPlaybackLoop();
    };
    const onPlay = () => {
      setIsPlaying(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
      startPlaybackLoop();
    };
    const onPause = () => {
      setIsPlaying(false);
      stopPlaybackLoop();
      setVideoTime(video.currentTime || 0);
      syncFrameFromVideo({ force: true });
      redrawRef.current();
    };
    video.addEventListener('loadedmetadata', onMeta);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    video.src = videoUrl;
    video.load();
    return () => {
      stopPlaybackLoop();
      video.removeEventListener('loadedmetadata', onMeta);
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
    };
  }, [open, mediaMode, videoPlaybackRate, videoUrl, syncFrameFromVideo]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.defaultPlaybackRate = videoPlaybackRate;
    video.playbackRate = videoPlaybackRate;
  }, [videoPlaybackRate, videoUrl]);

  useEffect(() => {
    if (!open) return;
    const resizeCanvas = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      const rect = container.getBoundingClientRect();
      const nextWidth = Math.max(320, Math.floor(rect.width));
      const nextHeight = Math.max(240, Math.floor(rect.height));
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
      }
      redraw();
    };
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => requestAnimationFrame(resizeCanvas))
      : null;
    if (observer && containerRef.current) observer.observe(containerRef.current);
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', resizeCanvas);
    };
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

  const runLesionModel = useCallback(async (
    imgPt: number[] | null,
    box: { x1: number; y1: number; x2: number; y2: number } | null = null,
    clicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }> = [],
  ): Promise<number[][] | null> => {
    if (!patient || segmentationBusy) return null;
    setSegmentationBusy(true);
    setSegmentationModelResult(null);
    setMessage(
      zh
        ? `${segmentationModel === 'dinov3' ? 'DINOv3' : 'ConvNeXt-UNet'} 病灶预测中…`
        : `${segmentationModel === 'dinov3' ? 'DINOv3' : 'ConvNeXt-UNet'} lesion prediction…`,
    );
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/lesion-segmentation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame_png_b64: frame.b64,
          model: segmentationModel,
          threshold: 0.5,
          image_width: frame.width,
          image_height: frame.height,
          box: box
            ? {
                x1: box.x1 * scale,
                y1: box.y1 * scale,
                x2: box.x2 * scale,
                y2: box.y2 * scale,
              }
            : undefined,
          clicks: clicks.length
            ? clicks.map((point) => ({
                x: point.x * scale,
                y: point.y * scale,
                label: point.label,
              }))
            : imgPt
              ? [{ x: imgPt[0] * scale, y: imgPt[1] * scale, label: 'positive' }]
              : [],
        }),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        mask_polygon?: number[][];
        model?: string;
        lesion_area_ratio?: number;
        validation_summary?: Record<string, unknown>;
      };
      if (!response.ok || !data.ok || !Array.isArray(data.mask_polygon) || data.mask_polygon.length < 3) {
        throw new Error(data.error || 'Lesion model returned no valid mask');
      }
      setSegmentationModelResult({
        model: data.model,
        lesion_area_ratio: data.lesion_area_ratio,
        validation_summary: data.validation_summary,
      });
      const maxCoord = Math.max(...data.mask_polygon.flatMap((point) => point));
      const polyFull = maxCoord <= 1.5
        ? data.mask_polygon.map((point) => [point[0] * frame.fullWidth, point[1] * frame.fullHeight])
        : data.mask_polygon.map((point) => [point[0] / scale, point[1] / scale]);
      const poly = prepareEditableContour(polyFull, 96);
      pointsRef.current = poly;
      setPoints(poly);
      snapshotOriginal(poly, wallPointsRef.current);
      const assistReport = buildModelAssistReport(
        patient,
        poly,
        frame.fullWidth,
        frame.fullHeight,
        segmentationModel,
        data.lesion_area_ratio,
      );
      setSamReport(assistReport);
      onSystemReport?.(assistReport);
      setMessage(
        zh
          ? `${segmentationModel === 'dinov3' ? 'DINOv3' : 'ConvNeXt-UNet'} 已生成病灶 ROI（${poly.length} 点）`
          : `${segmentationModel === 'dinov3' ? 'DINOv3' : 'ConvNeXt-UNet'} lesion ROI ready (${poly.length} points)`,
      );
      return poly;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : 'Lesion model failed';
      setSegmentationModelResult({ error: messageText });
      setMessage(messageText);
      return null;
    } finally {
      setSegmentationBusy(false);
    }
  }, [mediaMode, onSystemReport, patient, segmentationBusy, segmentationModel, snapshotOriginal, wallPointsRef, zh]);

  useEffect(() => {
    runLesionModelRef.current = runLesionModel;
  }, [runLesionModel]);

  const runSamClick = useCallback(async (
    imgPt: number[],
    label: 'positive' | 'negative' = 'positive',
    box?: { x1: number; y1: number; x2: number; y2: number } | null,
  ) => {
    freezeCurrentFrame();
    let next = samClicksRef.current;
    const alreadyPrompted = next.some((point) => (
      Math.abs(point.x - imgPt[0]) < 1
      && Math.abs(point.y - imgPt[1]) < 1
      && point.label === label
    ));
    if (!alreadyPrompted) {
      next = [...samClicksRef.current, { x: imgPt[0], y: imgPt[1], label }];
      samClicksRef.current = next;
      setSamClicks(next);
    }
    if (simpleVideoMode && mediaMode === 'video') {
      return runLesionModel(imgPt, box || null, next);
    }
    return runSamAtPoint(imgPt, {
      keepEditing: true,
      stayInSam: true,
      source: 'sam',
      clicks: next.length ? next : undefined,
      box: box || undefined,
    });
  }, [freezeCurrentFrame, mediaMode, runLesionModel, runSamAtPoint, simpleVideoMode]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const imgPt = canvasToImage(e);
    if (!imgPt) return;

    if (simpleVideoMode && mediaMode === 'video') {
      if (samBusy || segmentationBusy) return;
      e.preventDefault();
      if (simpleEditMode && points.length >= 3) {
        const editablePoints = getCurrentTrackedPolygon();
        if (editablePoints !== pointsRef.current) {
          pointsRef.current = clonePoly(editablePoints);
          setPoints(pointsRef.current);
        }
        let nearest = -1;
        let bestDistance = hitThreshold() * hitThreshold() * 9;
        editablePoints.forEach((point, index) => {
          const distance = dist2(point, imgPt);
          if (distance <= bestDistance) {
            bestDistance = distance;
            nearest = index;
          }
        });
        if (nearest >= 0) {
          e.currentTarget.setPointerCapture(e.pointerId);
          freezeCurrentFrame();
          pushEditUndo();
          dragSoftRef.current = true;
          dragIndexRef.current = nearest;
          dragLayerRef.current = 'lesion';
          setDragIndex(nearest);
          setDragLayer('lesion');
        }
        return;
      }
      videoFrameOverridesRef.current = [];
      setVideoFrameOverrides([]);
      setTrackingPrepared(false);
      setSimpleEditMode(false);
      if (simplePromptMode === 'box') {
        clearSamPrompts();
        setSimplePromptBox(null);
        e.currentTarget.setPointerCapture(e.pointerId);
        samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
        setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
        return;
      }
      // Point prompts stay in the native multimask path; only an explicit doctor
      // box should constrain the model to a rectangular context.
      void runSamClick(imgPt, e.shiftKey ? 'negative' : 'positive', simplePromptBox)
        .then((poly) => resumeSimpleTracking(poly));
      return;
    }

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
        setSimplePromptBox(box);
        setSimplePromptMode('point');
        void runSamClick([cx, cy], 'positive', box).then((poly) => resumeSimpleTracking(poly));
      } else {
        void runSamClick(
          [boxDrag.x0, boxDrag.y0],
          neg ? 'negative' : 'positive',
        )
          .then((poly) => resumeSimpleTracking(poly));
      }
      return;
    }
    if (dragIndexRef.current !== null) {
      draggingRef.current = false;
      setPoints(clonePoly(pointsRef.current));
      setWallPoints(clonePoly(wallPointsRef.current));
      if (simpleVideoMode && mediaMode === 'video') {
        setTrackingPrepared(false);
        recordVideoFrameOverride(pointsRef.current, 'accepted');
      }
      setMessage(
        zh
          ? '当前帧区域已更新'
          : 'Current-frame region updated',
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
    const imageWidth = video.videoWidth;
    const imageHeight = video.videoHeight;
    let currentPoly = points.map((p) => [p[0], p[1]]);
    let propagatedFrames: VideoMaskFrameOverride[] = [{
      timestamp_sec: Number(start.toFixed(3)),
      imageWidth,
      imageHeight,
      mask_polygon: currentPoly.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
      roi_bbox: bboxFromPolygon(currentPoly),
      source: 'video_propagate',
      propagation_status: 'seed',
    }];
    setVideoFrameOverrides(propagatedFrames);
    let okSteps = 0;
    try {
      try {
        const centroid = polygonCentroid(currentPoly);
        const nativeResponse = await fetch('/api/agent/video/propagate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: patient?.patient_id || patient?.id || '',
            video_url: videoUrl,
            frame_time: start,
            image_width: imageWidth,
            image_height: imageHeight,
            clicks: samClicksRef.current.length
              ? samClicksRef.current
              : centroid
                ? [{ x: centroid[0], y: centroid[1], label: 'positive' }]
                : [],
            box: bboxFromPolygon(currentPoly),
            direction: 'both',
          }),
        });
        const nativePayload = await nativeResponse.json() as {
          ok?: boolean;
          error?: string;
          result?: {
            status?: string;
            needs_reanchor?: boolean;
            accepted_frames?: number;
            num_frames?: number;
            frames?: Array<{
              frame_time: number;
              direction?: string;
              mask_polygon?: number[][];
              accepted?: boolean;
              quality_score?: number;
            }>;
          };
        };
        if (!nativeResponse.ok || !nativePayload.ok || !nativePayload.result) {
          throw new Error(nativePayload.error || 'native video propagation failed');
        }
        const nativeFrames = (nativePayload.result.frames || [])
          .filter((frame) => Array.isArray(frame.mask_polygon) && frame.mask_polygon.length >= 3)
          .map((frame) => {
            const maskPolygon = frame.mask_polygon!.map((point) => [Number(point[0]), Number(point[1])]);
            return {
              timestamp_sec: Number(frame.frame_time.toFixed(3)),
              imageWidth,
              imageHeight,
              mask_polygon: maskPolygon,
              roi_bbox: bboxFromPolygon(maskPolygon),
              source: 'video_track' as const,
              propagation_status: frame.direction === 'seed' ? 'seed' as const : 'accepted' as const,
              quality_score: Number(frame.quality_score ?? 0),
            };
          });
        if (!nativeFrames.length) throw new Error('native video propagation returned no masks');
        videoFrameOverridesRef.current = nativeFrames;
        setVideoFrameOverrides(nativeFrames);
        const nearest = nativeFrames.reduce((best, frame) => (
          Math.abs(frame.timestamp_sec - start) < Math.abs(best.timestamp_sec - start) ? frame : best
        ), nativeFrames[0]);
        if (nearest?.mask_polygon?.length) {
          pointsRef.current = nearest.mask_polygon;
          setPoints(nearest.mask_polygon);
        }
        setFrameFrozen(true);
        frameFrozenRef.current = true;
        setMessage(
          zh
            ? `原生视频传播完成：${nativePayload.result.accepted_frames || nativeFrames.length}/${nativePayload.result.num_frames || nativeFrames.length} 帧${nativePayload.result.needs_reanchor ? '，已请求重锚定' : ''}`
            : `Native video propagation complete: ${nativePayload.result.accepted_frames || nativeFrames.length}/${nativePayload.result.num_frames || nativeFrames.length} frames`,
        );
        return;
      } catch (nativeError) {
        setMessage(
          zh
            ? `原生视频传播不可用，回退逐帧跟踪：${nativeError instanceof Error ? nativeError.message : 'unknown error'}`
            : 'Native propagation unavailable; falling back to sampled tracking',
        );
      }

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
        propagatedFrames = [
          ...propagatedFrames,
          {
            timestamp_sec: Number(t.toFixed(3)),
            imageWidth,
            imageHeight,
            mask_polygon: nextPoly.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
            roi_bbox: bboxFromPolygon(nextPoly),
            source: 'video_propagate',
            propagation_status: 'accepted',
          },
        ];
        setVideoFrameOverrides(propagatedFrames);
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
  }, [mediaMode, patient?.id, patient?.patient_id, points, videoUrl, zh, freezeCurrentFrame, runSamAtPoint, redraw]);

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
      video_frames: mediaMode === 'video' && videoFrameOverrides.length
        ? videoFrameOverrides
        : undefined,
      note: mediaMode === 'video' && videoFrameOverrides.length
        ? 'Video propagation stores lesion contours at sampled timestamps; wall contour remains current-frame only.'
        : undefined,
      updated_at: new Date().toISOString(),
    };
  }, [patient, points, wallPoints, roiMode, mode, mediaMode, videoTime, videoUrl, videoFrameOverrides]);

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
      setVideoFrameOverrides([]);
      clearSamPrompts();
      setSimplePromptBox(null);
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

  const openEditor = useCallback((opts?: { videoSam?: boolean; sam?: boolean; keyframes?: boolean }) => {
    if (opts?.videoSam) setPendingOpenVideoSam(true);
    if (opts?.keyframes) setPendingKeyframeRequest(true);
    if (opts?.videoSam || opts?.keyframes) setMediaMode('video');
    if (opts?.sam && !opts?.videoSam && !opts?.keyframes) setMediaMode('image');
    const useSam = Boolean(opts?.videoSam || opts?.sam);
    setMode(useSam ? 'sam' : 'soft');
    samClicksRef.current = [];
    setSamClicks([]);
    setSamBoxPreview(null);
    setSimplePromptBox(null);
    // Keep dense contours — soft-deform uses sparse control handles (direction_demo)
    setOpen(true);
    setMessage(
      useSam
        ? (zh
          ? '点击画面标记关注区域，系统返回当前帧结果'
          : 'Click the frame to get the current-frame result')
        : (zh
          ? '拖橙/绿控制点软变形边界（同人机互助 HTML）; 硬拖/加点/删点为辅助'
          : 'Drag orange/green handles to soft-deform (same as HTML demo)'),
    );
  }, [zh]);

  // AssistHub / external open request (additive; floating buttons unchanged)
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ videoSam?: boolean; sam?: boolean; keyframes?: boolean }>).detail;
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
        <div className={inline
          ? 'pointer-events-auto relative flex min-h-0 min-w-0 flex-1 items-stretch justify-stretch overflow-hidden bg-[#080b0f]'
          : 'pointer-events-auto fixed inset-0 z-[200500] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm'}>
          <div className={inline
            ? 'relative flex h-full w-full min-h-0 min-w-0 flex-col overflow-hidden bg-black'
            : 'flex h-[min(94vh,920px)] w-[min(1380px,98vw)] flex-col overflow-hidden rounded-2xl border border-cyan-400/25 bg-slate-950 shadow-2xl'}>
            <div className={`flex min-w-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-black px-3 ${simpleVideoMode ? 'py-1.5' : 'py-3'}`}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-slate-100">
                  {simpleVideoMode
                    ? (patient.id_short || patient.patient_id || 'Case')
                    : (zh ? (mediaMode === 'video' ? '视频工具' : '静态图分割') : (mediaMode === 'video' ? 'Video tools' : 'Static image segmentation'))}
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-500">
                  {simpleVideoMode
                    ? (videos.find((video) => video.url === videoUrl)?.filename || videoUrl || (zh ? '病例视频' : 'Case video'))
                    : `${patient.id_short}, ${zh
                      ? mediaMode === 'video'
                        ? '当前帧证据与 ROI 工具'
                        : '当前静态图，点击或框选病灶'
                      : mediaMode === 'video'
                        ? 'Current-frame evidence and ROI tools'
                        : 'Current image, click or box the lesion'}`}
                </div>
              </div>
              <div className={simpleVideoMode ? 'hidden' : 'flex min-w-0 flex-wrap items-center justify-end gap-2'}>
                  <button
                    type="button"
                    disabled={dinoBusy}
                    onClick={() => void extractDinoFeatures()}
                    className="rounded-lg border border-amber-300/50 bg-amber-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-amber-100 disabled:opacity-40"
                    title={zh ? '提取当前静态图或视频帧的 DINOv3 区域特征' : 'Extract DINOv3 region features from the current frame'}
                  >
                    {dinoBusy ? (zh ? 'DINO 提取中' : 'DINO running') : dinoResult?.available ? 'DINO ✓' : (zh ? 'DINO 特征' : 'DINO features')}
                  </button>
                  {mediaMode === 'video' && (
                    <>
                      <button
                        type="button"
                        disabled={!videoUrl || keyBusy}
                        onClick={() => void scoreKeyframes()}
                        className="rounded-lg border border-violet-300/50 bg-violet-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-violet-100 disabled:opacity-40"
                        title={zh ? '按清晰度、对比度和运动信息选择候选关键帧' : 'Select quality keyframes'}
                      >
                        {keyBusy ? (zh ? '关键帧打分中' : 'Scoring') : (zh ? '选择关键帧' : 'Keyframes')}
                        {keyCandidates.length ? ` (${keyCandidates.length})` : ''}
                      </button>
                      <button
                        type="button"
                        disabled={!videoUrl || propagateBusy || points.length < 3}
                        onClick={() => void propagateMaskAcrossVideo()}
                        className="rounded-lg border border-emerald-300/50 bg-emerald-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-100 disabled:opacity-40"
                      >
                        {propagateBusy ? (zh ? '传播中' : 'Propagating') : (zh ? '全视频传播' : 'Propagate')}
                      </button>
                    </>
                  )}
                  {!simpleVideoMode && (
                    <>
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
                    </>
                  )}
                  {!inline && (
                    <button
                      type="button"
                      onClick={() => setOpen(false)}
                      className="rounded-lg border border-white/15 p-2 text-slate-300 hover:bg-white/5"
                      aria-label={zh ? '关闭分割编辑器' : 'Close segmentation editor'}
                    >
                      <X size={16} />
                    </button>
                  )}
              </div>
            </div>

            {!simpleVideoMode && (
            <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-2">
              {([
                ['soft', zh ? '软变形' : 'Soft', MousePointer2],
                ['hard', zh ? '硬拖点' : 'Hard', Pencil],
                ['add', zh ? '加点' : 'Add', Plus],
                ['delete', zh ? '删点' : 'Delete', Eraser],
                ['sam', zh ? '标记关注区域' : 'Mark region', Sparkles],
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
                          ? '点击画面标记关注区域'
                          : 'Click the frame to mark a region',
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
                    setMessage(zh ? '已清除关注标记' : 'Region markers cleared');
                  }}
                  className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-100"
                >
                  {zh ? `清除标记 (${samClicks.length})` : `Clear markers (${samClicks.length})`}
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
              <button
                type="button"
                disabled={points.length < 3 && !layerResult}
                onClick={() => setWallAnalysisOpen((value) => !value)}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  wallAnalysisOpen
                    ? 'border-emerald-400/50 bg-emerald-500/20 text-emerald-100'
                    : 'border-white/10 text-slate-300 hover:bg-white/5'
                } disabled:opacity-40`}
              >
                <Layers size={13} />
                    {wallAnalysisOpen ? (zh ? '关闭组织层观察' : 'Close tissue view') : (zh ? '组织层观察' : 'Tissue view')}
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
                {zh ? `视频工具${videos.length ? ` (${videos.length})` : ''}` : `Video tools${videos.length ? ` (${videos.length})` : ''}`}
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
            )}

            {mediaMode === 'video' && (
              <>
              {simpleVideoMode ? (
                <>
                  <div className="relative z-40 flex w-full shrink-0 flex-col items-center px-2 pt-1">
                    <div className={`flex max-w-full flex-wrap items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-black/90 px-2 py-2 shadow-2xl shadow-black/50 backdrop-blur-md transition-all duration-200 ${
                      simpleToolsOpen ? 'max-h-40 translate-y-0 overflow-visible opacity-100' : 'pointer-events-none max-h-0 -translate-y-2 overflow-hidden border-transparent p-0 opacity-0'
                    }`}>
                      <button
                        type="button"
                        onClick={() => { setSimplePromptMode('point'); setSimpleEditMode(false); }}
                        className={`rounded-md border px-2.5 py-1.5 text-[10px] ${simplePromptMode === 'point' && !simpleEditMode ? 'border-white/50 bg-white/15 text-white' : 'border-white/10 text-slate-400 hover:bg-white/5'}`}
                      >
                        {zh ? (simplePromptBox ? '点选修正' : '点选') : (simplePromptBox ? 'Refine points' : 'Point')}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setSimplePromptMode('box'); setSimpleEditMode(false); }}
                        className={`rounded-md border px-2.5 py-1.5 text-[10px] ${simplePromptMode === 'box' && !simpleEditMode ? 'border-white/50 bg-white/15 text-white' : 'border-white/10 text-slate-400 hover:bg-white/5'}`}
                      >
                        {zh ? '框选' : 'Box'}
                      </button>
                      <label className="ml-1 flex items-center gap-1 rounded-md border border-white/10 px-2 py-1.5 text-[10px] text-slate-500">
                        <span>{zh ? '模型' : 'Model'}</span>
                        <select
                          value={segmentationModel}
                          onChange={(event) => setSegmentationModel(event.target.value as LesionSegmentationModel)}
                          className="max-w-[112px] bg-transparent text-slate-200 outline-none"
                          aria-label={zh ? '病灶分割模型' : 'Lesion segmentation model'}
                        >
                          <option value="dinov3">DINOv3 lesion</option>
                          <option value="convnext">ConvNeXt-UNet</option>
                        </select>
                      </label>
                      <button
                        type="button"
                        disabled={points.length < 3}
                        onClick={() => setSimpleEditMode((value) => {
                          const next = !value;
                          setTrackOnPlay(!next);
                          return next;
                        })}
                        className={`rounded-md border px-2.5 py-1.5 text-[10px] disabled:opacity-40 ${simpleEditMode ? 'border-emerald-300/60 bg-emerald-300/15 text-emerald-100' : 'border-white/10 text-slate-400 hover:bg-white/5'}`}
                      >
                        {simpleEditMode ? (zh ? '完成修正' : 'Finish edit') : (zh ? '修正轮廓' : 'Edit contour')}
                      </button>
                      <button
                        type="button"
                        disabled={!samClicks.length}
                        onClick={() => {
                          clearSamPrompts();
                          setMessage(zh ? '已清除提示点，可重新点选' : 'Prompt points cleared; add new points');
                        }}
                        className="rounded-md border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-400 hover:bg-white/5 disabled:opacity-40"
                      >
                        {zh ? `清除点 (${samClicks.length})` : `Clear points (${samClicks.length})`}
                      </button>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => void handleClear()}
                        className="rounded-md border border-amber-300/30 px-2.5 py-1.5 text-[10px] text-amber-100 hover:bg-amber-300/10 disabled:opacity-40"
                      >
                        {zh ? '重置预测' : 'Reset prediction'}
                      </button>
                      <button
                        type="button"
                        disabled={points.length < 3 || precomputeBusy}
                        onClick={() => void precomputeVideoTracking()}
                        className="rounded-md border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-400 hover:bg-white/5 disabled:opacity-40"
                      >
                        {precomputeBusy
                          ? (zh ? `跟踪 ${precomputeProgress || ''}` : `Track ${precomputeProgress || ''}`)
                          : (zh ? '预计算跟踪' : 'Precompute track')}
                      </button>
                      <button
                        type="button"
                        disabled={!videoUrl || keyBusy}
                        onClick={() => void scoreKeyframes()}
                        className="rounded-md border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-400 hover:bg-white/5 disabled:opacity-40"
                      >
                        {keyBusy ? (zh ? '关键帧中' : 'Scoring') : (zh ? '关键帧' : 'Keyframes')}
                      </button>
                      <button
                        type="button"
                        disabled={!videoUrl || unifiedAgentBusy || !onUnifiedAgentRun}
                        onClick={() => void runUnifiedAgent()}
                        className="flex items-center gap-1 rounded-md border border-white/20 bg-white/10 px-2.5 py-1.5 text-[10px] text-white hover:bg-white/15 disabled:opacity-40"
                      title={zh ? '启动当前病例 Agent，汇总知识检索与 memory 证据' : 'Start the current-case Agent with knowledge and memory evidence'}
                      >
                        <Sparkles size={10} />
                        {unifiedAgentBusy ? (zh ? 'Agent 中' : 'Agent running') : (zh ? '病例 Agent' : 'Case Agent')}
                      </button>
                      <button
                        type="button"
                        disabled={samBusy || points.length < 3}
                        onClick={() => {
                          const center = polygonCentroid(points);
                          const currentBox = bboxFromPolygon(points);
                          if (center && currentBox) {
                            freezeCurrentFrame();
                            void runSamAtPoint(center, {
                              source: 'sam',
                              box: currentBox,
                              keepEditing: true,
                              stayInSam: true,
                              llmReport: true,
                            });
                          }
                        }}
                        className="rounded-md border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-400 hover:bg-white/5 disabled:opacity-40"
                      >
                        {samBusy ? (zh ? '证据中' : 'Evidence') : (zh ? '证据' : 'Evidence')}
                      </button>
                      <button
                        type="button"
                        disabled={points.length < 3 || precomputeBusy}
                        onClick={() => setTrackOnPlay((value) => !value)}
                        className={`rounded-md border px-2.5 py-1.5 text-[10px] disabled:opacity-40 ${trackOnPlay ? 'border-emerald-300/60 bg-emerald-300/15 text-emerald-100' : 'border-white/10 text-slate-400 hover:bg-white/5'}`}
                      >
                        {trackOnPlay ? (zh ? '跟踪开' : 'Track on') : (zh ? '跟踪关' : 'Track off')}
                      </button>
                      <button
                        type="button"
                        disabled={dinoBusy}
                        onClick={() => void extractDinoFeatures()}
                        className="rounded-md border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-400 hover:bg-white/5 disabled:opacity-40"
                      >
                        {dinoBusy ? (zh ? 'DINO 中' : 'DINO running') : 'DINO'}
                      </button>
                    </div>
                    <div className={`mt-1 text-center text-[10px] text-slate-500 transition-opacity ${simpleToolsOpen ? 'opacity-100' : 'pointer-events-none h-0 overflow-hidden opacity-0'}`}>
                      {simpleEditMode
                        ? (zh ? '拖动轮廓控制点' : 'Drag contour handles')
                        : simplePromptMode === 'box'
                          ? (zh ? '拖动框选目标区域；框外内容不会被保留' : 'Draw a box; content outside it is discarded')
                          : simplePromptBox
                            ? (zh ? '在框内点选修正：正点保留，Shift+点击排除' : 'Refine inside the box: positive points keep, Shift-click excludes')
                            : (zh ? '点击目标为正点，Shift+点击背景为负点' : 'Click target for positive points; Shift-click background for negative points')}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSimpleToolsOpen((value) => !value)}
                    className="pointer-events-auto absolute right-3 top-1 z-50 flex h-8 w-8 items-center justify-center rounded-lg border border-white/15 bg-black/80 text-slate-300 shadow-lg backdrop-blur hover:bg-white/10 hover:text-white"
                    aria-label={simpleToolsOpen ? (zh ? '隐藏工具栏' : 'Hide tools') : (zh ? '显示工具栏' : 'Show tools')}
                    title={simpleToolsOpen ? (zh ? '隐藏工具栏' : 'Hide tools') : (zh ? '显示工具栏' : 'Show tools')}
                  >
                    <PanelTop size={14} />
                  </button>
                  {dinoResult ? (
                    <div className="pointer-events-auto mt-1 w-[min(220px,calc(100%-1.5rem))] self-end rounded-lg border border-white/15 bg-black/90 p-2 shadow-2xl backdrop-blur-md">
                      <div className="flex items-center justify-between gap-2 text-[10px] font-semibold text-slate-100">
                        <span>DINOv3</span>
                        <span className={dinoResult.available ? 'text-emerald-200' : 'text-amber-200'}>
                          {dinoResult.available ? 'ready' : 'failed'}
                        </span>
                      </div>
                      {dinoResult.available ? (
                        <>
                          <div className="mt-1 text-[9px] text-slate-400">
                            {dinoResult.feature_dim || 0}D · {dinoResult.token_grid?.join(' × ') || '—'} tokens
                          </div>
                          {dinoResult.feature_overlay_png ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={dinoResult.feature_overlay_png} alt="DINO feature overlay" className="mt-1.5 h-16 w-full rounded border border-white/10 object-contain" />
                          ) : null}
                        </>
                      ) : (
                        <div className="mt-1 break-words text-[9px] leading-relaxed text-amber-100/80">
                          {dinoResult.error || (zh ? 'DINO 未返回结果' : 'DINO returned no result')}
                        </div>
                      )}
                    </div>
                  ) : null}
                  {segmentationModelResult ? (
                    <div className="pointer-events-auto mt-1 w-[min(260px,calc(100%-1.5rem))] self-end rounded-lg border border-emerald-300/20 bg-black/90 px-2 py-1.5 text-[9px] shadow-lg">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-slate-400">{segmentationModelResult.model || segmentationModel}</span>
                        <span className={segmentationModelResult.error ? 'text-amber-200' : 'text-emerald-200'}>
                          {segmentationModelResult.error ? 'error' : 'mask ready'}
                        </span>
                      </div>
                      {segmentationModelResult.error ? (
                        <div className="mt-1 break-words text-amber-100/80">{segmentationModelResult.error}</div>
                      ) : (
                        <div className="mt-1 text-slate-500">
                          {zh ? '病灶占比' : 'lesion area'}: {segmentationModelResult.lesion_area_ratio != null ? `${(segmentationModelResult.lesion_area_ratio * 100).toFixed(2)}%` : '—'}
                        </div>
                      )}
                    </div>
                  ) : null}
                </>
              ) : (
              <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-black/80 px-4 py-2">
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
                  {zh ? '播放时自动跟随' : 'Auto-track on play'}
                </label>
                <button
                  type="button"
                  disabled={!videoUrl || keyBusy}
                  onClick={() => void scoreKeyframes()}
                  title={zh ? '按清晰度、对比度和运动信息选择候选关键帧' : 'Select keyframes by sharpness, contrast, and motion'}
                  className="rounded-lg border border-violet-400/40 px-2 py-1 text-[10px] text-violet-100 disabled:opacity-40"
                >
                  {keyBusy ? (zh ? '关键帧打分中…' : 'Scoring keyframes…') : (zh ? '选择关键帧' : 'Select keyframes')}
                </button>
                <button
                  type="button"
                  disabled={!videoUrl || keyBusy || propagateBusy || points.length < 3}
                  onClick={() => void propagateMaskAcrossVideo()}
                  className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-100 disabled:opacity-40"
                >
                  {propagateBusy
                    ? (zh ? `全视频传播 ${propagateProgress || ''}` : `Propagating ${propagateProgress || ''}`)
                    : (zh ? '全视频传播' : 'Propagate video')}
                </button>
                <button
                  type="button"
                  disabled={!videoUrl || samBusy || propagateBusy || points.length < 3}
                  onClick={() => {
                    freezeCurrentFrame();
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) void runSamAtPoint(c, { source: 'sam', box, keepEditing: true });
                    else setMessage(zh ? '请先点击视频画面获得当前帧结果' : 'Click the video frame first');
                  }}
                  className="rounded-lg border border-violet-400/40 px-2 py-1 text-[10px] text-violet-100 disabled:opacity-40"
                >
                  {zh ? '重新分析当前帧' : 'Re-analyze current frame'}
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
              </>
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
                      if (kf.predicted_polygon?.length && v.videoWidth && v.videoHeight) {
                        const predicted = kf.predicted_polygon.map((point) => [
                          point[0] * v.videoWidth,
                          point[1] * v.videoHeight,
                        ]);
                        pointsRef.current = predicted;
                        setPoints(predicted);
                        setFrameFrozen(true);
                        frameFrozenRef.current = true;
                        redrawRef.current();
                      }
                      setMessage(
                        zh
                          ? `${kf.prediction_status === 'predicted' ? '已应用病灶预测' : '跳转到候选'} ${kf.timestamp_sec.toFixed(2)}s, score=${kf.score}`
                          : `${kf.prediction_status === 'predicted' ? 'Lesion prediction applied' : 'Seek'} ${kf.timestamp_sec.toFixed(2)}s, score=${kf.score}`,
                      );
                    }}
                    className="flex w-[124px] shrink-0 flex-col overflow-hidden rounded-lg border border-white/10 bg-black/80 text-left hover:border-white/30"
                  >
                    <div className="relative h-16 w-full bg-black">
                      {kf.thumb_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={kf.thumb_url} alt="" className="h-full w-full object-contain" />
                      ) : (
                        <div className="flex h-full items-center justify-center text-[10px] text-slate-500">no thumb</div>
                      )}
                      {kf.predicted_polygon?.length ? (
                        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
                          <polygon
                            points={kf.predicted_polygon.map((point) => point.join(',')).join(' ')}
                            fill="rgba(255,255,255,0.16)"
                            stroke="rgba(255,255,255,0.95)"
                            strokeWidth="0.008"
                            vectorEffect="non-scaling-stroke"
                          />
                        </svg>
                      ) : null}
                      {kf.prediction_status ? (
                        <span className="absolute right-1 top-1 rounded bg-black/75 px-1 py-0.5 text-[8px] text-slate-200">
                          {kf.prediction_status === 'predicted' ? 'ROI ✓' : kf.prediction_status === 'needs_roi' ? 'ROI needed' : kf.prediction_status === 'pending' ? '...' : 'failed'}
                        </span>
                      ) : null}
                    </div>
                    <div className="px-1.5 py-1 font-mono text-[9px] text-slate-200">
                      {kf.timestamp_sec.toFixed(2)}s, {kf.score.toFixed(2)}
                    </div>
                    <div className="truncate px-1.5 pb-1 text-[8px] text-slate-400">
                      {(kf.reasons || []).join(',')}
                    </div>
                  </button>
                ))}
              </div>
            )}

            <div className="relative min-h-0 flex-1 overflow-hidden bg-black">
              <div ref={containerRef} className="relative h-full w-full bg-black">
                {mediaMode === 'video' && (
                  <video
                    ref={videoRef}
                    className={simpleVideoMode ? 'absolute inset-0 z-0 h-full w-full bg-black object-contain' : 'hidden'}
                    muted
                    playsInline
                    preload="auto"
                    crossOrigin="anonymous"
                  />
                )}
                <canvas
                  ref={canvasRef}
                  className="relative z-10 h-full w-full touch-none"
                  style={{ cursor: dragIndex !== null ? 'grabbing' : simpleEditMode ? 'grab' : mode === 'soft' || mode === 'hard' ? 'grab' : 'crosshair' }}
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
              <div className={`absolute inset-y-3 right-3 z-30 w-[min(390px,calc(100%-1.5rem))] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-xl border border-emerald-300/30 bg-slate-950/95 shadow-2xl shadow-black/60 backdrop-blur-md ${!simpleVideoMode && wallAnalysisOpen ? 'flex' : 'hidden'}`}>
                <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-3 py-2">
                  <div className="flex items-center gap-2 text-xs font-semibold text-emerald-100">
                    <Layers size={14} />
                    {zh ? '组织层观察' : 'Tissue layer observation'}
                  </div>
                  <button
                    type="button"
                    onClick={() => setWallAnalysisOpen(false)}
                    className="rounded-md border border-white/10 px-2 py-1 text-[10px] text-slate-300 hover:bg-white/10"
                  >
                    {zh ? '收起' : 'Collapse'}
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-2 custom-scrollbar">
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
                  <p className="mt-2 px-1 text-[9px] leading-relaxed text-slate-500">
                    {zh
                      ? 'ContactGeom / LayerBridge 结果是辅助提示，不作病理层次结论。Alt+点击设取样点。'
                      : 'ContactGeom / LayerBridge is assistive evidence, not pathological layer truth.'}
                  </p>
                </div>
              </div>
            </div>
            {simpleVideoMode && (
              <div className="shrink-0 border-t border-white/10 bg-black px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="w-11 shrink-0 text-right font-mono text-[10px] text-slate-500">
                    {videoTime.toFixed(2)}
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={Math.max(videoDuration, 0.01)}
                    step={0.01}
                    value={videoTime}
                    disabled={!videoUrl}
                    onChange={(event) => {
                      const nextTime = Number(event.target.value);
                      const video = videoRef.current;
                      if (!video) return;
                      video.pause();
                      video.currentTime = nextTime;
                      setVideoTime(nextTime);
                      setFrameFrozen(false);
                      frameFrozenRef.current = false;
                      syncFrameFromVideo({ force: true });
                      redrawRef.current();
                    }}
                    className="video-progress min-w-0 flex-1"
                    aria-label={zh ? '视频进度' : 'Video progress'}
                  />
                  <span className="w-11 shrink-0 font-mono text-[10px] text-slate-500">
                    {videoDuration.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-[10px] text-slate-500">
                    {videos.find((video) => video.url === videoUrl)?.filename || (zh ? '病例视频' : 'Case video')}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        video.pause();
                        const nextTime = Math.max(0, video.currentTime - 1 / 30);
                        video.currentTime = nextTime;
                        setVideoTime(nextTime);
                        syncFrameFromVideo({ force: true });
                        redrawRef.current();
                      }}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-30"
                      title={zh ? '后退一帧' : 'Previous frame'}
                    >
                      <SkipBack size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        if (video.paused) void video.play();
                        else video.pause();
                      }}
                      className="flex h-7 min-w-12 items-center justify-center gap-1 rounded-md border border-white/20 bg-white/10 px-2 text-[10px] text-white hover:bg-white/15 disabled:opacity-30"
                    >
                      {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                      {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        video.pause();
                        const nextTime = Math.min(video.duration || videoTime, video.currentTime + 1 / 30);
                        video.currentTime = nextTime;
                        setVideoTime(nextTime);
                        syncFrameFromVideo({ force: true });
                        redrawRef.current();
                      }}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-30"
                      title={zh ? '前进一帧' : 'Next frame'}
                    >
                      <SkipForward size={13} />
                    </button>
                    <label className="ml-1 flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[10px] text-slate-400">
                      <span>{zh ? '速度' : 'Speed'}</span>
                      <select
                        value={String(videoPlaybackRate)}
                        onChange={(event) => setVideoPlaybackRate(Number(event.target.value))}
                        className="bg-transparent text-slate-200 outline-none"
                        aria-label={zh ? '视频倍速' : 'Video playback speed'}
                      >
                        {VIDEO_PLAYBACK_RATES.map((rate) => (
                          <option key={rate} value={rate}>{rate}×</option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2 border-t border-white/10 px-4 py-3">
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={saving || points.length < 3}
                  onClick={() => void handleSave()}
                  className="flex items-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold text-emerald-100 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  {zh ? '保存覆盖' : 'Save override'}
                </button>
              )}
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={samBusy || points.length < 3}
                  onClick={() => {
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) {
                      freezeCurrentFrame();
                      void runSamAtPoint(c, { source: 'sam', box, keepEditing: true, stayInSam: true, llmReport: true });
                    }
                  }}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-white/10 disabled:opacity-40"
                >
                  {samBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                  {zh ? '生成系统证据' : 'Generate system evidence'}
                </button>
              )}
              {simpleVideoMode && points.length >= 3 && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void handleSave()}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-white/10 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  {zh ? '保存当前轮廓' : 'Save contour'}
                </button>
              )}
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void handleClear()}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
                >
                  <Trash2 size={13} />
                  {zh ? '清除' : 'Clear'}
                </button>
              )}
              {!inline && (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[11px] text-cyan-100"
                >
                  <Check size={13} />
                  {zh ? '完成并关闭' : 'Done'}
                </button>
              )}
              <div className="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                <ZoomIn size={12} />
                {simpleVideoMode ? (
                  <span>{zh ? '当前帧系统结果' : 'Current-frame system result'}</span>
                ) : (
                  <span>
                    {zh ? '当前层' : 'Layer'} {activeLayer === 'wall' ? wallPoints.length : points.length}pt
                    {wallPoints.length >= 3 ? `, ${zh ? '壁' : 'wall'}${wallPoints.length}` : ''}
                  </span>
                )}
                {samAvailable === false && (
                  <span className="text-amber-300/90">
                    {zh ? '系统分析服务不可用' : 'Analysis service unavailable'}
                  </span>
                )}
              </div>
            </div>
            {!simpleVideoMode && samReport && (
              <div className="border-t border-white/10 bg-black px-4 py-3 text-[11px] text-slate-200">
                <div className="font-semibold text-slate-100">{zh ? '系统证据（辅助意见）' : 'System evidence (assistive)'}</div>
                <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-400">
                  <span>{zh ? '推荐' : 'Recommendation'}: {samReport.recommended_stage || '—'}</span>
                  <span>{zh ? '置信度' : 'Confidence'}: {samReport.calibrated_confidence != null ? `${Math.round(samReport.calibrated_confidence * 100)}%` : '—'}</span>
                  <span>{zh ? '证据' : 'Evidence'}: {samReport.evidence?.length || 0}</span>
                  <span>{zh ? '相似病例' : 'Similar cases'}: {samReport.similar_cases?.length || 0}</span>
                </div>
                {samReport.summary ? <div className="mt-2 leading-relaxed text-slate-300">{sanitizeSystemCopy(samReport.summary)}</div> : null}
                <div className="mt-2 text-[10px] text-amber-200/80">{zh ? '仅供医生复核，不覆盖最终判断；证据不足时请继续查看连续帧。' : 'For clinician review only; does not overwrite final judgment.'}</div>
              </div>
            )}
            {message && (
              <div className="border-t border-white/5 px-4 py-2 text-[11px] text-slate-300">{message}</div>
            )}
          </div>
        </div>
  ) : null;

  return (
    <>
      {!inline && (<div className="pointer-events-auto absolute bottom-[5.75rem] left-3 z-[110] flex flex-col gap-2">
        <button
          type="button"
          onClick={() => openEditor({ sam: true })}
          className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-[11px] font-semibold shadow-lg backdrop-blur transition hover:-translate-y-0.5 ${
            override
              ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
              : 'border-white/15 bg-black/70 text-gray-200 hover:border-cyan-400/40'
          }`}
          title={zh ? '打开边界工具' : 'Open boundary tools'}
        >
          <Pencil size={14} />
          <span>{zh ? '边界工具' : 'Boundary tools'}</span>
          {override && (
            <span className="rounded-full bg-cyan-400/20 px-1.5 py-0.5 text-[9px] text-cyan-200">
              {override.mask_polygon.length}pt
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => openEditor({ videoSam: true })}
          className="flex items-center gap-2 rounded-xl border border-white/15 bg-black/75 px-3 py-2 text-[11px] font-semibold text-slate-200 shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:border-white/30"
          title={zh ? '直接打开本例对应视频工具' : 'Open matched patient video tools'}
        >
          <Video size={14} />
          <span>{zh ? '视频工具' : 'Video tools'}</span>
        </button>
      </div>)}
      {typeof document !== 'undefined' && !inline ? createPortal(modal, document.body) : modal}
    </>
  );
}
